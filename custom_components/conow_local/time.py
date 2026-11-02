"""Time entities for the HH:MM registers of the October panel map."""

from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity_factory import build_device_info
from .panel import panel_map
from .panel.panel_coordinator import ConowPanelCoordinator, get_panel_coordinator
from .panel.panel_guard import async_refuse_device_write


class ConowPanelTime(CoordinatorEntity[ConowPanelCoordinator], TimeEntity):
    """Schedule register (high byte hour, low byte minute) as a time entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ConowPanelCoordinator,
        entry: ConfigEntry,
        register: panel_map.PanelRegister,
    ) -> None:
        """Initialize time entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._register = register
        self._attr_unique_id = f"{entry.entry_id}_{register.code}"
        self._attr_name = register.name
        self._attr_suggested_object_id = register.code
        self._attr_device_info = build_device_info(coordinator.hass, entry)

    @property
    def native_value(self) -> dt_time | None:
        """Return the current HH:MM value."""
        raw = (self.coordinator.data or {}).get(self._register.code, {}).get("raw")
        if not isinstance(raw, int):
            return None
        hour = (raw >> 8) & 0xFF
        minute = raw & 0xFF
        if hour > 23 or minute > 59:
            return None
        return dt_time(hour=hour, minute=minute)

    async def async_set_value(self, value: dt_time) -> None:
        """Refuse single-register writes from the device page."""
        async_refuse_device_write(self.hass, self._entry)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one time entity per HH:MM register in the panel map."""
    coordinator = get_panel_coordinator(hass, entry.entry_id)
    if coordinator is None:
        # RTU entries have no October map; TCP entries with an unreadable map
        # are skipped as well.
        return
    registers = [register for register in panel_map.get_registers() if register.is_time]
    async_add_entities(
        ConowPanelTime(coordinator, entry, register) for register in registers
    )
