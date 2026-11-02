"""Coordinator that polls the October map used by the grouping panel."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import panel_map
from ..client import ConowModbusError
from ..const import CONF_MODBUS_MODE, DOMAIN, LOGGER, MODBUS_TCP_MODES
from ..coordinator import ConowLocalCoordinator
from ..map_router import MAP_V1, MAP_V2

PANEL_POLL_INTERVAL_S = 30
PANEL_COORDINATORS = f"{DOMAIN}_panel_coordinators"


class ConowPanelCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Poll ``panel_registers.json`` blocks for panel-backed entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        main: ConowLocalCoordinator,
    ) -> None:
        """Initialize the panel coordinator."""
        self.entry = entry
        self.main = main
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_panel_{entry.entry_id}",
            update_interval=timedelta(seconds=PANEL_POLL_INTERVAL_S),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Read every panel block and decode it into ``{code: {...}}``."""
        blocks = await self.main.async_read_panel_blocks()
        decoded: dict[str, dict[str, Any]] = {}
        for block, words in blocks.items():
            if words is not None:
                decoded.update(panel_map.decode_block(block, words))
        if not decoded:
            raise UpdateFailed("October map is not readable on this device")
        return decoded


async def async_setup_panel_coordinator(
    hass: HomeAssistant,
    entry: ConfigEntry,
    main: ConowLocalCoordinator,
) -> ConowPanelCoordinator | None:
    """Create and refresh the entry's shared panel coordinator.

    Only TCP entries whose firmware selected the v2 map expose the October
    map; everything else keeps the regular v1 entities and has no
    panel-backed entities.
    """
    if getattr(main, "map_version", MAP_V1) != MAP_V2:
        LOGGER.info(
            "Panel map skipped for %s: firmware does not select panel_registers.json",
            entry.title,
        )
        return None
    if entry.data.get(CONF_MODBUS_MODE) not in MODBUS_TCP_MODES:
        return None
    coordinator = ConowPanelCoordinator(hass, entry, main)
    try:
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryNotReady, ConowModbusError, OSError):
        LOGGER.info(
            "Panel map is not readable for %s; skipping panel entities", entry.title
        )
        await coordinator.async_shutdown()
        return None
    hass.data.setdefault(PANEL_COORDINATORS, {})[entry.entry_id] = coordinator
    return coordinator


def get_panel_coordinator(
    hass: HomeAssistant, entry_id: str
) -> ConowPanelCoordinator | None:
    """Return the entry's shared panel coordinator, if it was set up."""
    return hass.data.get(PANEL_COORDINATORS, {}).get(entry_id)


async def async_shutdown_panel_coordinator(
    hass: HomeAssistant, entry_id: str
) -> None:
    """Stop and forget the entry's shared panel coordinator."""
    coordinator = hass.data.get(PANEL_COORDINATORS, {}).pop(entry_id, None)
    if coordinator is not None:
        await coordinator.async_shutdown()
