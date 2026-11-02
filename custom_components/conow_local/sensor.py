"""Modbus sensor entities."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ConowLocalCoordinator
from .entity_factory import (
    build_device_info,
    build_sensor_description,
    register_for_entity,
)
from .map_router import MAP_V2
from .panel import panel_map
from .panel.panel_coordinator import ConowPanelCoordinator, get_panel_coordinator
from .panel.panel_entities import (
    build_panel_sensor_description,
    is_panel_sensor,
    panel_unique_code,
)
from .register_map import EntityDef, get_entities


class ConowModbusSensor(CoordinatorEntity[ConowLocalCoordinator], SensorEntity):
    """Sensor backed by a Modbus monitoring register."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ConowLocalCoordinator,
        entry: ConfigEntry,
        entity: EntityDef,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self._register_name = entity.register
        register = register_for_entity(entity)
        self.entity_description = build_sensor_description(entity, register)
        self._attr_unique_id = f"{entry.entry_id}_{entity.code}"
        self._attr_device_info = build_device_info(coordinator.hass, entry)

    @property
    def native_value(self) -> float | int | None:
        """Return sensor value."""
        return self.coordinator.get_register_value("monitoring", self._register_name)


class ConowPanelSensor(CoordinatorEntity[ConowPanelCoordinator], SensorEntity):
    """Read-only register from the October panel map."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ConowPanelCoordinator,
        entry: ConfigEntry,
        register: panel_map.PanelRegister,
        unique_code: str,
    ) -> None:
        """Initialize the panel-backed sensor."""
        super().__init__(coordinator)
        self._register = register
        self.entity_description = build_panel_sensor_description(register)
        self._attr_unique_id = f"{entry.entry_id}_{unique_code}"
        self._attr_device_info = build_device_info(coordinator.hass, entry)

    @property
    def native_value(self) -> Any:
        """Return the decoded register value."""
        data = (self.coordinator.data or {}).get(self._register.code) or {}
        if self._register.values:
            # Enum registers expose the mapped label, matching the options.
            return data.get("display") or None
        if self._register.dtype == "string":
            return data.get("raw") or None
        return data.get("value")


async def _async_add_panel_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one sensor per read-only register of the October map."""
    coordinator = get_panel_coordinator(hass, entry.entry_id)
    if coordinator is None:
        return
    v1_codes = {
        entity.code for entity in (*get_entities("sensor"), *get_entities("number"))
    }
    async_add_entities(
        ConowPanelSensor(
            coordinator,
            entry,
            register,
            unique_code=panel_unique_code(register, v1_codes),
        )
        for register in panel_map.get_registers()
        if is_panel_sensor(register)
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Modbus sensors from the active register map."""
    coordinator: ConowLocalCoordinator = entry.runtime_data
    if coordinator.map_version != MAP_V2:
        async_add_entities(
            ConowModbusSensor(coordinator, entry, entity_def)
            for entity_def in get_entities("sensor")
        )
        return
    await _async_add_panel_sensors(hass, entry, async_add_entities)
