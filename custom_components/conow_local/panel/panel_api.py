"""WebSocket API and custom panel for the Conow Local grouping view."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.frontend import (
    add_extra_js_url,
    async_panel_exists,
    remove_extra_js_url,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from . import panel_map
from ..client import ConowModbusError
from ..const import DOMAIN, LOGGER, PANEL_URL_PATH
from .panel_functions import (
    async_build_panel_state,
    async_write_panel_group,
    build_panel_map,
    get_panel_devices,
)

URL_BASE = "/conow_local_panel_static"
PANEL_WEBCOMPONENT = "conow-local-panel"
PANEL_STATIC_VERSION = "46"
PANEL_SCRIPT_URL = f"{URL_BASE}/conow-local-panel.js?v={PANEL_STATIC_VERSION}"
NOTIFY_SCRIPT_URL = f"{URL_BASE}/conow-local-notify.js?v={PANEL_STATIC_VERSION}"
PANEL_SIDEBAR_ENABLED = True
SIDEBAR_TITLES = {
    "de": "Conow Local Gruppen",
    "nl": "Conow Local groepen",
    "zh-Hans": "Conow Local 分组",
}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/get_panel_devices"}
)
@websocket_api.async_response
async def websocket_get_panel_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Return Conow Local devices available for the grouping panel."""
    connection.send_result(msg["id"], {"devices": get_panel_devices(hass)})


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/get_panel_map"}
)
@websocket_api.async_response
async def websocket_get_panel_map(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Return the grouped October map without device values."""
    result = await hass.async_add_executor_job(build_panel_map)
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/get_panel_functions",
        vol.Required("device_id"): str,
    }
)
@websocket_api.async_response
async def websocket_get_panel_functions(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Return the grouped October-map read model for one device."""
    try:
        state = await async_build_panel_state(hass, msg["device_id"])
    except LookupError:
        connection.send_error(msg["id"], "not_found", "Device not found")
        return
    connection.send_result(msg["id"], state)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_panel_group",
        vol.Required("device_id"): str,
        vol.Required("group_id"): str,
        vol.Required("values"): {str: vol.Any(int, float, str)},
    }
)
@websocket_api.async_response
async def websocket_set_panel_group(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Write every writable register of a group in one request."""
    try:
        state = await async_write_panel_group(
            hass, msg["device_id"], msg["group_id"], msg["values"]
        )
    except LookupError as err:
        connection.send_error(msg["id"], "not_found", str(err))
        return
    except ValueError as err:
        connection.send_error(msg["id"], "invalid_value", str(err))
        return
    except (ConowModbusError, OSError) as err:
        connection.send_error(msg["id"], "write_failed", str(err))
        return
    state["source"] = "local"
    connection.send_result(msg["id"], state)


@callback
def _register_websocket_api(hass: HomeAssistant) -> None:
    if hass.data.get(f"{DOMAIN}_panel_ws_registered"):
        return
    websocket_api.async_register_command(hass, websocket_get_panel_devices)
    websocket_api.async_register_command(hass, websocket_get_panel_map)
    websocket_api.async_register_command(hass, websocket_get_panel_functions)
    websocket_api.async_register_command(hass, websocket_set_panel_group)
    hass.data[f"{DOMAIN}_panel_ws_registered"] = True


async def async_register_local_panel(hass: HomeAssistant) -> None:
    """Register the grouping panel, its static assets and websocket API."""
    # Parse and validate the map off the event loop so WS calls stay cheap.
    try:
        await hass.async_add_executor_job(panel_map.preload)
    except (OSError, ValueError, KeyError) as err:
        LOGGER.error("Panel: cannot load panel_registers.json: %s", err)
    _register_websocket_api(hass)

    frontend_dir = Path(__file__).parent / "frontend"
    if not hass.data.get(f"{DOMAIN}_panel_static_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(frontend_dir), cache_headers=False)]
        )
        hass.data[f"{DOMAIN}_panel_static_registered"] = True

    # Adds the "Open panel" action to the device-page write-guard toast.
    previous_js = hass.data.get(f"{DOMAIN}_notify_js")
    if previous_js != NOTIFY_SCRIPT_URL:
        if previous_js:
            remove_extra_js_url(hass, previous_js)
        add_extra_js_url(hass, NOTIFY_SCRIPT_URL)
        hass.data[f"{DOMAIN}_notify_js"] = NOTIFY_SCRIPT_URL

    if hass.data.get(f"{DOMAIN}_panel_registered"):
        return

    if PANEL_SIDEBAR_ENABLED and not async_panel_exists(hass, PANEL_URL_PATH):
        language = str(hass.config.language or "")
        sidebar_title = (
            SIDEBAR_TITLES.get(language)
            or SIDEBAR_TITLES.get(language.split("-")[0])
            or "Conow Local"
        )
        await panel_custom.async_register_panel(
            hass=hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_WEBCOMPONENT,
            config_panel_domain=DOMAIN,
            module_url=PANEL_SCRIPT_URL,
            sidebar_title=sidebar_title,
            sidebar_icon="mdi:format-list-group",
            embed_iframe=False,
            require_admin=False,
        )

    hass.data[f"{DOMAIN}_panel_registered"] = True
