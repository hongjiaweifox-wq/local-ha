"""Unified Modbus data update coordinator.

One coordinator polls the active register map (v1 or v2) and exposes a flat
``{code: {raw, value, display}}`` snapshot to both the HA entities and the
grouping panel.  v1 keeps the 5 s interval, v2 polls every 30 s; both work
over RTU and TCP.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..maps import model as map_model
from ..client import (
    INTER_FRAME_DELAY_S,
    POST_WRITE_DELAY_S,
    ConowModbusClient,
    ConowModbusError,
)
from ..const import (
    CONF_MODBUS_BAUDRATE,
    CONF_MODBUS_HOST,
    CONF_MODBUS_MODE,
    CONF_MODBUS_PORT,
    CONF_MODBUS_SLAVE,
    CONF_MODBUS_TCP_PORT,
    DEFAULT_BAUDRATE,
    DEFAULT_TCP_PORT,
    DOMAIN,
    LOGGER,
    MODBUS_POLL_INTERVAL,
    MODBUS_TCP_MODES,
)
from ..maps.registry import (
    FIRMWARE_VERSION_ADDRESS,
    FIRMWARE_VERSION_REGISTERS,
    MAP_V1,
    MAP_V2,
    format_version,
    map_source,
    parse_firmware_version,
    select_map,
)

_T = TypeVar("_T")

PANEL_POLL_INTERVAL_S = 30


def read_map_blocks(
    client: ConowModbusClient, map_version: str
) -> dict[str, list[int] | None]:
    """Read every block of one map with one connected client."""
    blocks: dict[str, list[int] | None] = {}
    for index, (block, (start, count)) in enumerate(
        map_model.get_block_spans(map_version).items()
    ):
        if index:
            time.sleep(INTER_FRAME_DELAY_S)
        try:
            blocks[block] = client.read_holding_registers(start, count)
        except ConowModbusError:
            LOGGER.debug("Map %s: block %s read failed", map_version, block)
            blocks[block] = None
    return blocks


def decode_map_blocks(
    blocks: dict[str, list[int] | None], map_version: str
) -> dict[str, dict[str, Any]]:
    """Decode the successfully read blocks into one flat snapshot."""
    decoded: dict[str, dict[str, Any]] = {}
    for block, words in blocks.items():
        if words is not None:
            decoded.update(map_model.decode_block(block, words, map_version))
    return decoded


def write_register_ops(
    client: ConowModbusClient, ops: list[tuple[int, list[int]]]
) -> None:
    """Write ``(address, words)`` operations back to back."""
    for index, (address, words) in enumerate(ops):
        if index:
            time.sleep(INTER_FRAME_DELAY_S)
        if len(words) == 1:
            client.write_register(address, words[0])
        else:
            client.write_registers(address, words)
        time.sleep(POST_WRITE_DELAY_S)


class ConowLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a CONOW device over Modbus RTU or TCP."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        self.entry = entry
        self.mode = entry.data.get(CONF_MODBUS_MODE, "rtu")
        self.slave = entry.data[CONF_MODBUS_SLAVE]
        if self.mode in MODBUS_TCP_MODES:
            self.host = entry.data[CONF_MODBUS_HOST]
            self.tcp_port = entry.data.get(CONF_MODBUS_TCP_PORT, DEFAULT_TCP_PORT)
            self.port = None
            self.baudrate = None
        else:
            self.host = None
            self.port = entry.data[CONF_MODBUS_PORT]
            self.baudrate = entry.data[CONF_MODBUS_BAUDRATE]
        self._lock = threading.Lock()
        self._client: ConowModbusClient | None = None
        # v1 is the default; async_probe_map_version() may upgrade this.
        self.map_version = MAP_V1
        self.firmware_version: tuple[int, ...] | None = None
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=MODBUS_POLL_INTERVAL),
        )

    def _connect(self) -> ConowModbusClient:
        """Open or reuse the Modbus client (serial or TCP)."""
        if self._client is None:
            client = ConowModbusClient(
                self.port,
                host=self.host,
                tcp_port=self.tcp_port if self.host is not None else DEFAULT_TCP_PORT,
                slave=self.slave,
                baudrate=self.baudrate or DEFAULT_BAUDRATE,
            )
            client.connect()
            self._client = client
        return self._client

    def _reset_client(self) -> None:
        """Close the client after an I/O error."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _run_locked(self, operation: Callable[[ConowModbusClient], _T]) -> _T:
        """Run a Modbus operation with exclusive port access."""
        with self._lock:
            try:
                return operation(self._connect())
            except ConowModbusError:
                self._reset_client()
                raise

    def shutdown(self) -> None:
        """Release the serial port."""
        with self._lock:
            self._reset_client()

    def _probe_firmware_version(self) -> tuple[tuple[int, ...] | None, bool]:
        """Read the firmware register and report whether the probe succeeded.

        Any reply selects the v2 map, so the decoded version is only used for
        logging.  Some machines expose a single word at 0x274E, so a failed
        two-word read is retried with one word before giving up.
        """
        last_error: ConowModbusError | None = None
        for count in (FIRMWARE_VERSION_REGISTERS, 1):
            try:
                words = self._run_locked(
                    lambda client, count=count: client.read_holding_registers(
                        FIRMWARE_VERSION_ADDRESS,
                        count,
                        retries=2,
                    )
                )
            except ConowModbusError as err:
                last_error = err
                continue
            return parse_firmware_version(words), True

        LOGGER.info(
            "Map: firmware probe at 0x%04X failed (%s); keeping %s",
            FIRMWARE_VERSION_ADDRESS,
            last_error,
            map_source(MAP_V1),
        )
        return None, False

    async def async_probe_map_version(self) -> str:
        """Probe the device and store the selected register map id."""
        version, probe_ok = await self.hass.async_add_executor_job(
            self._probe_firmware_version
        )
        self.firmware_version = version
        self.map_version = select_map(probe_ok)
        self.update_interval = timedelta(
            seconds=(
                PANEL_POLL_INTERVAL_S
                if self.map_version == MAP_V2
                else MODBUS_POLL_INTERVAL
            )
        )
        LOGGER.info(
            "Map: firmware=%s -> %s (%s)",
            format_version(version) or "unknown",
            self.map_version,
            map_source(self.map_version),
        )
        return self.map_version

    def _read_snapshot(self) -> dict[str, dict[str, Any]]:
        """Blocking read of every block of the active map."""
        return self._run_locked(
            lambda client: decode_map_blocks(
                read_map_blocks(client, self.map_version), self.map_version
            )
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device."""
        try:
            data = await self.hass.async_add_executor_job(self._read_snapshot)
        except ConowModbusError as err:
            raise UpdateFailed(str(err)) from err
        if not data:
            raise UpdateFailed(
                f"{map_source(self.map_version)} is not readable on this device"
            )
        return data

    async def async_read_snapshot(self) -> dict[str, dict[str, Any]]:
        """Read the active map without touching coordinator data.

        Used by the grouping panel so a manual refresh does not overwrite the
        polled entity data.
        """
        return await self.hass.async_add_executor_job(self._read_snapshot)

    def _write_panel_ops(self, ops: list[tuple[int, list[int]]]) -> None:
        """Write grouping-panel registers under the shared Modbus lock."""
        self._run_locked(lambda client: write_register_ops(client, ops))

    async def async_write_panel_ops(self, ops: list[tuple[int, list[int]]]) -> None:
        """Write grouping-panel registers without disturbing entity polling."""
        await self.hass.async_add_executor_job(self._write_panel_ops, ops)

    def _entry(self, code: str) -> dict[str, Any]:
        return (self.data or {}).get(code) or {}

    def get_raw(self, code: str) -> int | str | None:
        """Return the raw register value of a code."""
        return self._entry(code).get("raw")

    def get_value(self, code: str) -> float | str | None:
        """Return the decoded physical value of a code."""
        return self._entry(code).get("value")

    def get_display(self, code: str) -> str:
        """Return the panel display string of a code."""
        return self._entry(code).get("display", "")
