#!/usr/bin/env python3
"""Fake Modbus TCP server for manual integration testing of conow_local.

Serves the same register map the integration loads
(``custom_components/conow_local/registers.json`` by default) with plausible
values, so Home Assistant can connect exactly as it would to real hardware.

Supported function codes: 0x03 read holding registers, 0x06 write single
register, 0x10 write multiple registers. Unknown addresses answer with
exception 0x02, unknown function codes with 0x01.

Examples::

    # default: 127.0.0.1:1502, values fixed
    python3 tools/fake_modbus_server.py

    # 502 needs root on macOS/Linux; 1502 works without privileges
    python3 tools/fake_modbus_server.py --port 1502

    # drifting values, so dashboards visibly update
    python3 tools/fake_modbus_server.py --live

    # only answer slave/unit id 160 (default A0)
    python3 tools/fake_modbus_server.py --slave 160

    # serve the October (v2) map and report firmware 1.2, so the integration
    # selects panel_registers.json and never touches the v1 addresses
    python3 tools/fake_modbus_server.py \
        --map custom_components/conow_local/panel/panel_registers.json \
        --firmware-version 1.2

    # serve the v1 map with no readable version, so registers.json is selected
    python3 tools/fake_modbus_server.py \
        --map custom_components/conow_local/registers.json

    # accept challenge code 000042 on direct connections (default 123456)
    python3 tools/fake_modbus_server.py --verify-code 000042

The server also starts a browser test page on ``--http-port`` (default: Modbus
port + 100, so 127.0.0.1:1602 for the default port). It can:

* edit any writable register by physical value or raw word;
* add fault rules that answer with a Modbus exception, delay the reply, or do
  not reply at all (client timeout), optionally limited to a repeat count;
* show every client request and server reply as raw hex, with the matched rule,
  exception code, and duration.

Normal replies are the default; rules only apply while enabled.

In Home Assistant's config flow choose *Modbus TCP*, host ``127.0.0.1``,
port ``1502`` (or whatever was passed to ``--port``), slave ``160``.
"""

from __future__ import annotations

import argparse
import json
import math
import socketserver
import struct
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FC_READ_HOLDING = 0x03
FC_WRITE_SINGLE = 0x06
FC_WRITE_MULTIPLE = 0x10

# Direct-connection challenge registers (0x045C–0x045D, uint32 high word first).
VERIFY_CODE_ADDRESS = 0x045C
VERIFY_CODE_DEFAULT = "123456"

EXC_ILLEGAL_FUNCTION = 0x01
EXC_ILLEGAL_ADDRESS = 0x02
EXC_ILLEGAL_VALUE = 0x03
EXC_SERVER_FAILURE = 0x04

DEFAULT_MAP = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "conow_local"
    / "registers.json"
)

# Raw values for any register the seed table does not name, keyed by unit.
UNIT_DEFAULTS = {
    "V": 230.0,
    "A": 5.0,
    "W": 100.0,
    "%": 50.0,
    "Hz": 50.0,
    "kWh": 100.0,
    "°C": 25.0,
    "℃": 25.0,
}

SEED = {
    # monitoring
    "system_status": 0x0008,  # running + charging
    "fault_code": 0,
    "battery_voltage": 52.3,
    "battery_soc": 62,
    "battery_design_capacity": 2.0,
    "battery_cell_temp_max": 27.5,
    "battery_cell_temp_min": 26.1,
    "battery_cumulative_charge_energy": 1234.5,
    "battery_cumulative_discharge_energy": 1100.2,
    "grid_active_power": 240,
    "grid_frequency": 50.01,
    "grid_cumulative_import_energy": 500.25,
    "grid_cumulative_export_energy": 320.75,
    "backup_load_power": 320,
    "backup_load_cumulative_export_energy": 88.4,
    "backup_load_cumulative_import_energy": 41.2,
    "pv_total_power": 450,
    "pv_total_cumulative_energy": 780.5,
    "pv1_power": 250,
    "pv1_cumulative_energy": 450.2,
    "pv2_power": 200,
    "pv2_cumulative_energy": 330.3,
    "pv3_power": 0,
    "pv3_cumulative_energy": 0,
    "pv4_power": 0,
    "pv4_cumulative_energy": 0,
    # control
    "grid_charge_power_limit": 800,
    "battery_discharge_power_limit": 800,
    "backup_soc": 20,
    "off_grid_output_enable": 0,
    "pv_curtailment_enable": 0,
    "charge_discharge_direction": 0,
    "battery_target_power": 0,
    "battery_cutoff_soc": 20,
}

# Seed values that are raw words rather than physical quantities.
RAW_SEED = {"system_status", "device_status", "charge_discharge_direction"}

# Registers that represent a running counter and grow while --live is on.
LIVE_SIGNALS = {
    "battery_soc": lambda t: 62 + 6 * math.sin(t / 40),
    "grid_active_power": lambda t: 240 + 140 * math.sin(t / 12),
    "pv_total_power": lambda t: 450 + 200 * math.sin(t / 9),
    "pv1_power": lambda t: 250 + 120 * math.sin(t / 9),
    "pv2_power": lambda t: 200 + 80 * math.sin(t / 9 + 1.1),
    "grid_frequency": lambda t: 50 + 0.02 * math.sin(t / 7),
    "battery_voltage": lambda t: 52.3 + 0.4 * math.sin(t / 25),
    "battery_cell_temp_max": lambda t: 27.5 + 0.8 * math.sin(t / 60),
    "battery_cell_temp_min": lambda t: 26.1 + 0.6 * math.sin(t / 60 + 0.6),
}


class IllegalAddress(Exception):
    """Modbus exception 0x02."""


class IllegalValue(Exception):
    """Modbus exception 0x03."""


class FaultRuleError(ValueError):
    """Invalid fault-injection rule supplied by the test UI."""


MAX_EVENTS = 1000
FAULT_MODES = ("exception", "drop", "delay")
FAULT_OPS = ("read", "write", "any")


class Monitor:
    """Fault-injection rules and a ring buffer of Modbus exchanges."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._next_event = 1
        self._rules: list[dict] = []
        self._next_rule = 1

    # -- exchange log --------------------------------------------------
    def record(self, event: dict) -> dict:
        """Append one exchange and return the stored event."""
        with self._lock:
            event = dict(event)
            event["id"] = self._next_event
            self._next_event += 1
            event["ts"] = time.strftime("%H:%M:%S", time.localtime(event["time"]))
            self._events.append(event)
            if len(self._events) > MAX_EVENTS:
                del self._events[: len(self._events) - MAX_EVENTS]
            return event

    def events_after(self, after: int, limit: int = 300) -> list[dict]:
        """Return events with ``id > after`` (newest last)."""
        with self._lock:
            if after <= 0:
                events = self._events[-limit:]
            else:
                events = [item for item in self._events if item["id"] > after][-limit:]
            return [dict(item) for item in events]

    def clear_events(self) -> None:
        """Drop all buffered exchanges."""
        with self._lock:
            self._events.clear()

    # -- fault rules ---------------------------------------------------
    def rules(self) -> list[dict]:
        """Return a copy of the configured rules."""
        with self._lock:
            return [dict(item) for item in self._rules]

    def add_rule(self, payload: dict) -> dict:
        """Validate and append a fault-injection rule."""
        op = str(payload.get("op", "any"))
        mode = str(payload.get("mode", "exception"))
        if op not in FAULT_OPS:
            raise FaultRuleError(f"op must be one of {', '.join(FAULT_OPS)}")
        if mode not in FAULT_MODES:
            raise FaultRuleError(f"mode must be one of {', '.join(FAULT_MODES)}")
        try:
            start = int(payload.get("start"))
            end = int(payload.get("end", start))
        except (TypeError, ValueError) as err:
            raise FaultRuleError("start/end must be integers") from err
        if not 0 <= start <= end <= 0xFFFF:
            raise FaultRuleError("expected 0 <= start <= end <= 65535")
        try:
            exception = int(payload.get("exception", EXC_SERVER_FAILURE))
            delay_ms = int(payload.get("delay_ms", 0))
            times = int(payload.get("times", 0))
        except (TypeError, ValueError) as err:
            raise FaultRuleError("exception/delay_ms/times must be integers") from err
        if not 1 <= exception <= 11:
            raise FaultRuleError("exception code must be 1–11")
        if not 0 <= delay_ms <= 60_000:
            raise FaultRuleError("delay_ms must be 0–60000")
        if not 0 <= times <= 100_000:
            raise FaultRuleError("times must be 0–100000 (0 = unlimited)")
        with self._lock:
            rule = {
                "id": self._next_rule,
                "enabled": True,
                "op": op,
                "start": start,
                "end": end,
                "mode": mode,
                "exception": exception,
                "delay_ms": delay_ms,
                "times": times,
                "remaining": times,
                "matched": 0,
            }
            self._next_rule += 1
            self._rules.append(rule)
            return dict(rule)

    def toggle_rule(self, rule_id: int, enabled: bool) -> dict | None:
        """Enable or disable a rule; re-arm a spent repeat count."""
        with self._lock:
            for rule in self._rules:
                if rule["id"] == rule_id:
                    rule["enabled"] = bool(enabled)
                    if enabled and rule["times"] > 0 and rule["remaining"] == 0:
                        rule["remaining"] = rule["times"]
                    return dict(rule)
        return None

    def delete_rule(self, rule_id: int) -> bool:
        """Remove one rule."""
        with self._lock:
            for index, rule in enumerate(self._rules):
                if rule["id"] == rule_id:
                    del self._rules[index]
                    return True
        return False

    def clear_rules(self) -> None:
        """Remove every rule."""
        with self._lock:
            self._rules.clear()

    def match(
        self, op: str, address: int | None, count: int | None
    ) -> dict | None:
        """Return the first enabled rule matching an operation/range."""
        if address is None:
            return None
        end = address + max(1, count or 1) - 1
        with self._lock:
            for rule in self._rules:
                if not rule["enabled"]:
                    continue
                if rule["op"] not in ("any", op):
                    continue
                if rule["start"] <= end and address <= rule["end"]:
                    rule["matched"] += 1
                    if rule["remaining"] > 0:
                        rule["remaining"] -= 1
                        if rule["remaining"] == 0:
                            rule["enabled"] = False
                    return dict(rule)
        return None


def describe_pdu(pdu: bytes) -> dict:
    """Return the operation/address/count/values carried by a request PDU."""
    fc = pdu[0] if pdu else 0
    if fc == FC_READ_HOLDING and len(pdu) >= 5:
        address, count = struct.unpack(">HH", pdu[1:5])
        return {"fc": fc, "op": "read", "address": address, "count": count, "values": None}
    if fc == FC_WRITE_SINGLE and len(pdu) >= 5:
        address, value = struct.unpack(">HH", pdu[1:5])
        return {
            "fc": fc,
            "op": "write",
            "address": address,
            "count": 1,
            "values": [value],
        }
    if fc == FC_WRITE_MULTIPLE and len(pdu) >= 6:
        address, quantity, byte_count = struct.unpack(">HHB", pdu[1:6])
        values = None
        if len(pdu) == 6 + byte_count and byte_count == quantity * 2:
            values = list(struct.unpack(f">{quantity}H", pdu[6:]))
        return {
            "fc": fc,
            "op": "write",
            "address": address,
            "count": quantity,
            "values": values,
        }
    return {"fc": fc, "op": "other", "address": None, "count": None, "values": None}


def describe_response(pdu: bytes) -> dict:
    """Return the exception/values carried by a response PDU."""
    if not pdu:
        return {}
    fc = pdu[0]
    if fc & 0x80:
        return {"exception": pdu[1] if len(pdu) > 1 else None}
    if fc == FC_READ_HOLDING and len(pdu) >= 2:
        byte_count = pdu[1]
        body = pdu[2 : 2 + byte_count]
        values = list(struct.unpack(f">{len(body) // 2}H", body)) if body else []
        return {"count": len(values), "values": values}
    if fc in (FC_WRITE_SINGLE, FC_WRITE_MULTIPLE):
        return {"echo": True}
    return {}


def _hex(frame: bytes) -> str:
    """Render a frame as space-separated uppercase hex bytes."""
    return " ".join(f"{byte:02X}" for byte in frame)



@dataclass(frozen=True)
class RegisterDef:
    """One register (or 32-bit pair / string) from the map file."""

    code: str
    address: int
    count: int
    dtype: str
    scale: float
    offset: float
    unit: str
    writable: bool
    block: str
    name: str = ""


class RegisterBank:
    """In-memory holding-register storage with map awareness."""

    def __init__(
        self,
        defs: list[RegisterDef],
        ranges: tuple[tuple[int, int], ...],
        verify_code: str | None = VERIFY_CODE_DEFAULT,
        firmware_version: str | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._defs = defs
        self._by_code = {item.code: item for item in defs}
        self._by_address = {item.address: item for item in defs}
        self._verify_code = int(verify_code) if verify_code is not None else None
        self._firmware_version = firmware_version
        # Continuation words of multi-word registers belong to the same def, so a
        # block write may span the high/low half of a uint32 register.
        self._owner: dict[int, RegisterDef] = {}
        for item in defs:
            for offset in range(item.count):
                self._owner[item.address + offset] = item
        self._ranges = ranges
        self._words: dict[int, int] = {}
        self._seed()

    # -- map helpers -------------------------------------------------
    def coverage(self) -> str:
        """Human readable list of served ranges."""
        return ", ".join(f"{start}–{end}" for start, end in self._ranges)

    def _check_readable(self, address: int, count: int) -> None:
        end = address + count - 1
        for start, stop in self._ranges:
            if start <= address and end <= stop:
                return
        raise IllegalAddress(f"address {address}–{end} is outside the served map")

    def _writable_def(self, address: int) -> RegisterDef:
        item = self._owner.get(address)
        if item is None or not item.writable:
            raise IllegalAddress(f"address {address} is not a writable register")
        return item

    # -- encoding ----------------------------------------------------
    @staticmethod
    def _encode(item: RegisterDef, physical: float) -> list[int]:
        raw = round(physical / item.scale + item.offset) if item.scale else 0
        if item.dtype == "int16":
            raw &= 0xFFFF
            return [raw]
        if item.dtype in ("uint32", "int32"):
            raw = int(raw) & 0xFFFFFFFF
            return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]
        if item.dtype == "string":
            return [0] * item.count
        return [int(raw) & 0xFFFF]

    def _write_def(self, item: RegisterDef, words: list[int]) -> None:
        for offset, word in enumerate(words):
            self._words[item.address + offset] = word & 0xFFFF

    def _read_def_raw(self, item: RegisterDef) -> int:
        first = self._words.get(item.address, 0)
        if item.dtype in ("uint32", "int32"):
            return (first << 16) | self._words.get(item.address + 1, 0)
        return first

    def _seed(self) -> None:
        for item in self._defs:
            if item.code == "firmware_version" and self._firmware_version:
                encoded = self._firmware_version.encode("ascii")[: item.count * 2]
                words = [
                    (encoded[index] << 8)
                    | (encoded[index + 1] if index + 1 < len(encoded) else 0)
                    for index in range(0, len(encoded), 2)
                ]
                self._write_def(item, words)
                continue
            if item.code in SEED:
                value = SEED[item.code]
                if item.code in RAW_SEED:
                    # Bit fields and enums are seeded as raw words, not physical values.
                    self._write_def(item, [int(value) & 0xFFFF])
                else:
                    self._write_def(item, self._encode(item, value))
                continue
            if item.dtype == "string":
                continue
            default = UNIT_DEFAULTS.get(item.unit, 0.0)
            self._write_def(item, self._encode(item, default))

    # -- Modbus operations -------------------------------------------
    def read(self, address: int, count: int) -> list[int]:
        """Read `count` words starting at `address`."""
        self._check_readable(address, count)
        with self._lock:
            return [self._words.get(address + i, 0) for i in range(count)]

    def write_single(self, address: int, value: int) -> None:
        """Write one holding register (FC 0x06)."""
        item = self._writable_def(address)
        with self._lock:
            self._words[address] = value & 0xFFFF
            self._reflect(item)

    def write_multiple(self, address: int, values: list[int]) -> None:
        """Write consecutive holding registers (FC 0x10)."""
        if not 1 <= len(values) <= 123:
            raise IllegalValue(f"quantity {len(values)} out of range")
        if address == VERIFY_CODE_ADDRESS and self._verify_code is not None:
            if len(values) != 2 or ((values[0] << 16) | values[1]) != self._verify_code:
                raise IllegalValue("verification code rejected")
        items = [self._writable_def(address + i) for i in range(len(values))]
        with self._lock:
            for index, value in enumerate(values):
                self._words[address + index] = value & 0xFFFF
            for item in dict.fromkeys(items):
                self._reflect(item)

    def _reflect(self, item: RegisterDef) -> None:
        """Mirror a control write into the status word the UI polls."""
        if item.code not in ("charge_discharge_direction", "device_status"):
            return
        status = self._by_code.get("system_status") or self._by_code.get("device_status")
        if status is None or status.code == item.code:
            return
        direction = self._read_def_raw(self._by_code["charge_discharge_direction"]) if (
            "charge_discharge_direction" in self._by_code
        ) else self._read_def_raw(item)
        word = self._words.get(status.address, 0)
        word &= ~0b0001_1001  # clear standby(0), charging(3), discharging(4)
        if direction == 1:
            word |= 1 << 3
        elif direction == 2:
            word |= 1 << 4
        else:
            word |= 1 << 0
        self._words[status.address] = word & 0xFFFF

    def has_code(self, code: str) -> bool:
        """Return whether the map defines this code."""
        return code in self._by_code

    def raw_of(self, code: str) -> int | None:
        """Return the raw word(s) currently held for a code."""
        item = self._by_code.get(code)
        if item is None:
            return None
        with self._lock:
            return self._read_def_raw(item)

    def set_physical(self, code: str, value: float) -> bool:
        """Set a register by code if the map defines it (used by --live)."""
        item = self._by_code.get(code)
        if item is None or item.dtype == "string":
            return False
        with self._lock:
            self._write_def(item, self._encode(item, value))
        return True

    # -- test UI -----------------------------------------------------
    def snapshot(self) -> list[dict]:
        """Return every mapped register with its current value."""
        with self._lock:
            return [self._snapshot_entry(item) for item in self._defs]

    def _snapshot_entry(self, item: RegisterDef) -> dict:
        words = [self._words.get(item.address + i, 0) & 0xFFFF for i in range(item.count)]
        raw_words = " ".join(f"{word:04X}" for word in words)
        if item.dtype == "string":
            data = b"".join(word.to_bytes(2, "big") for word in words)
            text = data.split(b"\x00", 1)[0].decode("ascii", errors="replace")
            return {
                "address": item.address,
                "address_hex": f"0x{item.address:04X}",
                "code": item.code,
                "name": item.name,
                "dtype": item.dtype,
                "count": item.count,
                "scale": item.scale,
                "offset": item.offset,
                "unit": item.unit,
                "writable": item.writable,
                "block": item.block,
                "raw": None,
                "raw_words": raw_words,
                "value": text,
                "text": text,
            }
        if item.dtype == "int16":
            raw = struct.unpack(">h", words[0].to_bytes(2, "big"))[0]
        elif item.dtype == "int32":
            packed = b"".join(word.to_bytes(2, "big") for word in words[:2])
            raw = struct.unpack(">i", packed)[0]
        elif item.dtype == "uint32":
            raw = (words[0] << 16) | words[1]
        else:
            raw = words[0]
        value = (raw - item.offset) * item.scale
        if isinstance(value, float):
            value = int(value) if value.is_integer() else round(value, 6)
        return {
            "address": item.address,
            "address_hex": f"0x{item.address:04X}",
            "code": item.code,
            "name": item.name,
            "dtype": item.dtype,
            "count": item.count,
            "scale": item.scale,
            "offset": item.offset,
            "unit": item.unit,
            "writable": item.writable,
            "block": item.block,
            "raw": raw,
            "raw_words": raw_words,
            "value": value,
            "text": None,
        }

    def set_by_address(
        self,
        address: int,
        value: float | str,
        *,
        raw: bool = False,
        code: str | None = None,
        force: bool = False,
    ) -> dict:
        """Set one register from the test UI, by physical or raw value.

        ``force`` lets the UI change read-only registers too: the fake device
        owns its memory, so monitoring values must be editable. Modbus write
        requests still go through ``write_single``/``write_multiple`` and keep
        honouring the map's ``writable`` flag.
        """
        item = self._by_code.get(code) if code else None
        if item is None:
            item = self._owner.get(int(address))
        if item is None:
            raise IllegalAddress(f"address {address} is not in the map")
        if not item.writable and not force:
            raise IllegalAddress(f"address {address} ({item.code}) is read-only")
        if item.dtype == "string":
            text = str(value)
            encoded = text.encode("ascii", errors="replace")[: item.count * 2]
            encoded = encoded.ljust(item.count * 2, b"\x00")
            words = [
                (encoded[index] << 8) | encoded[index + 1]
                for index in range(0, len(encoded), 2)
            ]
        elif raw:
            number = int(value)
            if item.dtype in ("uint32", "int32") and item.count == 2:
                number &= 0xFFFFFFFF
                words = [(number >> 16) & 0xFFFF, number & 0xFFFF]
            else:
                words = [number & 0xFFFF]
        else:
            number = float(value)
            raw_value = round(number / item.scale + item.offset) if item.scale else round(number)
            if item.dtype in ("uint32", "int32") and item.count == 2:
                raw_value &= 0xFFFFFFFF
                words = [(raw_value >> 16) & 0xFFFF, raw_value & 0xFFFF]
            else:
                words = [raw_value & 0xFFFF]
        with self._lock:
            self._write_def(item, words)
            self._reflect(item)
            return self._snapshot_entry(item)

    def reset(self) -> None:
        """Restore every register to its seeded value."""
        with self._lock:
            self._words.clear()
            self._seed()


def load_map(path: Path) -> tuple[list[RegisterDef], tuple[tuple[int, int], ...]]:
    """Parse a registers.json file into definitions plus served ranges."""
    data = json.loads(path.read_text(encoding="utf-8"))
    defs: list[RegisterDef] = []
    for item in data["registers"]:
        dtype = item.get("dtype", "uint16")
        if dtype in ("uint32", "int32"):
            count = 2
        elif dtype == "string":
            count = int(item.get("length", 1))
        else:
            count = 1
        defs.append(
            RegisterDef(
                code=item["code"],
                address=int(item["address"]),
                count=count,
                dtype=dtype,
                scale=float(item.get("scale", 1.0)),
                offset=float(item.get("offset", 0.0)),
                unit=str(item.get("unit", "")),
                writable=bool(item.get("writable", False)),
                block=str(item.get("block", "")),
                name=str(item.get("name") or item["code"]),
            )
        )

    ranges: list[tuple[int, int]] = []
    blocks = data.get("blocks", {})
    for block in {item.block for item in defs} | set(blocks):
        members = [item for item in defs if item.block == block]
        start = int(blocks.get(block, {}).get("start", members[0].address if members else 0))
        end = max((item.address + item.count - 1 for item in members), default=start)
        ranges.append((min(start, end), end))
    ranges.sort()
    # The direct-connection challenge is outside the register map file but must
    # be writable for config-flow verification tests.
    defs.append(
        RegisterDef(
            code="verify_code",
            address=VERIFY_CODE_ADDRESS,
            count=2,
            dtype="uint32",
            scale=1.0,
            offset=0.0,
            unit="",
            writable=True,
            block="verify",
        )
    )
    ranges.append((VERIFY_CODE_ADDRESS, VERIFY_CODE_ADDRESS + 1))
    return defs, tuple(ranges)


def _recv_exact(sock, size: int) -> bytes | None:
    """Read exactly `size` bytes, or None on a clean disconnect."""
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)


def _build_mbap(transaction: int, unit: int, pdu: bytes) -> bytes:
    return struct.pack(">HHHB", transaction, 0, len(pdu) + 1, unit) + pdu


def _exception(fc: int, code: int) -> bytes:
    return bytes([fc | 0x80, code])


class RequestHandler(socketserver.BaseRequestHandler):
    """Serve one Modbus TCP connection."""

    bank: RegisterBank
    monitor: Monitor
    slave: int
    verbose: bool
    peer: str = "?"

    def setup(self) -> None:
        """Record the peer address for log lines."""
        self.peer = f"{self.client_address[0]}:{self.client_address[1]}"

    def handle(self) -> None:
        """Loop over MBAP frames until the peer disconnects."""
        self.request.settimeout(60)
        try:
            self._serve_frames()
        except (TimeoutError, ConnectionResetError, BrokenPipeError):
            return

    def _serve_frames(self) -> None:
        while True:
            header = _recv_exact(self.request, 7)
            if header is None:
                return
            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            if protocol != 0 or length < 2:
                self._log(f"bad MBAP header proto={protocol} length={length}, closing")
                return
            pdu = _recv_exact(self.request, length - 1)
            if pdu is None:
                return
            if self.slave and unit != self.slave:
                self._log(f"ignored request for unit {unit} (expecting {self.slave})")
                continue
            self._handle_pdu(transaction, unit, header, pdu)

    def _handle_pdu(
        self, transaction: int, unit: int, header: bytes, pdu: bytes
    ) -> None:
        """Apply fault rules, dispatch the PDU, and log the exchange."""
        started = time.monotonic()
        info = describe_pdu(pdu)
        request_frame = header + pdu
        rule = self.monitor.match(info["op"], info["address"], info["count"])
        delay_ms = 0
        if rule is not None and rule["mode"] == "delay":
            delay_ms = int(rule.get("delay_ms") or 0)
            if delay_ms:
                time.sleep(delay_ms / 1000)

        dropped = rule is not None and rule["mode"] == "drop"
        response: bytes | None = None
        if rule is not None and rule["mode"] == "exception":
            response = _exception(
                info["fc"], int(rule.get("exception") or EXC_SERVER_FAILURE)
            )
        elif not dropped:
            try:
                response = self._dispatch(pdu)
            except Exception as exc:  # noqa: BLE001 - keep the server alive
                # `response` must stay a bare PDU: it is framed below.
                self._log(f"handler error: {exc!r}")
                response = _exception(info["fc"], EXC_SERVER_FAILURE)

        response_frame = (
            _build_mbap(transaction, unit, response) if response is not None else b""
        )
        if response_frame:
            self.request.sendall(response_frame)

        reply = describe_response(response) if response is not None else {}
        event = {
            "time": time.time(),
            "peer": self.peer,
            "transaction": transaction,
            "unit": unit,
            "fc": info["fc"],
            "op": info["op"],
            "address": info["address"],
            "count": info["count"],
            "values": info["values"],
            "tx": _hex(request_frame),
            "rx": _hex(response_frame),
            "exception": reply.get("exception"),
            "reply_count": reply.get("count"),
            "reply_values": reply.get("values"),
            "dropped": dropped,
            "delay_ms": delay_ms,
            "rule": rule,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
        self.monitor.record(event)
        self._log_exchange(event)

    def _log_exchange(self, event: dict) -> None:
        """Print the raw request/reply pair when verbose."""
        if not self.verbose:
            return
        stamp = time.strftime("%H:%M:%S")
        print(f"{stamp} [{event['peer']}] <- {event['tx']}", flush=True)
        if event["dropped"]:
            rule_id = event["rule"]["id"] if event["rule"] else "?"
            print(
                f"{stamp} [{event['peer']}] -> (dropped by rule #{rule_id}, no reply)",
                flush=True,
            )
            return
        print(
            f"{stamp} [{event['peer']}] -> {event['rx']} "
            f"({event['duration_ms']} ms)",
            flush=True,
        )

    # -- PDU handling -------------------------------------------------
    def _dispatch(self, pdu: bytes) -> bytes:
        fc = pdu[0] if pdu else 0
        if fc == FC_READ_HOLDING:
            return self._read(pdu)
        if fc == FC_WRITE_SINGLE:
            return self._write_single(pdu)
        if fc == FC_WRITE_MULTIPLE:
            return self._write_multiple(pdu)
        self._log(f"FC{fc:02X} unsupported -> exception 0x01")
        return _exception(fc, EXC_ILLEGAL_FUNCTION)

    def _read(self, pdu: bytes) -> bytes:
        if len(pdu) != 5:
            return _exception(FC_READ_HOLDING, EXC_ILLEGAL_VALUE)
        address, count = struct.unpack(">HH", pdu[1:5])
        if not 1 <= count <= 125:
            return _exception(FC_READ_HOLDING, EXC_ILLEGAL_VALUE)
        try:
            words = self.bank.read(address, count)
        except IllegalAddress as exc:
            self._log(f"FC03 addr={address} count={count} -> exception 0x02 ({exc})")
            return _exception(FC_READ_HOLDING, EXC_ILLEGAL_ADDRESS)
        self._log(f"FC03 addr={address} count={count} -> {count} regs")
        return bytes([FC_READ_HOLDING, count * 2]) + b"".join(
            struct.pack(">H", word) for word in words
        )

    def _write_single(self, pdu: bytes) -> bytes:
        if len(pdu) != 5:
            return _exception(FC_WRITE_SINGLE, EXC_ILLEGAL_VALUE)
        address, value = struct.unpack(">HH", pdu[1:5])
        try:
            self.bank.write_single(address, value)
        except IllegalAddress as exc:
            self._log(f"FC06 addr={address} value={value} -> exception 0x02 ({exc})")
            return _exception(FC_WRITE_SINGLE, EXC_ILLEGAL_ADDRESS)
        self._log(f"FC06 addr={address} value={value} -> ok")
        return pdu

    def _write_multiple(self, pdu: bytes) -> bytes:
        if len(pdu) < 6:
            return _exception(FC_WRITE_MULTIPLE, EXC_ILLEGAL_VALUE)
        address, quantity, byte_count = struct.unpack(">HHB", pdu[1:6])
        if byte_count != quantity * 2 or len(pdu) != 6 + byte_count:
            self._log(f"FC10 addr={address} qty={quantity} -> exception 0x03 (byte count)")
            return _exception(FC_WRITE_MULTIPLE, EXC_ILLEGAL_VALUE)
        values = list(struct.unpack(f">{quantity}H", pdu[6:]))
        try:
            self.bank.write_multiple(address, values)
        except IllegalAddress as exc:
            self._log(f"FC10 addr={address} qty={quantity} -> exception 0x02 ({exc})")
            return _exception(FC_WRITE_MULTIPLE, EXC_ILLEGAL_ADDRESS)
        except IllegalValue as exc:
            self._log(f"FC10 addr={address} qty={quantity} -> exception 0x03 ({exc})")
            return _exception(FC_WRITE_MULTIPLE, EXC_ILLEGAL_VALUE)
        self._log(f"FC10 addr={address} qty={quantity} values={values} -> ok")
        return pdu[:5]

    def _log(self, message: str) -> None:
        if self.verbose:
            stamp = time.strftime("%H:%M:%S")
            print(f"{stamp} [{self.peer}] {message}", flush=True)


class FakeModbusServer(socketserver.ThreadingTCPServer):
    """Threaded TCP server that reuses the address and survives errors."""

    allow_reuse_address = True
    daemon_threads = True


TEST_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Conow 模拟 Modbus 测试台</title>
<style>
*{box-sizing:border-box}
:root{--bg:#eef1f5;--card:#fff;--ink:#17212b;--muted:#667085;--line:#dde3ea;--accent:#2f6fed;--accent-ink:#fff;--ok:#12805c;--warn:#b54708;--bad:#c0293b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme: dark){:root{--bg:#0f141a;--card:#161d26;--ink:#e6edf3;--muted:#94a3b8;--line:#263241;--accent:#5b8cff;--accent-ink:#0b1020;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171}}
html,body{margin:0;height:100%}
body{font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 18px;padding:13px 18px;background:var(--card);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
h1{font-size:17px;margin:0}
h2{font-size:14px;margin:0}
.meta{color:var(--muted);font-size:12px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stats{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.badge{font-size:11px;padding:3px 8px;border:1px solid var(--line);border-radius:999px;color:var(--muted);white-space:nowrap}
main{padding:14px;display:grid;gap:14px}
.bottom{display:grid;grid-template-columns:430px minmax(0,1fr);gap:14px;align-items:start}
@media(max-width:1100px){.bottom{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;min-width:0}
.card-head{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:10px}
.card-head h2{margin-right:2px}
input,select,button{font:inherit;color:inherit}
input[type=text],input[type=search],input[type=number],select{background:transparent;border:1px solid var(--line);border-radius:8px;padding:6px 8px;color:inherit;min-width:0}
input:focus,select:focus{outline:2px solid color-mix(in srgb,var(--accent) 35%,transparent);outline-offset:0}
button{background:var(--accent);color:var(--accent-ink);border:0;border-radius:8px;padding:7px 12px;cursor:pointer;font-weight:600}
button:hover{filter:brightness(1.06)}
button.small{padding:4px 9px;font-size:12px}
button.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
button.danger{background:transparent;color:var(--bad);border:1px solid color-mix(in srgb,var(--bad) 45%,transparent)}
.check{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);user-select:none;cursor:pointer;white-space:nowrap}
.muted{color:var(--muted);font-size:12px}
.mono{font-family:var(--mono)}
.table-wrap{max-height:46vh;overflow:auto;border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:13px}
th{position:sticky;top:0;background:var(--card);z-index:1;text-align:left;font-size:11px;letter-spacing:.04em;color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
tr:last-child td{border-bottom:0}
tr.writable td:first-child{box-shadow:inset 3px 0 var(--accent)}
.addr{white-space:nowrap;color:var(--muted)}
.code{font-family:var(--mono);font-size:12px;word-break:break-all}
.name{font-size:11px;color:var(--muted);max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.valwrap{display:flex;align-items:center;gap:6px}
.val{width:112px;font-family:var(--mono);font-size:12px;padding:5px 7px;border:1px solid var(--line);border-radius:7px;background:transparent}
.val.wide{width:190px}
.val[disabled]{opacity:.55}
.val.flash{animation:flash .6s}
@keyframes flash{0%{background:color-mix(in srgb,var(--accent) 30%,transparent)}100%{background:transparent}}
.unit{font-size:11px;color:var(--muted);min-width:24px}
.raw{font-family:var(--mono);font-size:11px;color:var(--muted);white-space:nowrap}
.ro{margin-left:6px;font-size:10px;border:1px solid var(--line);border-radius:4px;padding:0 4px;color:var(--muted)}
#ruleForm{display:grid;gap:10px;margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.form-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:10px}
.form-row label{display:flex;flex-direction:column;gap:4px;font-size:11px;color:var(--muted)}
.form-row input,.form-row select{width:100%}
#ruleForm button{justify-self:start}
.rule{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:2px 10px;padding:9px 10px;border:1px solid var(--line);border-radius:9px;margin-bottom:8px;background:color-mix(in srgb,var(--ink) 2%,transparent)}
.rule.disabled{opacity:.5}
.rule-title{font-family:var(--mono);font-size:12px;word-break:break-word}
.rule-meta{grid-column:1;font-size:11px;color:var(--muted)}
.rule-actions{grid-column:2;grid-row:1 / span 2;display:flex;gap:6px;align-items:center}
.log-list{max-height:58vh;overflow:auto;border:1px solid var(--line);border-radius:10px;font-size:12px}
.log{padding:7px 10px;border-bottom:1px solid var(--line);display:grid;grid-template-columns:116px minmax(0,1fr);gap:10px}
.log:last-child{border-bottom:0}
.log.exc{box-shadow:inset 3px 0 var(--bad)}
.log.drop{box-shadow:inset 3px 0 var(--warn)}
.log-meta{font-family:var(--mono);font-size:10.5px;color:var(--muted);line-height:1.65;word-break:break-all}
.log-row{display:grid;grid-template-columns:16px minmax(0,1fr);gap:0 8px;line-height:1.5}
.log-row .desc{font-family:var(--mono);font-size:11.5px;word-break:break-word}
.log-row .hex{grid-column:2;font-family:var(--mono);font-size:10.5px;color:var(--muted);word-break:break-all;margin-top:1px}
.dir{grid-row:1 / span 2;color:var(--accent);font-weight:700;text-align:center}
.log.exc .log-row.reply .desc{color:var(--bad)}
.log.drop .log-row.reply .desc{color:var(--warn)}
.tag{display:inline-block;margin-left:6px;padding:0 5px;border-radius:4px;background:color-mix(in srgb,var(--bad) 15%,transparent);color:var(--bad);font-size:10px;font-family:inherit}
#toast{position:fixed;right:18px;bottom:18px;background:var(--ink);color:var(--bg);padding:9px 14px;border-radius:9px;font-size:12.5px;opacity:0;transform:translateY(6px);transition:.18s;pointer-events:none;max-width:380px;z-index:50}
#toast.show{opacity:1;transform:none}
#toast.bad{background:var(--bad);color:#fff}
</style>
</head>
<body>
<header>
  <h1>Conow 模拟 Modbus 测试台</h1>
  <div id="meta" class="meta">连接中…</div>
  <div class="stats">
    <span id="regCount" class="badge">0 个寄存器</span>
    <span id="ruleCount" class="badge">0 条故障规则</span>
  </div>
</header>
<main>
  <section class="card">
    <div class="card-head">
      <h2>寄存器</h2>
      <input id="search" type="search" placeholder="搜索代码 / 名称 / 地址 / 区块" style="flex:1 1 220px">
      <label class="check"><input type="checkbox" id="onlyWritable"> 只看可写</label>
      <label class="check"><input type="checkbox" id="rawMode"> 原始值编辑</label>
      <button id="resetAll" class="small ghost" type="button">恢复初始值</button>
    </div>
    <p class="muted" style="margin:0 0 8px">可直接改写任意寄存器的模拟值；Modbus 写请求仍按 Map 的 writable 权限校验。</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th>地址</th><th>代码 / 名称</th><th>类型</th><th>值</th><th>原始字</th><th>操作</th></tr></thead>
        <tbody id="regBody"></tbody>
      </table>
    </div>
  </section>
  <div class="bottom">
    <section class="card">
      <div class="card-head">
        <h2>故障注入</h2>
        <button id="clearRules" class="small ghost" type="button">清空规则</button>
        <span class="muted">默认全部正常回复</span>
      </div>
      <form id="ruleForm">
        <div class="form-row">
          <label>操作
            <select id="ruleOp">
              <option value="any">读 + 写</option>
              <option value="read">读 (FC03)</option>
              <option value="write">写 (FC06/10)</option>
            </select>
          </label>
          <label>起始地址
            <input id="ruleStart" type="text" value="10000">
          </label>
          <label>结束地址
            <input id="ruleEnd" type="text" placeholder="同起始">
          </label>
        </div>
        <div class="form-row">
          <label>动作
            <select id="ruleMode">
              <option value="exception">返回异常报文</option>
              <option value="drop">不回复（超时）</option>
              <option value="delay">延迟回复</option>
            </select>
          </label>
          <label id="excField">异常码
            <select id="ruleException">
              <option value="1">01 非法功能</option>
              <option value="2">02 非法地址</option>
              <option value="3">03 非法值</option>
              <option value="4" selected>04 从站故障</option>
              <option value="5">05 确认</option>
              <option value="6">06 从站忙</option>
              <option value="8">08 存储校验失败</option>
              <option value="10">0A 网关路径不可用</option>
              <option value="11">0B 网关目标无响应</option>
            </select>
          </label>
          <label id="delayField">延迟 (ms)
            <input id="ruleDelay" type="number" min="0" max="60000" value="2000">
          </label>
          <label>次数 (0 = 不限)
            <input id="ruleTimes" type="number" min="0" value="0">
          </label>
        </div>
        <button type="submit">添加规则</button>
      </form>
      <p class="muted" style="margin:0 0 10px">重叠规则按添加顺序匹配，第一条生效；次数用完会自动禁用。</p>
      <div id="ruleList"></div>
    </section>
    <section class="card">
      <div class="card-head">
        <h2>报文监控</h2>
        <label class="check"><input type="checkbox" id="autoScroll" checked> 自动滚动</label>
        <label class="check"><input type="checkbox" id="pauseLogs"> 暂停</label>
        <button id="clearLogs" class="small ghost" type="button">清空</button>
        <span id="logHint" class="muted">实时</span>
      </div>
      <div id="logList" class="log-list"></div>
    </section>
  </div>
</main>
<div id="toast"></div>
<script>
const $ = (id) => document.getElementById(id);
let registers = [];
const rows = new Map();
let lastLogId = 0;
let logPaused = false;
let filter = "";
let onlyWritable = false;
let rawMode = false;
let tableKey = "";
let fetchingLogs = false;

function hex(value) {
  return "0x" + Number(value).toString(16).toUpperCase().padStart(4, "0");
}
function registerKey(register) {
  return register.address + "|" + register.code;
}
function parseNumber(text) {
  const value = String(text).trim();
  if (/^[+-]?0x[0-9a-f]+$/i.test(value)) return parseInt(value, 16);
  if (/^[+-]?\d+$/.test(value)) return parseInt(value, 10);
  const number = Number(value);
  return Number.isFinite(number) ? number : NaN;
}
async function api(path, options) {
  const response = await fetch(path, Object.assign({cache: "no-store"}, options));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}
function post(path, body) {
  return api(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body || {})
  });
}
let toastTimer = 0;
function toast(message, bad) {
  const el = $("toast");
  el.textContent = message;
  el.className = "show" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.className = ""; }, 2400);
}

function updateStats() {
  $("regCount").textContent = registers.length + " 个寄存器";
}
function maybeBuildTable() {
  const key = filter + "|" + onlyWritable + "|" + rawMode;
  if (key === tableKey) return;
  tableKey = key;
  buildTable();
}
function buildTable() {
  const query = filter.trim().toLowerCase();
  const body = $("regBody");
  body.textContent = "";
  rows.clear();
  for (const register of registers) {
    if (onlyWritable && !register.writable) continue;
    if (query) {
      const haystack = [
        register.code, register.name, register.block,
        register.address, hex(register.address)
      ].join(" ").toLowerCase();
      if (!haystack.includes(query)) continue;
    }
    const tr = document.createElement("tr");
    if (register.writable) tr.classList.add("writable");

    const address = document.createElement("td");
    address.className = "mono addr";
    address.textContent = hex(register.address);
    address.title = String(register.address);

    const info = document.createElement("td");
    const code = document.createElement("div");
    code.className = "code";
    code.textContent = register.code;
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = register.name;
    name.title = register.name;
    info.append(code, name);

    const dtype = document.createElement("td");
    dtype.className = "mono";
    dtype.textContent = register.dtype + (register.count > 1 ? " ×" + register.count : "");

    const valueCell = document.createElement("td");
    const wrap = document.createElement("div");
    wrap.className = "valwrap";
    const input = document.createElement("input");
    input.className = "val" + (register.dtype === "string" ? " wide" : "");
    input.type = "text";
    input.dataset.address = register.address;
    input.addEventListener("input", () => { input.dataset.dirty = "1"; });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") writeRegister(register, input);
    });
    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = register.unit || "";
    wrap.append(input, unit);
    valueCell.append(wrap);

    const raw = document.createElement("td");
    raw.className = "raw";

    const action = document.createElement("td");
    const button = document.createElement("button");
    button.className = "small";
    button.type = "button";
    button.textContent = "写入";
    button.addEventListener("click", () => writeRegister(register, input));
    action.append(button);
    if (!register.writable) {
      const readOnly = document.createElement("span");
      readOnly.className = "muted ro";
      readOnly.textContent = "只读";
      readOnly.title = "Map 中标记为只读；测试页仍可模拟写入";
      action.append(readOnly);
    }

    tr.append(address, info, dtype, valueCell, raw, action);
    body.append(tr);
    rows.set(registerKey(register), {register, input, raw, tr});
  }
}
function updateValues() {
  for (const register of registers) {
    const row = rows.get(registerKey(register));
    if (!row) continue;
    const focused = document.activeElement === row.input;
    const dirty = row.input.dataset.dirty === "1";
    if (!focused && !dirty) {
      if (register.dtype === "string") {
        row.input.value = register.text || "";
      } else if (rawMode) {
        row.input.value = String(register.raw);
      } else {
        row.input.value = String(register.value);
      }
    }
    let rawText = register.raw_words;
    if (register.raw !== null && register.raw !== undefined) {
      rawText += "  |  " + register.raw;
    }
    row.raw.textContent = rawText;
    row.input.title = "地址 " + register.address + " (" + register.address_hex + ")  原始: " + register.raw_words;
  }
}
async function writeRegister(register, input) {
  const text = input.value.trim();
  let value = text;
  if (register.dtype !== "string") {
    value = parseNumber(text);
    if (!Number.isFinite(value)) return toast("请输入有效数字", true);
  }
  try {
    const data = await post("/api/register", {
      address: register.address,
      code: register.code,
      value: value,
      raw: register.dtype !== "string" && rawMode
    });
    const index = registers.findIndex((item) => registerKey(item) === registerKey(register));
    if (index >= 0) registers[index] = data.register;
    input.dataset.dirty = "";
    input.classList.remove("flash");
    void input.offsetWidth;
    input.classList.add("flash");
    toast("已写入 " + hex(register.address) + " " + register.code);
    updateValues();
  } catch (error) {
    toast("写入失败: " + error.message, true);
  }
}

function syncRuleFields() {
  const mode = $("ruleMode").value;
  $("excField").style.display = mode === "exception" ? "" : "none";
  $("delayField").style.display = mode === "delay" ? "" : "none";
}
function describeRule(rule) {
  const op = rule.op === "read" ? "读" : rule.op === "write" ? "写" : "读+写";
  const range = rule.start === rule.end ? hex(rule.start) : hex(rule.start) + "–" + hex(rule.end);
  let action = "";
  if (rule.mode === "exception") {
    action = "异常回应 0x" + Number(rule.exception).toString(16).toUpperCase().padStart(2, "0");
  } else if (rule.mode === "drop") {
    action = "不回复（客户端超时）";
  } else {
    action = "延迟 " + rule.delay_ms + " ms 后回复";
  }
  return "#" + rule.id + "  " + op + "  " + range + " → " + action;
}
function renderRules(rules) {
  $("ruleCount").textContent = rules.length + " 条故障规则";
  const box = $("ruleList");
  box.textContent = "";
  if (!rules.length) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "暂无规则，所有请求按正常报文回复。";
    box.append(empty);
    return;
  }
  for (const rule of rules) {
    const item = document.createElement("div");
    item.className = "rule" + (rule.enabled ? "" : " disabled");
    const title = document.createElement("div");
    title.className = "rule-title";
    title.textContent = describeRule(rule);
    const meta = document.createElement("div");
    meta.className = "rule-meta";
    meta.textContent = "已匹配 " + rule.matched + " 次 · " +
      (rule.times ? "剩余 " + rule.remaining + "/" + rule.times : "不限次数");
    const actions = document.createElement("div");
    actions.className = "rule-actions";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "small ghost";
    toggle.textContent = rule.enabled ? "禁用" : "启用";
    toggle.addEventListener("click", () => toggleRule(rule));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "small danger";
    remove.textContent = "删除";
    remove.addEventListener("click", () => deleteRule(rule));
    actions.append(toggle, remove);
    item.append(title, meta, actions);
    box.append(item);
  }
}
async function toggleRule(rule) {
  try {
    await post("/api/rules/" + rule.id + "/toggle", {enabled: !rule.enabled});
    await loadState();
  } catch (error) {
    toast("操作失败: " + error.message, true);
  }
}
async function deleteRule(rule) {
  try {
    await api("/api/rules/" + rule.id, {method: "DELETE"});
    await loadState();
  } catch (error) {
    toast("删除失败: " + error.message, true);
  }
}

function describeRequest(event) {
  const op = event.op === "read" ? "读" : event.op === "write" ? "写" : "其他";
  let text = "FC" + Number(event.fc).toString(16).toUpperCase().padStart(2, "0") + " " + op;
  if (event.address !== null && event.address !== undefined) text += " " + hex(event.address);
  if (event.count) text += " × " + event.count;
  if (event.values && event.values.length) text += "  ← [" + event.values.join(", ") + "]";
  return text;
}
function describeReply(event) {
  if (event.dropped) return "未回复（故障注入：客户端会超时）";
  if (event.exception) {
    return "异常回应 0x" + Number(event.exception).toString(16).toUpperCase().padStart(2, "0");
  }
  if (event.reply_count !== null && event.reply_count !== undefined) {
    return "正常回应，返回 " + event.reply_count + " 个寄存器";
  }
  return "正常回应";
}
function appendLogs(events) {
  const list = $("logList");
  for (const event of events) {
    const item = document.createElement("div");
    item.className = "log" + (event.exception ? " exc" : "") + (event.dropped ? " drop" : "");

    const meta = document.createElement("div");
    meta.className = "log-meta";
    meta.textContent = event.ts + "\n" + event.peer;
    meta.style.whiteSpace = "pre-line";

    const body = document.createElement("div");
    const request = document.createElement("div");
    request.className = "log-row";
    const requestDir = document.createElement("span");
    requestDir.className = "dir";
    requestDir.textContent = "←";
    const requestDesc = document.createElement("span");
    requestDesc.className = "desc";
    requestDesc.textContent = describeRequest(event);
    if (event.rule) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = "规则 #" + event.rule.id;
      requestDesc.append(tag);
    }
    const requestHex = document.createElement("span");
    requestHex.className = "hex";
    requestHex.textContent = event.tx;
    request.append(requestDir, requestDesc, requestHex);

    const reply = document.createElement("div");
    reply.className = "log-row reply";
    const replyDir = document.createElement("span");
    replyDir.className = "dir";
    replyDir.textContent = "→";
    const replyDesc = document.createElement("span");
    replyDesc.className = "desc";
    const duration = event.duration_ms !== undefined && event.duration_ms !== null
      ? "  (" + event.duration_ms + " ms)" : "";
    replyDesc.textContent = describeReply(event) + duration;
    const replyHex = document.createElement("span");
    replyHex.className = "hex";
    replyHex.textContent = event.rx || "(无回复)";
    reply.append(replyDir, replyDesc, replyHex);

    body.append(request, reply);
    item.append(meta, body);
    list.append(item);
  }
  while (list.children.length > 500) list.firstChild.remove();
  if ($("autoScroll").checked) list.scrollTop = list.scrollHeight;
}
async function loadLogs() {
  if (logPaused || fetchingLogs) return;
  fetchingLogs = true;
  try {
    const data = await api("/api/logs?after=" + lastLogId + "&limit=200");
    if (data.events.length) appendLogs(data.events);
    lastLogId = data.last;
    $("logHint").textContent = "实时";
  } catch (error) {
    $("logHint").textContent = "日志连接失败";
  } finally {
    fetchingLogs = false;
  }
}

async function loadState() {
  try {
    const state = await api("/api/state");
    const mapName = String(state.map).split("/").pop();
    $("meta").textContent = mapName + " · Modbus :" + state.modbus_port +
      " · 从站 " + (state.slave || "任意") + " · 服务范围 " + state.coverage;
    $("meta").title = state.map;
    registers = state.registers;
    updateStats();
    maybeBuildTable();
    updateValues();
    renderRules(state.rules);
  } catch (error) {
    $("meta").textContent = "连接失败: " + error.message;
  }
}

$("search").addEventListener("input", (event) => {
  filter = event.target.value;
  maybeBuildTable();
  updateValues();
});
$("onlyWritable").addEventListener("change", (event) => {
  onlyWritable = event.target.checked;
  maybeBuildTable();
  updateValues();
});
$("rawMode").addEventListener("change", (event) => {
  rawMode = event.target.checked;
  maybeBuildTable();
  updateValues();
});
$("resetAll").addEventListener("click", async () => {
  try {
    await post("/api/reset", {});
    await loadState();
    toast("已恢复初始值");
  } catch (error) {
    toast("重置失败: " + error.message, true);
  }
});
$("ruleMode").addEventListener("change", syncRuleFields);
$("ruleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const start = parseNumber($("ruleStart").value);
  const endText = $("ruleEnd").value.trim();
  const end = endText ? parseNumber(endText) : start;
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return toast("地址必须是数字，可写 0x 前缀", true);
  }
  const payload = {
    op: $("ruleOp").value,
    start: start,
    end: end,
    mode: $("ruleMode").value,
    exception: Number($("ruleException").value),
    delay_ms: Number($("ruleDelay").value) || 0,
    times: Number($("ruleTimes").value) || 0
  };
  try {
    const data = await post("/api/rules", payload);
    toast("已添加规则 #" + data.rule.id);
    await loadState();
  } catch (error) {
    toast("添加失败: " + error.message, true);
  }
});
$("clearRules").addEventListener("click", async () => {
  try {
    await post("/api/rules/clear", {});
    await loadState();
    toast("已清空规则");
  } catch (error) {
    toast("操作失败: " + error.message, true);
  }
});
$("pauseLogs").addEventListener("change", (event) => {
  logPaused = event.target.checked;
  $("logHint").textContent = logPaused ? "已暂停" : "实时";
  if (!logPaused) loadLogs();
});
$("clearLogs").addEventListener("click", async () => {
  try {
    await post("/api/logs/clear", {});
    $("logList").textContent = "";
    lastLogId = 0;
    toast("日志已清空");
  } catch (error) {
    toast("清空失败: " + error.message, true);
  }
});

syncRuleFields();
loadState();
loadLogs();
setInterval(loadState, 2000);
setInterval(loadLogs, 1000);
</script>
</body>
</html>
"""


class TestHTTPHandler(BaseHTTPRequestHandler):
    """Serve the browser test page and its JSON API."""

    protocol_version = "HTTP/1.1"
    server: "TestHTTPServer"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        """Keep the console for Modbus traffic, not HTTP access logs."""

    def _send_bytes(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _error(self, status: int, message: object) -> None:
        self._send_json(status, {"error": str(message)})

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise FaultRuleError("request body too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise FaultRuleError(f"invalid JSON: {err}") from err
        if not isinstance(payload, dict):
            raise FaultRuleError("JSON body must be an object")
        return payload

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Serve the page, state, or buffered log events."""
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send_bytes(200, TEST_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/state":
            self._send_json(200, self.server.state())
            return
        if parsed.path == "/api/logs":
            query = parse_qs(parsed.query)
            try:
                after = int(query.get("after", ["0"])[0])
            except ValueError:
                after = 0
            try:
                limit = int(query.get("limit", ["300"])[0])
            except ValueError:
                limit = 300
            limit = max(1, min(limit, 1000))
            events = self.server.monitor.events_after(after, limit)
            last = events[-1]["id"] if events else after
            self._send_json(200, {"events": events, "last": last})
            return
        self._error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Handle register writes, rule changes, reset, and log clearing."""
        parts = [part for part in urlparse(self.path).path.split("/") if part]
        try:
            payload = self._read_json()
            if parts == ["api", "register"]:
                address = int(payload.get("address"))
                if "value" not in payload:
                    raise FaultRuleError("value is required")
                entry = self.server.bank.set_by_address(
                    address,
                    payload["value"],
                    raw=bool(payload.get("raw", False)),
                    code=payload.get("code"),
                    force=True,
                )
                self._send_json(200, {"register": entry})
                return
            if parts == ["api", "rules"]:
                self._send_json(201, {"rule": self.server.monitor.add_rule(payload)})
                return
            if parts == ["api", "rules", "clear"]:
                self.server.monitor.clear_rules()
                self._send_json(200, {"ok": True})
                return
            if (
                len(parts) == 4
                and parts[:2] == ["api", "rules"]
                and parts[3] == "toggle"
            ):
                rule = self.server.monitor.toggle_rule(
                    int(parts[2]), bool(payload.get("enabled", True))
                )
                if rule is None:
                    self._error(404, f"rule {parts[2]} not found")
                else:
                    self._send_json(200, {"rule": rule})
                return
            if parts == ["api", "reset"]:
                self.server.bank.reset()
                self._send_json(200, {"ok": True})
                return
            if parts == ["api", "logs", "clear"]:
                self.server.monitor.clear_events()
                self._send_json(200, {"ok": True})
                return
            self._error(404, "not found")
        except FaultRuleError as err:
            self._error(400, err)
        except (IllegalAddress, IllegalValue) as err:
            self._error(400, err)
        except (TypeError, ValueError) as err:
            self._error(400, f"invalid value: {err}")
        except Exception as err:  # noqa: BLE001 - report, keep serving
            self._error(500, f"{type(err).__name__}: {err}")

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        """Delete one fault rule."""
        parts = [part for part in urlparse(self.path).path.split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "rules"]:
            try:
                rule_id = int(parts[2])
            except ValueError:
                self._error(400, "invalid rule id")
                return
            if self.server.monitor.delete_rule(rule_id):
                self._send_json(200, {"ok": True})
            else:
                self._error(404, f"rule {rule_id} not found")
            return
        self._error(404, "not found")


class TestHTTPServer(ThreadingHTTPServer):
    """HTTP server exposing the register editor, fault rules, and log."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        bank: RegisterBank,
        monitor: Monitor,
        map_path: Path,
        coverage: str,
        modbus_port: int,
        slave: int,
    ) -> None:
        super().__init__(address, TestHTTPHandler)
        self.bank = bank
        self.monitor = monitor
        self.map_path = map_path
        self.coverage = coverage
        self.modbus_port = modbus_port
        self.slave = slave

    def state(self) -> dict:
        """Return everything the page needs for one refresh."""
        return {
            "map": str(self.map_path),
            "coverage": self.coverage,
            "modbus_port": self.modbus_port,
            "slave": self.slave,
            "server_time": time.strftime("%H:%M:%S"),
            "registers": self.bank.snapshot(),
            "rules": self.monitor.rules(),
        }


def start_live_thread(bank: RegisterBank, interval: float = 2.0) -> threading.Thread:
    """Drift the seeded values so dashboards move."""
    started = time.monotonic()

    def run() -> None:
        while True:
            time.sleep(interval)
            elapsed = time.monotonic() - started
            for code, signal in LIVE_SIGNALS.items():
                bank.set_physical(code, signal(elapsed))
            if bank.has_code("pv_total_power"):
                pv_total = sum(
                    bank.raw_of(code) or 0
                    for code in ("pv1_power", "pv2_power")
                    if bank.has_code(code)
                )
                bank.set_physical("pv_total_power", pv_total)

    thread = threading.Thread(target=run, name="live-values", daemon=True)
    thread.start()
    return thread


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command line options."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument(
        "--port", type=int, default=1502, help="TCP port (default 1502; 502 needs root)"
    )
    parser.add_argument(
        "--map", type=Path, default=DEFAULT_MAP, help=f"register map JSON (default {DEFAULT_MAP})"
    )
    parser.add_argument(
        "--slave",
        type=int,
        default=0,
        help="unit id to answer, 0 = any (default 0; real device uses 160)",
    )
    parser.add_argument("--live", action="store_true", help="drift values every 2 s")
    parser.add_argument(
        "--verify-code",
        default=VERIFY_CODE_DEFAULT,
        help=f"code accepted at 0x045C (default {VERIFY_CODE_DEFAULT})",
    )
    parser.add_argument(
        "--firmware-version",
        default=None,
        help="ASCII firmware version served at 0x2763 (e.g. 1.2; default empty)",
    )
    parser.add_argument(
        "--http-host",
        default="127.0.0.1",
        help="test UI bind address (default 127.0.0.1)",
    )
    parser.add_argument(
        "--http-port",
        type=int,
        default=None,
        help="test UI port (default: Modbus port + 100)",
    )
    parser.add_argument(
        "--no-http",
        action="store_true",
        help="disable the browser test page",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="only log startup/shutdown")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the fake server until interrupted."""
    args = parse_args(argv)
    if not args.map.is_file():
        print(f"register map not found: {args.map}", file=sys.stderr)
        return 2

    defs, ranges = load_map(args.map)
    code = str(args.verify_code).strip()
    if len(code) != 6 or not code.isdigit():
        print("--verify-code must be exactly 6 digits", file=sys.stderr)
        return 2
    bank = RegisterBank(
        defs,
        ranges,
        verify_code=code,
        firmware_version=args.firmware_version,
    )
    monitor = Monitor()

    RequestHandler.bank = bank
    RequestHandler.monitor = monitor
    RequestHandler.slave = args.slave
    RequestHandler.verbose = not args.quiet

    try:
        server = FakeModbusServer((args.host, args.port), RequestHandler)
    except OSError as exc:
        print(f"cannot listen on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1

    http_server: TestHTTPServer | None = None
    http_port = args.http_port
    if http_port is None:
        http_port = args.port + 100 if args.port <= 65435 else 0
    if not args.no_http:
        try:
            http_server = TestHTTPServer(
                (args.http_host, http_port),
                bank=bank,
                monitor=monitor,
                map_path=args.map,
                coverage=bank.coverage(),
                modbus_port=args.port,
                slave=args.slave,
            )
        except OSError as exc:
            print(
                f"test UI disabled: cannot listen on {args.http_host}:{http_port}: {exc}",
                file=sys.stderr,
            )

    print(f"map      {args.map} ({len(defs)} registers)")
    print(f"serving  {bank.coverage()}")
    print(f"listen   {args.host}:{args.port}  unit={'any' if not args.slave else args.slave}")
    print(f"mode     {'live values' if args.live else 'static'}")
    if http_server is not None:
        print(f"test UI  http://{args.http_host}:{http_server.server_address[1]}/")
    print("HA       Modbus TCP, host 127.0.0.1, port %d, slave 160" % args.port)
    print("Ctrl+C to stop", flush=True)

    if args.live:
        start_live_thread(bank)

    if http_server is not None:
        threading.Thread(
            target=http_server.serve_forever,
            kwargs={"poll_interval": 0.2},
            name="test-ui",
            daemon=True,
        ).start()

    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        if http_server is not None:
            http_server.shutdown()
            http_server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
