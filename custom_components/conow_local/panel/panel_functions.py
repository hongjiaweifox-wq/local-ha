"""Build the read model for the Conow Local grouping panel.

The panel consumes the same unified map model and entity specs as the HA
device page.  Loaded entries read through the main coordinator; entries that
are not loaded may be inspected over a short-lived TCP connection (never a
second serial handle).
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..maps import model as map_model
from ..client import ConowModbusClient, ConowModbusError
from ..const import (
    CONF_MODBUS_HOST,
    CONF_MODBUS_MODE,
    CONF_MODBUS_SLAVE,
    CONF_MODBUS_TCP_PORT,
    DEFAULT_TCP_PORT,
    DOMAIN,
    LOGGER,
    MODBUS_TCP_MODES,
)
from ..device.coordinator import (
    ConowLocalCoordinator,
    decode_map_blocks,
    read_map_blocks,
    write_register_ops,
)
from ..maps.entity_model import panel_code_map
from ..maps.registry import (
    FIRMWARE_VERSION_ADDRESS,
    FIRMWARE_VERSION_REGISTERS,
    MAP_PATHS,
    MAP_V1,
    PANEL_MAP_MIN_FIRMWARE,
    format_version,
    map_source,
    parse_firmware_version,
    select_map,
)


def _control_kind(register: map_model.PanelRegister) -> str:
    """Return the editor type the panel should render for this register."""
    if register.is_time:
        return "time"
    if register.boolean:
        return "switch"
    if register.values:
        return "enum"
    if register.dtype == "string":
        return "text"
    return "number"


def _enum_raw(register: map_model.PanelRegister, value: Any) -> int | None:
    """Resolve a submitted enum value (raw number or translated label)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    for raw, label in (register.values or {}).items():
        if label == value:
            return raw
    return None


def _device_name(entry, device_entry) -> str:
    return (
        device_entry.name_by_user
        or device_entry.name
        or entry.title
        or entry.entry_id
    )


# finalized-map codes that back a differently named v1 entity. Clicking the
# panel row opens the entity's more-info dialog, so the alias only covers
# registers whose meaning is identical across both maps.
ENTITY_CODE_ALIASES = {
    "ac_charge_power_limit": "grid_charge_power_limit",
    "ac_discharge_power_limit": "battery_discharge_power_limit",
    "charge_discharge_cutoff_soc": "battery_cutoff_soc",
    "system_soc": "battery_soc",
    "device_fault_code": "fault_code",
    "bypass_power": "backup_load_power",
}


def _entity_code_map(
    hass: HomeAssistant, entry_id: str, device_entry, map_version: str
) -> dict[str, str]:
    """Map register/entity codes to the entity_id backing them on this device."""
    registry = er.async_get(hass)
    if device_entry is not None:
        entries = er.async_entries_for_device(registry, device_entry.id)
    else:
        entries = er.async_entries_for_config_entry(registry, entry_id)
    unique_prefix = f"{entry_id}_"
    by_unique = {
        (item.unique_id or "")[len(unique_prefix) :]: item.entity_id
        for item in entries
        if (item.unique_id or "").startswith(unique_prefix)
    }
    mapping: dict[str, str] = {}
    for code, unique_code in panel_code_map(map_version).items():
        entity_id = by_unique.get(unique_code)
        if entity_id is not None:
            mapping[code] = entity_id
    return mapping


def _entity_id_for(register: map_model.PanelRegister, mapping: dict[str, str]) -> str | None:
    """Return the entity_id for a panel register, if one exists."""
    if register.code in mapping:
        return mapping[register.code]
    alias = ENTITY_CODE_ALIASES.get(register.code)
    return mapping.get(alias) if alias else None


def _serialize_group(
    group: map_model.PanelGroup,
    decoded: dict[str, dict[str, Any]] | None = None,
    entities: dict[str, str] | None = None,
    *,
    map_version: str,
) -> dict[str, Any]:
    decoded = decoded or {}
    entities = entities or {}
    index = map_model.get_register_index(map_version)
    members: list[dict[str, Any]] = []
    for code in group.members:
        register = index[code]
        value = decoded.get(code, {})
        if register.bits:
            # The register is a bitmask; expose the individual bits as
            # read-only boolean rows instead of the raw number.
            raw = value.get("raw")
            known = isinstance(raw, int)
            for bit in register.bits:
                is_on = known and bool(raw & (1 << bit.bit))
                members.append(
                    {
                        "code": bit.code,
                        "name": bit.name,
                        "address": register.address,
                        "address_hex": register.address_hex,
                        "dtype": register.dtype,
                        "length": 1,
                        "writable": False,
                        "unit": "",
                        "scale": 1,
                        "values": None,
                        "note": "",
                        "control": "bit",
                        "device_class": bit.device_class,
                        "bounds": None,
                        "raw": (1 if is_on else 0) if known else None,
                        "value": is_on if known else None,
                        "display": ("1" if is_on else "0") if known else "",
                        "entity_id": entities.get(bit.code),
                    }
                )
            continue
        members.append(
            {
                "code": register.code,
                "name": register.name,
                "address": register.address,
                "address_hex": register.address_hex,
                "dtype": register.dtype,
                "length": register.length,
                "writable": register.writable,
                "unit": register.unit,
                "scale": register.scale,
                "values": register.values,
                "note": register.note,
                "control": _control_kind(register),
                "bounds": map_model.numeric_bounds(register, decoded),
                "raw": value.get("raw"),
                "value": value.get("value"),
                "display": value.get("display", ""),
                "entity_id": _entity_id_for(register, entities),
            }
        )
    return {
        "id": group.id,
        "label": group.label,
        "icon": group.icon,
        "order": group.order,
        "atomic": group.atomic,
        "span": {
            "start": group.span_start,
            "end": group.span_end,
            "start_hex": f"0x{group.span_start:04X}",
            "end_hex": f"0x{group.span_end:04X}",
            "registers": group.span_registers,
        },
        "note": group.note,
        "count_register": group.count_register or None,
        "members": members,
        "subgroups": [
            {
                "label": subgroup.label,
                "key": subgroup.key or None,
                "members": list(subgroup.members),
            }
            for subgroup in group.subgroups
        ],
    }


def build_panel_map(map_version: str | None = None) -> dict[str, Any]:
    """Return the static grouped map of one map version (no device values).

    Without a known map version the result is empty: the frontend requests the
    map again once the device state tells it whether this is v1 or v2, so it
    never flashes the wrong map's groups.
    """
    if map_version not in MAP_PATHS:
        return {"map": {}, "groups": {}}
    return {
        "map": map_model.get_map_meta(map_version),
        "groups": {
            group.id: _serialize_group(group, map_version=map_version)
            for group in map_model.get_groups(map_version)
        },
    }


def get_panel_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    """List config entries that can be inspected through the grouping panel."""
    device_registry = dr.async_get(hass)
    devices: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.entry_id)}
        )
        coordinator = getattr(entry, "runtime_data", None)
        loaded = entry.state is ConfigEntryState.LOADED
        devices.append(
            {
                "device_id": device_entry.id if device_entry else entry.entry_id,
                "entry_id": entry.entry_id,
                "name": _device_name(entry, device_entry) if device_entry else entry.title,
                "online": bool(
                    loaded
                    and coordinator is not None
                    and coordinator.last_update_success
                ),
                "loaded": loaded,
                "mode": entry.data.get(CONF_MODBUS_MODE, "rtu"),
                "slave": entry.data.get(CONF_MODBUS_SLAVE),
            }
        )
    devices.sort(key=lambda item: item["name"].lower())
    return devices


def _entry_for_id(hass: HomeAssistant, device_id: str):
    """Resolve a panel ``device_id`` (HA device id or entry id) to an entry."""
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == device_id:
            return entry
        if device_entry and (DOMAIN, entry.entry_id) in device_entry.identifiers:
            return entry
    return None


def _probe_map_version(
    client: ConowModbusClient,
) -> tuple[str, tuple[int, ...] | None]:
    """Probe firmware and return the selected map plus decoded version.

    Any reply from the firmware register selects v2, including current
    machines that answer 0x0000.  A single-word read is retried because some
    firmware exposes only 0x274E.
    """
    words: list[int] | None = None
    for count in (FIRMWARE_VERSION_REGISTERS, 1):
        try:
            words = client.read_holding_registers(
                FIRMWARE_VERSION_ADDRESS,
                count,
                retries=2,
            )
        except ConowModbusError:
            continue
        break
    if words is None:
        return MAP_V1, None
    return select_map(True), parse_firmware_version(words)


def _merge_contiguous(
    ops: list[tuple[int, list[int]]],
) -> tuple[int, list[int]] | None:
    """Merge per-register writes into one frame when the addresses touch."""
    start = ops[0][0]
    expected = start
    words: list[int] = []
    for address, chunk in ops:
        if address != expected:
            return None
        words.extend(chunk)
        expected += len(chunk)
    return start, words


MAX_WRITE_REGISTERS = 123  # FC 0x10 quantity limit


def plan_group_writes(
    group: map_model.PanelGroup,
    values: dict[str, Any],
    live: dict[str, dict[str, Any]] | None = None,
    *,
    map_version: str,
) -> list[tuple[int, list[int]]]:
    """Validate a group submission and return ``(address, words)`` writes.

    A group is sent as one atomic FC 0x10 frame whenever its writable
    registers are contiguous; groups with gaps fall back to per-register
    frames written back to back.  ``live`` holds the decoded device state so
    limits that depend on another register (safety SoC, hardware power
    capability) can be enforced before anything is sent.
    """
    index = map_model.get_register_index(map_version)
    registers = [index[code] for code in group.members if index[code].writable]
    if not registers:
        raise ValueError(f"Group {group.id} has no writable registers")
    missing = [register.code for register in registers if register.code not in values]
    if missing:
        raise ValueError("Missing value for " + ", ".join(missing))
    if live is not None:
        # The cutoff SoC limits depend on the direction being written in this
        # same group, so validate against the submitted value, not the stale
        # reading.
        direction = index.get("charge_discharge_direction")
        submitted = values.get("charge_discharge_direction")
        if direction is not None and submitted is not None:
            raw = _enum_raw(direction, submitted)
            if raw is not None:
                live = dict(live)
                live["charge_discharge_direction"] = {"value": float(raw)}
    ops: list[tuple[int, list[int]]] = []
    for register in registers:
        value = values[register.code]
        bounds = map_model.numeric_bounds(register, live)
        if bounds is not None and not register.values and not register.is_time:
            try:
                physical = float(value)
            except (TypeError, ValueError):
                physical = None
            if physical is not None:
                low, high, _step = bounds
                if not low <= physical <= high:
                    raise ValueError(
                        f"{register.code}: {physical:g} is outside the allowed "
                        f"range {low:g}–{high:g}"
                    )
        ops.append((register.address, map_model.encode_value(register, value)))
    if len(ops) > 1:
        merged = _merge_contiguous(ops)
        if merged is not None and len(merged[1]) <= MAX_WRITE_REGISTERS:
            return [merged]
    return ops


def _write_ops_direct(entry, ops: list[tuple[int, list[int]]]) -> None:
    """Write through a short-lived TCP client when the entry is not loaded."""
    if entry.data.get(CONF_MODBUS_MODE) not in MODBUS_TCP_MODES:
        raise ConowModbusError("RTU entry must finish setup before writing")
    host = entry.data[CONF_MODBUS_HOST]
    tcp_port = entry.data.get(CONF_MODBUS_TCP_PORT, DEFAULT_TCP_PORT)
    slave = entry.data[CONF_MODBUS_SLAVE]
    with ConowModbusClient(host=host, tcp_port=tcp_port, slave=slave) as client:
        write_register_ops(client, ops)


async def async_write_panel_group(
    hass: HomeAssistant,
    device_id: str,
    group_id: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Write one group atomically and return the refreshed panel state."""
    entry = _entry_for_id(hass, device_id)
    if entry is None:
        raise LookupError(f"No {DOMAIN} entry for {device_id}")

    coordinator: ConowLocalCoordinator | None = getattr(entry, "runtime_data", None)
    loaded = entry.state is ConfigEntryState.LOADED and coordinator is not None
    live: dict[str, dict[str, Any]] = {}
    if loaded:
        map_version = coordinator.map_version
        live = dict(coordinator.data or {})
    else:
        try:
            map_version, _firmware, live = await hass.async_add_executor_job(
                _read_blocks_direct, entry
            )
        except (ConowModbusError, OSError):
            map_version, live = MAP_V1, {}

    group = map_model.get_group(group_id, map_version)
    if group is None:
        raise LookupError(f"Unknown group {group_id}")
    ops = plan_group_writes(group, values, live, map_version=map_version)

    if loaded:
        await coordinator.async_write_panel_ops(ops)
    else:
        await hass.async_add_executor_job(_write_ops_direct, entry, ops)

    LOGGER.info(
        "Panel: wrote group %s (%s register frames) to %s",
        group_id,
        len(ops),
        entry.entry_id,
    )
    return await async_build_panel_state(hass, device_id)


def _read_blocks_direct(entry) -> tuple[str, tuple[int, ...] | None, dict[str, dict[str, Any]]]:
    """Open a short-lived TCP client for entries the coordinator does not own."""
    if entry.data.get(CONF_MODBUS_MODE) not in MODBUS_TCP_MODES:
        # Never open a second handle on the serial port.
        return MAP_V1, None, {}
    host = entry.data[CONF_MODBUS_HOST]
    tcp_port = entry.data.get(CONF_MODBUS_TCP_PORT, DEFAULT_TCP_PORT)
    slave = entry.data[CONF_MODBUS_SLAVE]
    with ConowModbusClient(host=host, tcp_port=tcp_port, slave=slave) as client:
        map_version, version = _probe_map_version(client)
        blocks = read_map_blocks(client, map_version)
        return map_version, version, decode_map_blocks(blocks, map_version)


async def async_build_panel_state(hass: HomeAssistant, device_id: str) -> dict[str, Any]:
    """Read the selected grouped map and serialize the grouped values."""
    device_registry = dr.async_get(hass)
    entry = _entry_for_id(hass, device_id)
    if entry is None:
        raise LookupError(f"No {DOMAIN} entry for {device_id}")
    device_entry = device_registry.async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )

    coordinator: ConowLocalCoordinator | None = getattr(entry, "runtime_data", None)
    loaded = entry.state is ConfigEntryState.LOADED and coordinator is not None
    read_ok = False
    if loaded:
        map_version = coordinator.map_version
        firmware = coordinator.firmware_version
        try:
            decoded = await coordinator.async_read_snapshot()
            read_ok = bool(decoded)
        except (ConowModbusError, OSError):
            LOGGER.debug("Panel: fresh read failed for %s", entry.entry_id)
            decoded = dict(coordinator.data or {})
    else:
        try:
            map_version, firmware, decoded = await hass.async_add_executor_job(
                _read_blocks_direct, entry
            )
            read_ok = bool(decoded)
        except (ConowModbusError, OSError):
            LOGGER.debug("Panel: direct read failed for %s", entry.entry_id)
            map_version, firmware, decoded = MAP_V1, None, {}

    entities = _entity_code_map(hass, entry.entry_id, device_entry, map_version)
    LOGGER.debug(
        "Panel: read %s codes for %s (map=%s, firmware=%s)",
        len(decoded),
        entry.entry_id,
        map_version,
        format_version(firmware) or "unknown",
    )
    map_info = dict(map_model.get_map_meta(map_version))
    map_info.update(
        {
            "selected": map_version,
            "source": map_source(map_version),
            "firmware_version": format_version(firmware),
            "min_firmware": format_version(PANEL_MAP_MIN_FIRMWARE),
        }
    )
    return {
        "device_id": device_id,
        "name": _device_name(entry, device_entry) if device_entry else entry.title,
        "online": bool(
            read_ok
            or (loaded and coordinator.last_update_success)
            or firmware is not None
        ),
        "map_readable": read_ok,
        "map_version": 2 if map_version != MAP_V1 else 1,
        "map_source": map_info["source"],
        "firmware_version": map_info["firmware_version"],
        "min_firmware": map_info["min_firmware"],
        "mode": entry.data.get(CONF_MODBUS_MODE, "rtu"),
        "slave": entry.data.get(CONF_MODBUS_SLAVE),
        "map": map_info,
        "groups": {
            group.id: _serialize_group(
                group, decoded, entities, map_version=map_version
            )
            for group in map_model.get_groups(map_version)
        },
    }
