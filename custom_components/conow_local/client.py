"""CONOW Balcony Solar Storage — Modbus RTU/TCP client."""

from __future__ import annotations

import logging
import struct
import time

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


def _write_register_request_frame(slave: int, address: int, value: int) -> bytes:
    """Build FC 0x06 write single register request frame."""
    payload = struct.pack(">HH", address, value & 0xFFFF)
    return _build_rtu_frame(slave, 0x06, payload)


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


def _write_register_request_tcp_frame(slave: int, address: int, value: int) -> bytes:
    """Build FC 0x06 write single register TCP request (indicative TX log)."""
    return _build_tcp_frame(0, slave, 0x06, struct.pack(">HH", address, value & 0xFFFF))


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
    ) -> None:
        """Initialize client: TCP when host is given, RTU serial otherwise.

        Serial defaults to 38400 8N1; TCP targets an RS-485↔Ethernet adapter
        or the device's own Ethernet port.
        """
        self._slave = slave
        self._mode = MODBUS_MODE_TCP if host is not None else MODBUS_MODE_RTU
        self._port = port
        self._host = host
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
                if response is None:
                    raise ConowModbusError("No response from device")
                if response.isError():
                    raise ConowModbusError(str(response))
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

    def write_register(self, address: int, value: int) -> None:
        """Write single holding register (FC 0x06) with retry."""
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._flush_input_buffer()
                if self._mode == MODBUS_MODE_TCP:
                    tx_frame = _write_register_request_tcp_frame(self._slave, address, value)
                else:
                    tx_frame = _write_register_request_frame(self._slave, address, value)
                _LOGGER.info(
                    "Modbus write TX (FC 0x06): %s",
                    _format_rtu_hex(tx_frame),
                )
                response = self._client.write_register(
                    address,
                    value,
                    device_id=self._slave,
                )
                if response is None:
                    raise ConowModbusError("No response from device")
                if response.isError():
                    raise ConowModbusError(str(response))
                # FC 0x06 normal response echoes the request PDU (8 bytes).
                _LOGGER.info(
                    "Modbus write OK: slave=%s addr=%s value=%s; expected RX echo: %s",
                    self._slave,
                    address,
                    value,
                    _format_rtu_hex(tx_frame),
                )
                return
            except (ModbusException, ConowModbusError, OSError) as exc:
                last_error = exc
                _LOGGER.debug(
                    "Write failed (attempt %s/%s) addr=%s: %s",
                    attempt,
                    MAX_RETRIES,
                    address,
                    exc,
                )
                if attempt < MAX_RETRIES:
                    self._reconnect_after_error()
        if self._mode == MODBUS_MODE_TCP:
            err_frame = _write_register_request_tcp_frame(self._slave, address, value)
        else:
            err_frame = _write_register_request_frame(self._slave, address, value)
        _LOGGER.error(
            "Modbus write failed: slave=%s endpoint=%s addr=%s value=%s TX=%s err=%s",
            self._slave,
            self._endpoint,
            address,
            value,
            _format_rtu_hex(err_frame),
            last_error,
        )
        raise ConowModbusError(
            f"Write failed after {MAX_RETRIES} attempts: {last_error}"
        ) from last_error

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
                if response is None:
                    raise ConowModbusError("No response from device")
                if response.isError():
                    raise ConowModbusError(str(response))
                _LOGGER.info(
                    "Modbus write OK: slave=%s addr=%s count=%s values=%s",
                    self._slave,
                    address,
                    len(values),
                    values,
                )
                return
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
) -> None:
    """Verify Modbus connectivity by reading a register both maps implement."""
    address, count = CONNECTION_PROBE
    with ConowModbusClient(
        port, host=host, tcp_port=tcp_port, slave=slave, baudrate=baudrate
    ) as client:
        client.read_holding_registers(address, count)


def probe_direct_connection(
    host: str,
    *,
    tcp_port: int = DEFAULT_TCP_PORT,
    slave: int = DEFAULT_SLAVE,
    verify_code: str,
) -> None:
    """Verify a direct TCP link by writing the challenge code.

    The all-in-one machine requires the dynamic 8-character hexadecimal code
    shown by the device to be written to holding registers 0x2701–0x2702
    (9985–9986, uint32, high word first).  The code refreshes every 120 s over
    TCP until verification succeeds.  The write itself is the first Modbus
    request: a normal FC 0x10 response means the device accepted the code,
    while an error response or missing reply is treated as verification
    failure.
    """
    words = encode_verify_code(verify_code)
    with ConowModbusClient(host=host, tcp_port=tcp_port, slave=slave) as client:
        try:
            client.write_registers(VERIFY_CODE_START, words, retries=1)
        except ConowModbusError as err:
            raise ConowVerificationError(
                f"Verification code rejected: {err}"
            ) from err
