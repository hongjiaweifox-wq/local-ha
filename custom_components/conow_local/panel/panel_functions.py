"""Build the read model for the Conow Local grouping panel."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from . import panel_map
from ..client import (
    INTER_FRAME_DELAY_S,
    POST_WRITE_DELAY_S,
    ConowModbusClient,
    ConowModbusError,
)
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
from ..map_router import (
    FIRMWARE_VERSION_ADDRESS,
    FIRMWARE_VERSION_REGISTERS,
    MAP_V1,
    MAP_V2,
    PANEL_MAP_MIN_FIRMWARE,
    format_version,
    parse_firmware_version,
    select_map,
)
from .panel_coordinator import get_panel_coordinator


def _control_kind(register: panel_map.PanelRegister) -> str:
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


def _device_name(entry, device_entry) -> str:
    return (
        device_entry.name_by_user
        or device_entry.name
        or entry.title
        or entry.entry_id
    )


# October-map codes that back a differently named v1 entity. Clicking the
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


def _entity_code_map(hass: HomeAssistant, entry_id: str, device_entry) -> dict[str, str]:
    """Map register/entity codes to the entity_id backing them on this device."""
    registry = er.async_get(hass)
    if device_entry is not None:
        entries = er.async_entries_for_device(registry, device_entry.id)
    else:
        prefix = f"{entry_id}_"
        entries = [
            item
            for item in registry.entities.values()
            if (item.unique_id or "").startswith(prefix)
        ]
    prefix = f"{entry_id}_"
    mapping: dict[str, str] = {}
    panel_overrides: dict[str, str] = {}
    for item in entries:
        unique_id = item.unique_id or ""
        if not unique_id.startswith(prefix):
            continue
        code = unique_id[len(prefix) :]
        if code.startswith("status_"):
            # Bit sensors share one status register; they have no panel row.
            continue
        if code.startswith("panel_"):
            # October-map entity whose code also exists in the v1 map; this is
            # the entity that actually points at the panel register.
            panel_overrides[code[len("panel_") :]] = item.entity_id
            continue
        mapping.setdefault(code, item.entity_id)
    mapping.update(panel_overrides)
    return mapping


def _entity_id_for(register: panel_map.PanelRegister, mapping: dict[str, str]) -> str | None:
    """Return the entity_id for a panel register, if one exists."""
    if register.code in mapping:
        return mapping[register.code]
    alias = ENTITY_CODE_ALIASES.get(register.code)
    return mapping.get(alias) if alias else None


def _serialize_group(
    group: panel_map.PanelGroup,
    decoded: dict[str, dict[str, Any]] | None = None,
    entities: dict[str, str] | None = None,
) -> dict[str, Any]:
    decoded = decoded or {}
    entities = entities or {}
    index = panel_map.get_register_index()
    members: list[dict[str, Any]] = []
    for code in group.members:
        register = index[code]
        value = decoded.get(code, {})
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
                "bounds": panel_map.numeric_bounds(register, decoded),
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


def build_panel_map() -> dict[str, Any]:
    """Return the static grouped map (no device values)."""
    return {
        "map": panel_map.get_map_meta(),
        "groups": {
            group.id: _serialize_group(group) for group in panel_map.get_groups()
        },
    }


def get_panel_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    """List config entries that can be inspected through the grouping panel.

    Entries are listed even when the v1 coordinator is not loaded: the panel
    reads the October map independently, so a device that only speaks the new
    protocol can still be inspected.
    """
    device_registry = dr.async_get(hass)
    devices: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.entry_id)}
        )
        coordinator = getattr(entry, "runtime_data", None)
        loaded = entry.state is ConfigEntryState.LOADED
        map_version = getattr(coordinator, "map_version", MAP_V1)
        panel_coordinator = (
            get_panel_coordinator(hass, entry.entry_id)
            if loaded and map_version == MAP_V2
            else None
        )
        # On v2 the main coordinator does not poll, so its last_update_success
        # would stay True forever; the panel coordinator owns device health.
        online_coordinator = panel_coordinator or coordinator
        devices.append(
            {
                "device_id": device_entry.id if device_entry else entry.entry_id,
                "entry_id": entry.entry_id,
                "name": _device_name(entry, device_entry) if device_entry else entry.title,
                "online": bool(
                    loaded
                    and online_coordinator is not None
                    and online_coordinator.last_update_success
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
    """Probe firmware and return the selected map plus decoded version."""
    try:
        words = client.read_holding_registers(
            FIRMWARE_VERSION_ADDRESS,
            FIRMWARE_VERSION_REGISTERS,
            retries=2,
        )
    except ConowModbusError:
        return MAP_V1, None
    version = parse_firmware_version(words)
    return select_map(version), version


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
    group: panel_map.PanelGroup,
    values: dict[str, Any],
    live: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[int, list[int]]]:
    """Validate a group submission and return ``(address, words)`` writes.

    A group is sent as one atomic FC 0x10 frame whenever its writable
    registers are contiguous; groups with gaps fall back to per-register
    frames written back to back.  ``live`` holds the decoded device state so
    limits that depend on another register (safety SoC, hardware power
    capability) can be enforced before anything is sent.
    """
    index = panel_map.get_register_index()
    registers = [index[code] for code in group.members if index[code].writable]
    if not registers:
        raise ValueError(f"Group {group.id} has no writable registers")
    missing = [register.code for register in registers if register.code not in values]
    if missing:
        raise ValueError("Missing value for " + ", ".join(missing))
    ops: list[tuple[int, list[int]]] = []
    for register in registers:
        value = values[register.code]
        bounds = panel_map.numeric_bounds(register, live)
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
        ops.append((register.address, panel_map.encode_value(register, value)))
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
        for index, (address, words) in enumerate(ops):
            if index:
                time.sleep(INTER_FRAME_DELAY_S)
            if len(words) == 1:
                client.write_register(address, words[0])
            else:
                client.write_registers(address, words)
            time.sleep(POST_WRITE_DELAY_S)


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

    coordinator = getattr(entry, "runtime_data", None)
    loaded = entry.state is ConfigEntryState.LOADED and coordinator is not None
    live: dict[str, dict[str, Any]] = {}
    if loaded:
        map_version = getattr(coordinator, "map_version", MAP_V1)
        firmware = getattr(coordinator, "firmware_version", None)
        panel_coordinator = get_panel_coordinator(hass, entry.entry_id)
        live = dict(getattr(panel_coordinator, "data", None) or {})
    else:
        try:
            map_version, firmware, raw_blocks = await hass.async_add_executor_job(
                _read_blocks_direct, entry
            )
        except (ConowModbusError, OSError):
            map_version, firmware, raw_blocks = MAP_V1, None, {}
        for block, words in raw_blocks.items():
            if words is not None:
                live.update(panel_map.decode_block(block, words))
    if map_version != MAP_V2:
        raise ConowModbusError(
            "Grouped panel writes need the October register map "
            f"(firmware >= {format_version(PANEL_MAP_MIN_FIRMWARE)}); "
            f"this device reports {format_version(firmware) or 'an unknown firmware'}"
        )

    group = panel_map.get_group(group_id)
    if group is None:
        raise LookupError(f"Unknown group {group_id}")
    ops = plan_group_writes(group, values, live)

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


def _read_blocks(client: ConowModbusClient) -> dict[str, list[int] | None]:
    """Read every panel block with one connected client."""
    blocks: dict[str, list[int] | None] = {}
    for index, (block, (start, count)) in enumerate(panel_map.get_block_spans().items()):
        if index:
            time.sleep(INTER_FRAME_DELAY_S)
        try:
            blocks[block] = client.read_holding_registers(start, count)
        except ConowModbusError:
            LOGGER.debug("Panel: block %s read failed", block)
            blocks[block] = None
    return blocks


def _read_blocks_direct(
    entry,
) -> tuple[str, tuple[int, ...] | None, dict[str, list[int] | None]]:
    """Open a short-lived TCP client for entries the coordinator does not own."""
    if entry.data.get(CONF_MODBUS_MODE) not in MODBUS_TCP_MODES:
        # Never open a second handle on the serial port.
        return MAP_V1, None, {}
    host = entry.data[CONF_MODBUS_HOST]
    tcp_port = entry.data.get(CONF_MODBUS_TCP_PORT, DEFAULT_TCP_PORT)
    slave = entry.data[CONF_MODBUS_SLAVE]
    with ConowModbusClient(host=host, tcp_port=tcp_port, slave=slave) as client:
        map_version, version = _probe_map_version(client)
        if map_version != MAP_V2:
            return map_version, version, {}
        return map_version, version, _read_blocks(client)


async def async_build_panel_state(hass: HomeAssistant, device_id: str) -> dict[str, Any]:
    """Read the October map and serialize the grouped values for the panel."""
    device_registry = dr.async_get(hass)
    entry = _entry_for_id(hass, device_id)
    if entry is None:
        raise LookupError(f"No {DOMAIN} entry for {device_id}")
    device_entry = device_registry.async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    entities = _entity_code_map(hass, entry.entry_id, device_entry)

    coordinator = getattr(entry, "runtime_data", None)
    loaded = entry.state is ConfigEntryState.LOADED and coordinator is not None
    if loaded:
        map_version = getattr(coordinator, "map_version", MAP_V1)
        firmware = getattr(coordinator, "firmware_version", None)
        raw_blocks = (
            await coordinator.async_read_panel_blocks()
            if map_version == MAP_V2
            else {}
        )
    else:
        try:
            map_version, firmware, raw_blocks = await hass.async_add_executor_job(
                _read_blocks_direct, entry
            )
        except (ConowModbusError, OSError):
            LOGGER.debug("Panel: direct read failed for %s", entry.entry_id)
            map_version, firmware, raw_blocks = MAP_V1, None, {}

    decoded: dict[str, dict[str, Any]] = {}
    for block, words in raw_blocks.items():
        if words is not None:
            decoded.update(panel_map.decode_block(block, words))

    LOGGER.debug(
        "Panel: read %s/%s blocks for %s (map=%s, firmware=%s)",
        sum(1 for words in raw_blocks.values() if words is not None),
        len(raw_blocks),
        entry.entry_id,
        map_version,
        format_version(firmware) or "unknown",
    )
    read_ok = map_version == MAP_V2 and any(
        words is not None for words in raw_blocks.values()
    )
    map_info = dict(panel_map.get_map_meta())
    map_info.update(
        {
            "selected": map_version,
            "source": (
                "panel_registers.json" if map_version == MAP_V2 else "registers.json"
            ),
            "firmware_version": format_version(firmware),
            "min_firmware": format_version(PANEL_MAP_MIN_FIRMWARE),
        }
    )
    return {
        "device_id": device_id,
        "name": _device_name(entry, device_entry) if device_entry else entry.title,
        "online": bool(
            read_ok
            or (
                loaded
                and coordinator is not None
                and coordinator.last_update_success
            )
            or firmware is not None
        ),
        "map_readable": read_ok,
        "map_version": 2 if map_version == MAP_V2 else 1,
        "map_source": map_info["source"],
        "firmware_version": map_info["firmware_version"],
        "min_firmware": map_info["min_firmware"],
        "mode": entry.data.get(CONF_MODBUS_MODE, "rtu"),
        "slave": entry.data.get(CONF_MODBUS_SLAVE),
        "map": map_info,
        "blocks_read": {
            block: words is not None for block, words in raw_blocks.items()
        },
        "groups": (
            {
                group.id: _serialize_group(group, decoded, entities)
                for group in panel_map.get_groups()
            }
            if map_version == MAP_V2
            else {}
        ),
    }
