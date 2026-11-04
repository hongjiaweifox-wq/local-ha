"""Conow Local — Modbus RTU integration for CONOW energy devices."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, LOGGER, PLATFORMS, platforms_for_map
from .coordinator import ConowLocalCoordinator
from .map_router import MAP_V2
from .panel import panel_map
from .panel.panel_api import async_register_local_panel
from .panel.panel_coordinator import (
    async_setup_panel_coordinator,
    async_shutdown_panel_coordinator,
)
from .panel.panel_entities import panel_unique_code
from .register_map import get_entities


def _entity_unique_ids(entry: ConfigEntry, map_version: str) -> set[str]:
    """Return the unique IDs the selected map owns for this entry."""
    if map_version == MAP_V2:
        taken = {
            "switch": {entity.code for entity in get_entities("switch")},
            "binary_sensor": {
                entity.code for entity in get_entities("binary_sensor")
            },
            "sensor": {
                entity.code
                for platform in ("sensor", "number")
                for entity in get_entities(platform)
            },
        }
        ids: set[str] = set()
        for register in panel_map.get_registers():
            if register.boolean and register.writable:
                # Mirrors switch.py: overlapping codes get the panel_ prefix.
                code = panel_unique_code(register, taken["switch"])
                ids.add(f"{entry.entry_id}_{code}")
            elif register.is_time:
                ids.add(f"{entry.entry_id}_{register.code}")
            elif register.boolean:
                code = panel_unique_code(register, taken["binary_sensor"])
                ids.add(f"{entry.entry_id}_{code}")
            else:
                code = panel_unique_code(register, taken["sensor"])
                ids.add(f"{entry.entry_id}_{code}")
        return ids
    return {
        f"{entry.entry_id}_{entity.code}"
        for platform in PLATFORMS
        for entity in get_entities(platform)
    }


def _prune_stale_entities(
    hass: HomeAssistant, entry: ConfigEntry, map_version: str
) -> None:
    """Remove registry entries that belong to the map that is not active.

    Without this, switching maps leaves the other map's entities behind as
    unavailable "restored" entities, which looks like both maps are loaded.
    """
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    keep = _entity_unique_ids(entry, map_version)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id not in keep:
            LOGGER.debug(
                "Map %s: removing stale entity %s",
                map_version,
                registry_entry.entity_id,
            )
            registry.async_remove(registry_entry.entity_id)


type ConowLocalConfigEntry = ConfigEntry[ConowLocalCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Conow Local."""
    # pymodbus logs each timeout as ERROR; conow_local already retries internally.
    logging.getLogger("pymodbus").setLevel(logging.WARNING)
    await async_register_local_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConowLocalConfigEntry) -> bool:
    """Set up a Modbus RTU config entry."""
    coordinator = ConowLocalCoordinator(hass, entry)
    # Select the map before the first poll: exactly one of registers.json and
    # panel_registers.json is active for this entry.
    await coordinator.async_probe_map_version()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    # Exactly one map is active for this entry; drop the other map's registry
    # entries so they do not linger as unavailable entities.
    _prune_stale_entities(hass, entry, coordinator.map_version)
    # The finalized map is only safe on firmware that speaks its addresses.
    # Everything else keeps the v1 entities from registers.json.
    if coordinator.map_version == MAP_V2:
        # Shared by the switch and time platforms, and stopped again on unload.
        await async_setup_panel_coordinator(hass, entry, coordinator)
    else:
        LOGGER.info(
            "Panel disabled for %s: firmware does not select panel_registers.json",
            entry.title,
        )
    await hass.config_entries.async_forward_entry_setups(
        entry, platforms_for_map(coordinator.map_version)
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConowLocalConfigEntry) -> bool:
    """Unload Conow Local platforms."""
    coordinator = entry.runtime_data
    platforms = (
        platforms_for_map(coordinator.map_version)
        if coordinator is not None
        else list(PLATFORMS)
    )
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok:
        await async_shutdown_panel_coordinator(hass, entry.entry_id)
        if coordinator is not None:
            await hass.async_add_executor_job(coordinator.shutdown)
    return unload_ok
