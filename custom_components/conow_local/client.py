"""CONOW Balcony Solar Storage — Modbus RTU/TCP client."""

from __future__ import annotations

import logging
import struct
import time
from typing import Any

from pymodbus.client import ModbusSerialClient, ModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import DEFAULT_BAUDRATE, DEFAULT_SLAVE, DEFAULT_TCP_PORT, MODBUS_MODE_RTU, MODBUS_MODE_TCP
from .maps.registry import CONNECTION_PROBE

_LOGGER = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_INTERVAL_S = 0.5
INTER_FRAME_DELAY_S = 0.15
POST_WRITE_DELAY_S = 0.3
DEFAULT_TIMEOUT_S = 2.0


def _crc16_modbus(data: bytes) -> int:
    """Compute Modbus RTU CRC-16."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _build_rtu_frame(slave: int, function_code: int, payload: bytes) -> bytes:
    """Build a Modbus RTU frame (PDU + CRC, little-endian CRC)."""
    pdu = bytes([slave & 0xFF, function_code & 0xFF]) + payload
    crc = _crc16_modbus(pdu)
    return pdu + struct.pack("<H", crc)


def _format_rtu_hex(frame: bytes) -> str:
    """Format RTU bytes as upper-case hex groups."""
    return " ".join(f"{b:02X}" for b in frame)


def _read_holding_request_frame(slave: int, address: int, count: int) -> bytes:
    """Build FC 0x03 read holding registers request frame."""
    payload = struct.pack(">HH", address, count)
    return _build_rtu_frame(slave, 0x03, payload)


def _read_holding_response_frame(slave: int, registers: list[int]) -> bytes:
    """Build FC 0x03 read holding registers response frame (for logging)."""
    payload = bytes([len(registers) * 2 & 0xFF])
    for value in registers:
        payload += struct.pack(">H", value & 0xFFFF)
    return _build_rtu_frame(slave, 0x03, payload)


def _write_registers_request_frame(
    slave: int, address: int, values: list[int]
) -> bytes:
    """Build FC 0x10 write multiple registers request frame."""
    payload = struct.pack(">HHB", address, len(values), len(values) * 2)
    payload += b"".join(struct.pack(">H", value & 0xFFFF) for value in values)
    return _build_rtu_frame(slave, 0x10, payload)


def _build_tcp_frame(transaction_id: int, slave: int, function_code: int, payload: bytes) -> bytes:
    """Build a Modbus TCP frame (MBAP header + PDU, no CRC)."""
    header = struct.pack(">HHHB", transaction_id, 0, len(payload) + 2, slave & 0xFF)
    return header + bytes([function_code & 0xFF]) + payload


def _read_holding_request_tcp_frame(slave: int, address: int, count: int) -> bytes:
    """Build FC 0x03 read holding registers TCP request (indicative TX log)."""
    return _build_tcp_frame(0, slave, 0x03, struct.pack(">HH", address, count))


def _write_registers_request_tcp_frame(
    slave: int, address: int, values: list[int]
) -> bytes:
    """Build FC 0x10 write multiple registers TCP request (indicative TX log)."""
    payload = struct.pack(">HHB", address, len(values), len(values) * 2)
    payload += b"".join(struct.pack(">H", value & 0xFFFF) for value in values)
    return _build_tcp_frame(0, slave, 0x10, payload)


class ConowModbusError(Exception):
    """Raised when Modbus communication fails."""


class ConowConnectError(ConowModbusError):
    """Raised when the transport link cannot be opened at all.

    Kept apart from a failed request so the frontend can tell "the device is
    not reachable" (wrong IP, closed port, other subnet) from "the device
    answered and rejected what we sent".
    """


class ConowVerificationError(ConowModbusError):
    """Raised when the direct TCP verification code is rejected."""


# Modbus exception codes (function code | 0x80 in the reply).
EXCEPTION_NAMES = {
    1: "illegal function",
    2: "illegal data address",
    3: "illegal data value",
    4: "slave device failure",
    5: "acknowledge",
    6: "slave device busy",
    8: "memory parity error",
    10: "gateway path unavailable",
    11: "gateway target failed to respond",
}


class ConowExceptionResponseError(ConowModbusError):
    """The device answered with a Modbus exception response.

    The link is healthy — the device heard the request and refused it.  Such a
    reply must not be retried and must not drop the connection: resending the
    same request cannot change the answer, and on a direct-TCP machine a
    reconnect also has to re-send the verification code.
    """

    def __init__(self, function_code: int, exception_code: int) -> None:
        """Store the exception reply for callers and logs."""
        self.function_code = function_code
        self.exception_code = exception_code
        super().__init__(
            f"Modbus exception 0x{function_code:02X}/0x{exception_code:02X} "
            f"({EXCEPTION_NAMES.get(exception_code, 'unknown exception')})"
        )


def _raise_for_response(response: Any, function_code: int) -> None:
    """Raise the right error for a missing or exception response."""
    if response is None:
        raise ConowModbusError("No response from device")
    if response.isError():
        raise ConowExceptionResponseError(
            int(getattr(response, "function_code", function_code | 0x80)),
            int(getattr(response, "exception_code", 0)),
        )


VERIFY_CODE_START = 0x2701  # uint32 challenge, two holding registers (9985-9986)
VERIFY_CODE_LENGTH = 8


def encode_verify_code(code: str | int) -> list[int]:
    """Encode an 8-character hexadecimal code as uint32 words (high word first)."""
    text = str(code).strip()
    if len(text) != VERIFY_CODE_LENGTH or any(
        char not in "0123456789abcdefABCDEF" for char in text
    ):
        raise ConowModbusError(
            "Verification code must be exactly 8 hexadecimal characters"
        )
    value = int(text, 16)
    return [(value >> 16) & 0xFFFF, value & 0xFFFF]


class ConowModbusClient:
    """Local Modbus client (RTU serial or TCP) for CONOW devices."""

    def __init__(
        self,
        port: str | None = None,
        *,
        host: str | None = None,
        tcp_port: int = DEFAULT_TCP_PORT,
        slave: int = DEFAULT_SLAVE,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT_S,
        verify_code: str | None = None,
    ) -> None:
        """Initialize client: TCP when host is given, RTU serial otherwise.

        Serial defaults to 38400 8N1; TCP targets an RS-485↔Ethernet adapter
        or the device's own Ethernet port.  ``verify_code`` is the direct-TCP
        challenge; when set, it is written lazily — after the machine refuses
        a request — instead of before every link is used.
        """
        self._slave = slave
        self._mode = MODBUS_MODE_TCP if host is not None else MODBUS_MODE_RTU
        self._port = port
        self._host = host
        self._verify_code = (
            str(verify_code).strip()
            if verify_code and self._mode == MODBUS_MODE_TCP
            else None
        )
        # True once the code is known to be active or its verification has
        # already been attempted on this link; no second automatic write.
        self._verify_attempted = self._verify_code is None
        if self._mode == MODBUS_MODE_TCP:
            self._tcp_port = tcp_port
            # Log label mirrors what the adapter sees on the RS-485 side.
            self._endpoint = f"{host}:{tcp_port}"
            self._client: ModbusSerialClient | ModbusTcpClient = ModbusTcpClient(
                host=host,
                port=tcp_port,
                timeout=timeout,
                retries=0,
            )
        else:
            if port is None:
                raise ConowModbusError("RTU mode requires a serial port")
            self._tcp_port = DEFAULT_TCP_PORT
            self._endpoint = port
            self._client = ModbusSerialClient(
                port=port,
                framer="rtu",
                baudrate=baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=timeout,
                retries=0,
            )

    @property
    def mode(self) -> str:
        """Return the connection mode ('rtu' or 'tcp')."""
        return self._mode

    @property
    def connected(self) -> bool:
        """Whether the underlying socket/serial port is still open."""
        return bool(getattr(self._client, "connected", False))

    def mark_verified(self) -> None:
        """Record that the challenge code is already active on this link."""
        self._verify_attempted = True

    def _verify_after_refusal(self, error: ConowExceptionResponseError) -> bool:
        """Write the challenge code after an unverified link refuses a request.

        A direct-TCP machine reports the refusal itself: it answers the first
        request on a fresh, unverified link with a Modbus exception response.
        Reacting to that reply keeps the code out of the traffic entirely for a
        machine that does not need it, while a machine that does need it still
        gets exactly one write per link.  The caller retries its request once
        when this returns ``True``.

        Raises ``ConowVerificationError`` when the machine rejects the code, so
        the failure is reported as a code problem instead of a generic refusal.
        """
        if self._verify_attempted or not self._verify_code:
            return False
        # Only one automatic attempt per link: a rejected code must not be
        # rewritten on every poll.
        self._verify_attempted = True
        _LOGGER.info(
            "Device refused %s before verification; sending the stored "
            "verification code and retrying",
            error,
        )
        try:
            response = self._client.write_registers(
                VERIFY_CODE_START,
                encode_verify_code(self._verify_code),
                device_id=self._slave,
            )
            _raise_for_response(response, 0x10)
        except ConowExceptionResponseError as exc:
            message = (
                f"Verification code rejected ({exc}); update it under "
                "Settings > Devices & services > Conow Local > Configure"
            )
            _LOGGER.warning(message)
            raise ConowVerificationError(message) from exc
        except (ModbusException, ConowModbusError, OSError) as exc:
            message = f"Verification code write failed: {exc}"
            _LOGGER.warning(message)
            raise ConowVerificationError(message) from exc
        _LOGGER.info(
            "Modbus write OK: slave=%s addr=%s values=[verification code]",
            self._slave,
            VERIFY_CODE_START,
        )
        return True

    def connect(self) -> None:
        """Open the connection."""
        if not self._client.connect():
            if self._mode == MODBUS_MODE_TCP:
                raise ConowConnectError(
                    f"Failed to connect to {self._host}:{self._tcp_port}"
                )
            raise ConowConnectError(f"Failed to open serial port {self._port}")
        self._flush_input_buffer()

    def _flush_input_buffer(self) -> None:
        """Discard stale bytes before the next Modbus frame (serial only)."""
        serial_port = getattr(self._client, "socket", None)
        if serial_port is not None and hasattr(serial_port, "reset_input_buffer"):
            serial_port.reset_input_buffer()

    def _reconnect_after_error(self) -> None:
        """Close and reopen the connection after I/O failure."""
        self._client.close()
        time.sleep(RETRY_INTERVAL_S)
        if not self._client.connect():
            if self._mode == MODBUS_MODE_TCP:
                raise ConowConnectError(
                    f"Failed to reconnect to {self._host}:{self._tcp_port}"
                )
            raise ConowConnectError(f"Failed to reopen serial port {self._port}")
        self._flush_input_buffer()

    def close(self) -> None:
        """Close the serial connection."""
        self._client.close()

    def __enter__(self) -> ConowModbusClient:
        """Connect on context entry."""
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        """Disconnect on context exit."""
        self.close()

    def read_holding_registers(
        self, address: int, count: int, *, retries: int = MAX_RETRIES
    ) -> list[int]:
        """Read holding registers (FC 0x03) with retry.

        Set ``retries=1`` for optional probes where a slow failure should not
        delay setup and where the caller has a safe fallback.
        """
        attempts = max(1, retries)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self._flush_input_buffer()
                if self._mode == MODBUS_MODE_TCP:
                    tx_frame = _read_holding_request_tcp_frame(self._slave, address, count)
                else:
                    tx_frame = _read_holding_request_frame(self._slave, address, count)
                _LOGGER.debug(
                    "Modbus read TX (FC 0x03): %s",
                    _format_rtu_hex(tx_frame),
                )
                response = self._client.read_holding_registers(
                    address,
                    count=count,
                    device_id=self._slave,
                )
                _raise_for_response(response, 0x03)
                registers = list(response.registers)
                rx_frame = _read_holding_response_frame(self._slave, registers)
                _LOGGER.debug(
                    "Modbus read OK addr=%s count=%s RX=%s registers=%s",
                    address,
                    count,
                    _format_rtu_hex(rx_frame),
                    registers,
                )
                return registers
            except ConowExceptionResponseError as exc:
                _LOGGER.warning(
                    "Modbus read refused addr=%s count=%s: %s", address, count, exc
                )
                if self._verify_after_refusal(exc):
                    # The refusal was the machine's way of asking for the
                    # challenge code; the link is verified now.
                    return self.read_holding_registers(
                        address, count, retries=max(1, attempts - attempt)
                    )
                raise
            except (ModbusException, ConowModbusError, OSError) as exc:
                last_error = exc
                _LOGGER.debug(
                    "Read failed (attempt %s/%s) addr=%s: %s",
                    attempt,
                    attempts,
                    address,
                    exc,
                )
                if attempt < attempts:
                    self._reconnect_after_error()
        if self._mode == MODBUS_MODE_TCP:
            msg = (
                f"Read failed after {attempts} attempts (slave={self._slave}, "
                f"tcp={self._host}:{self._tcp_port}): device sent no Modbus "
                f"reply — check Enable External Control / ModBus RTU, the "
                f"TCP endpoint (server IP / port {DEFAULT_TCP_PORT}) and its "
                f"serial settings (slave 160 / 38400 8N1)"
            )
        else:
            msg = (
                f"Read failed after {attempts} attempts (slave={self._slave}, "
                f"port={self._port}): device sent no Modbus reply — check "
                f"Enable External Control / ModBus RTU, RS-485 wiring, "
                f"and slave/baud (160 / 38400)"
            )
        raise ConowModbusError(msg) from last_error

    def write_registers(
        self, address: int, values: list[int], *, retries: int = MAX_RETRIES
    ) -> None:
        """Write consecutive holding registers (FC 0x10) with retry.

        Devices that reject single-register writes for a coupled group require
        this function code; 32-bit values are written as one atomic frame.
        Set ``retries=1`` for one-shot writes such as challenge verification,
        where repeating a rejected value could lock the device.
        """
        if not values:
            raise ConowModbusError("write_registers requires at least one value")
        attempts = max(1, retries)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self._flush_input_buffer()
                if self._mode == MODBUS_MODE_TCP:
                    tx_frame = _write_registers_request_tcp_frame(
                        self._slave, address, values
                    )
                else:
                    tx_frame = _write_registers_request_frame(
                        self._slave, address, values
                    )
                _LOGGER.info("Modbus write TX (FC 0x10): %s", _format_rtu_hex(tx_frame))
                response = self._client.write_registers(
                    address,
                    values,
                    device_id=self._slave,
                )
                _raise_for_response(response, 0x10)
                _LOGGER.info(
                    "Modbus write OK: slave=%s addr=%s count=%s values=%s",
                    self._slave,
                    address,
                    len(values),
                    values,
                )
                return
            except ConowExceptionResponseError as exc:
                _LOGGER.warning(
                    "Modbus write refused addr=%s count=%s values=%s: %s",
                    address,
                    len(values),
                    values,
                    exc,
                )
                if self._verify_after_refusal(exc):
                    # The refusal was the machine's way of asking for the
                    # challenge code; the link is verified now.
                    return self.write_registers(
                        address, values, retries=max(1, attempts - attempt)
                    )
                raise
            except (ModbusException, ConowModbusError, OSError) as exc:
                last_error = exc
                _LOGGER.debug(
                    "Write failed (attempt %s/%s) addr=%s: %s",
                    attempt,
                    attempts,
                    address,
                    exc,
                )
                if attempt < attempts:
                    self._reconnect_after_error()
        _LOGGER.error(
            "Modbus FC 0x10 write failed: slave=%s endpoint=%s addr=%s values=%s err=%s",
            self._slave,
            self._endpoint,
            address,
            values,
            last_error,
        )
        raise ConowModbusError(
            f"Write failed after {attempts} attempt{'s' if attempts != 1 else ''}: "
            f"{last_error}"
        ) from last_error

def probe_connection(
    port: str | None = None,
    *,
    host: str | None = None,
    tcp_port: int = DEFAULT_TCP_PORT,
    slave: int = DEFAULT_SLAVE,
    baudrate: int = DEFAULT_BAUDRATE,
    keep_open: bool = False,
) -> ConowModbusClient | None:
    """Verify Modbus connectivity by reading a register both maps implement.

    With ``keep_open`` the verified client is returned instead of being
    closed, so the entry being created can poll it instead of opening a
    second connection.
    """
    address, count = CONNECTION_PROBE
    client = ConowModbusClient(
        port, host=host, tcp_port=tcp_port, slave=slave, baudrate=baudrate
    )
    try:
        client.connect()
        client.read_holding_registers(address, count)
    except Exception:
        client.close()
        raise
    if keep_open:
        return client
    client.close()
    return None


def probe_direct_connection(
    host: str,
    *,
    tcp_port: int = DEFAULT_TCP_PORT,
    slave: int = DEFAULT_SLAVE,
    verify_code: str,
    keep_open: bool = False,
) -> ConowModbusClient | None:
    """Verify a direct TCP link by writing the challenge code.

    The all-in-one machine requires the dynamic 8-character hexadecimal code
    shown by the device to be written to holding registers 0x2701–0x2702
    (9985–9986, uint32, high word first).  The code refreshes every 120 s over
    TCP until verification succeeds.  The write itself is the first Modbus
    request: a normal FC 0x10 response means the device accepted the code,
    while an error response or missing reply is treated as verification
    failure.

    With ``keep_open`` the verified client is returned instead of being
    closed: the entry being created adopts it, so the machine sees one
    connection and one code write, not two.
    """
    words = encode_verify_code(verify_code)
    client = ConowModbusClient(host=host, tcp_port=tcp_port, slave=slave)
    try:
        client.connect()
    except Exception:
        client.close()
        raise
    try:
        client.write_registers(VERIFY_CODE_START, words, retries=1)
    except ConowModbusError as err:
        client.close()
        raise ConowVerificationError(
            f"Verification code rejected: {err}"
        ) from err
    if keep_open:
        return client
    client.close()
    return None
