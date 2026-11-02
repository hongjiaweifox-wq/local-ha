"""Modbus data update coordinator."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .panel import panel_map
from .client import INTER_FRAME_DELAY_S, POST_WRITE_DELAY_S, ConowModbusClient, ConowModbusError
from .map_router import (
    FIRMWARE_VERSION_ADDRESS,
    FIRMWARE_VERSION_REGISTERS,
    MAP_V1,
    MAP_V2,
    format_version,
    parse_firmware_version,
    select_map,
)
from .register_map import DEFAULT_BAUDRATE
from .const import (
    CONF_MODBUS_BAUDRATE,
    CONF_MODBUS_HOST,
    CONF_MODBUS_MODE,
    CONF_MODBUS_PORT,
    CONF_MODBUS_SLAVE,
    CONF_MODBUS_TCP_PORT,
    DEFAULT_TCP_PORT,
    DOMAIN,
    LOGGER,
    MODBUS_POLL_INTERVAL,
    MODBUS_TCP_MODES,
)

_T = TypeVar("_T")


class ConowLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll CONOW device over Modbus RTU or TCP."""

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
        """Close the serial client after an I/O error."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _run_locked(self, operation: Callable[[ConowModbusClient], _T]) -> _T:
        """Run a Modbus operation with exclusive serial port access."""
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

    def _probe_firmware_version(self) -> tuple[int, ...] | None:
        """Read the 4-byte firmware version used for register-map routing."""

        def _operation(client: ConowModbusClient) -> list[int]:
            return client.read_holding_registers(
                FIRMWARE_VERSION_ADDRESS,
                FIRMWARE_VERSION_REGISTERS,
                retries=2,
            )

        try:
            words = self._run_locked(_operation)
        except ConowModbusError as err:
            LOGGER.info(
                "Map: firmware probe at 0x%04X failed (%s); keeping registers.json",
                FIRMWARE_VERSION_ADDRESS,
                err,
            )
            return None
        return parse_firmware_version(words)

    async def async_probe_map_version(self) -> str:
        """Probe the device and store the selected register map id."""
        version = await self.hass.async_add_executor_job(self._probe_firmware_version)
        self.firmware_version = version
        self.map_version = select_map(version)
        if self.map_version == MAP_V2:
            # v2 is panel-first: the panel coordinator owns device polling.
            # Leaving the v1 interval running would read v1 addresses on v2
            # firmware, so exactly one map stays active.
            self.update_interval = None
        LOGGER.info(
            "Map: firmware=%s -> %s (%s)",
            format_version(version) or "unknown",
            self.map_version,
            "panel_registers.json" if self.map_version != MAP_V1 else "registers.json",
        )
        return self.map_version

    def _read_device(self) -> dict[str, Any]:
        """Blocking Modbus read executed in executor."""
        if self.map_version == MAP_V2:
            # The panel coordinator reads the v2 blocks; never mix maps here.
            return {}
        return self._run_locked(lambda client: client.read_all())

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from device."""
        try:
            return await self.hass.async_add_executor_job(self._read_device)
        except ConowModbusError as err:
            raise UpdateFailed(str(err)) from err

    def _read_panel_blocks(self) -> dict[str, list[int] | None]:
        """Read the October map blocks for the grouping panel."""

        def _operation(client: ConowModbusClient) -> dict[str, list[int] | None]:
            blocks: dict[str, list[int] | None] = {}
            for index, (block, (start, count)) in enumerate(
                panel_map.get_block_spans().items()
            ):
                if index:
                    time.sleep(INTER_FRAME_DELAY_S)
                try:
                    blocks[block] = client.read_holding_registers(start, count)
                except ConowModbusError:
                    LOGGER.debug("Panel: block %s read failed", block)
                    blocks[block] = None
            return blocks

        return self._run_locked(_operation)

    async def async_read_panel_blocks(self) -> dict[str, list[int] | None]:
        """Read the grouping-panel map without touching coordinator data."""
        return await self.hass.async_add_executor_job(self._read_panel_blocks)

    def _write_panel_ops(self, ops: list[tuple[int, list[int]]]) -> None:
        """Write grouping-panel registers under the shared Modbus lock."""

        def _operation(client: ConowModbusClient) -> None:
            for index, (address, words) in enumerate(ops):
                if index:
                    time.sleep(INTER_FRAME_DELAY_S)
                if len(words) == 1:
                    client.write_register(address, words[0])
                else:
                    client.write_registers(address, words)
                time.sleep(POST_WRITE_DELAY_S)

        self._run_locked(_operation)

    async def async_write_panel_ops(self, ops: list[tuple[int, list[int]]]) -> None:
        """Write grouping-panel registers without disturbing entity polling."""
        await self.hass.async_add_executor_job(self._write_panel_ops, ops)

    def _write_and_read(
        self, write_op: Callable[[ConowModbusClient], None]
    ) -> dict[str, Any]:
        """Write then read back in one locked serial session."""

        def _operation(client: ConowModbusClient) -> dict[str, Any]:
            LOGGER.debug("Coordinator: executing Modbus write then read-back")
            write_op(client)
            time.sleep(POST_WRITE_DELAY_S)
            LOGGER.debug("Coordinator: read-back after write (monitoring + control)")
            data = client.read_all()
            control = data.get("control", {})
            direction = control.get("charge_discharge_direction", {})
            power = control.get("battery_target_power", {})
            cutoff = control.get("battery_cutoff_soc", {})
            LOGGER.debug(
                "Coordinator: read-back control snapshot direction=%s power=%s cutoff_soc=%s",
                direction.get("raw"),
                power.get("raw"),
                cutoff.get("raw"),
            )
            return data

        return self._run_locked(_operation)

    async def _async_write_and_update(
        self, write_op: Callable[[ConowModbusClient], None]
    ) -> None:
        """Write to device and push fresh register data to entities."""
        data = await self.hass.async_add_executor_job(self._write_and_read, write_op)
        self.async_set_updated_data(data)

    async def async_write_register_raw(self, name: str, raw_value: int) -> None:
        """Write a control register and refresh coordinator data."""
        await self._async_write_and_update(
            lambda client: client.write_named_register_raw(name, raw_value)
        )

    async def async_write_register(self, name: str, physical_value: float) -> None:
        """Write a control register using physical units."""
        await self._async_write_and_update(
            lambda client: client.write_named_register(name, physical_value)
        )

    async def async_write_force_mode(
        self, direction: int, power_w: int, cutoff_soc: int
    ) -> None:
        """Write forced charge/discharge command sequence."""
        await self._async_write_and_update(
            lambda client: client.write_force_mode(direction, power_w, cutoff_soc)
        )

    def get_register_value(self, block: str, name: str) -> float | None:
        """Return decoded physical value for a register name."""
        data = self.data or {}
        section = data.get(block, {})
        entry = section.get(name)
        if not entry:
            return None
        return entry.get("value")

    def get_status_bit(self, name: str) -> bool | None:
        """Return a parsed system status bit."""
        data = self.data or {}
        status = data.get("monitoring", {}).get("system_status")
        if not status:
            return None
        bits = status.get("bits", {})
        return bits.get(name)
