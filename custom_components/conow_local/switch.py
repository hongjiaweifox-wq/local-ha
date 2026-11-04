"""Modbus switch entities."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import ConowLocalCoordinator
from .entity_factory import build_device_info, build_switch_description
from .map_router import MAP_V2
from .panel import panel_map
from .panel.panel_coordinator import ConowPanelCoordinator, get_panel_coordinator
from .panel.panel_guard import async_refuse_device_write
from .register_map import EntityDef, get_entities


class ConowModbusSwitch(CoordinatorEntity[ConowLocalCoordinator], SwitchEntity):
    """Writable on/off Modbus register."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ConowLocalCoordinator,
        entry: ConfigEntry,
        entity: EntityDef,
    ) -> None:
        """Initialize switch entity."""
        super().__init__(coordinator)
        self._register_name = entity.register
        self.entity_description = build_switch_description(entity)
        self._attr_unique_id = f"{entry.entry_id}_{entity.code}"
        self._attr_device_info = build_device_info(coordinator.hass, entry)

    @property
    def is_on(self) -> bool | None:
        """Return switch state."""
        value = self.coordinator.get_register_value("control", self._register_name)
        if value is None:
            return None
        return bool(int(value))

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn switch on."""
        await self.coordinator.async_write_register_raw(self._register_name, 1)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn switch off."""
        await self.coordinator.async_write_register_raw(self._register_name, 0)


class ConowPanelSwitch(CoordinatorEntity[ConowPanelCoordinator], SwitchEntity):
    """On/off register from the finalized panel map."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ConowPanelCoordinator,
        entry: ConfigEntry,
        register: panel_map.PanelRegister,
        unique_code: str | None = None,
    ) -> None:
        """Initialize the panel-backed switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._register = register
        self._attr_unique_id = f"{entry.entry_id}_{unique_code or register.code}"
        self._attr_name = register.name
        self._attr_device_info = build_device_info(coordinator.hass, entry)

    @property
    def is_on(self) -> bool | None:
        """Return the register's raw 0/1 state."""
        raw = (self.coordinator.data or {}).get(self._register.code, {}).get("raw")
        if not isinstance(raw, int):
            return None
        return bool(raw)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Write 1 to the register."""
        await self._async_write(1)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Write 0 to the register."""
        await self._async_write(0)

    async def _async_write(self, value: int) -> None:
        """Refuse single-register writes from the device page."""
        async_refuse_device_write(self.coordinator.hass, self._entry)

async def _async_add_panel_switches(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one switch per on/off register of the finalized map (TCP only)."""
    coordinator = get_panel_coordinator(hass, entry.entry_id)
    if coordinator is None:
        return
    v1_codes = {entity.code for entity in get_entities("switch")}
    registers = [
        register
        for register in panel_map.get_registers()
        if register.boolean and register.writable
    ]
    async_add_entities(
        ConowPanelSwitch(
            coordinator,
            entry,
            register,
            # These codes also exist in the v1 map, so keep unique_ids apart;
            # panel_functions maps the "panel_" prefix back to the register.
            unique_code=(
                f"panel_{register.code}" if register.code in v1_codes else None
            ),
        )
        for register in registers
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Modbus switch entities from registers.json and the panel map."""
    coordinator: ConowLocalCoordinator = entry.runtime_data
    if coordinator.map_version != MAP_V2:
        entities = [
            ConowModbusSwitch(coordinator, entry, entity_def)
            for entity_def in get_entities("switch")
        ]
        async_add_entities(entities)
    await _async_add_panel_switches(hass, entry, async_add_entities)
