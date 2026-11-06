# Conow Local for Home Assistant

Local **Modbus RTU / TCP** integration for CONOW balcony-solar / all-in-one energy devices (Lyra, CBE, Atlas). No cloud account required.

Protocol reference: [developer-docs/modbus/balcony-solar-storage.md](https://github.com/conow-labs/developer-docs/blob/main/modbus/balcony-solar-storage.md)

## Features

- Read real-time monitoring registers (battery, grid, PV, energy counters)
- System status binary sensors (charging, fault, running, …)
- Write control registers (power limits, off-grid switch, force charge/discharge)

## Prerequisites

Complete **all** of the following before adding the integration.

### 1. Activate the device in the App

The device must be commissioned and online in the **CONOW ECO App** at least once before the RS-485 interface becomes operational. RS-485 will not work on a factory-fresh device that has never been activated.

### 2. Enable external control in the App

Modbus RTU is disabled until you turn on external control in the app:

1. Open **CONOW ECO App** → **Devices** tab
2. Tap your device to enter the device panel → **Settings**
3. Toggle on **Enable External Control / ModBus RTU**

The RS-485 interface will not respond to any Modbus commands until this is enabled.

### 3. RS-485 wiring

Connect an RS-485 to USB adapter between the Home Assistant host and the device RS-485 port (A/B polarity must match the device label).

### 4. Serial parameters

Use the factory defaults unless you have changed them in manufacturer setup software:


| Parameter     | Value                  |
| ------------- | ---------------------- |
| Baud rate     | **38400**              |
| Data bits     | 8                      |
| Parity        | None                   |
| Stop bits     | 1 (8N1)                |
| Slave address | **160** (hex **0xA0**) |




## Install (HACS)

1. Add `https://github.com/conow-labs/home-assistant-local` as a custom repository (Integration)
2. Install **Conow Local**
3. Restart Home Assistant



## Configure

**Settings → Devices & Services → Add Integration → Conow Local**

First choose the connection type — **Modbus RTU (RS-485 serial)**, **Modbus TCP (RS-485↔Ethernet adapter)**, or **Modbus TCP (direct to all-in-one machine)**.

### Modbus RTU (serial)

| Field         | Value                                                                   |
| ------------- | ----------------------------------------------------------------------- |
| Device name   | Any label you prefer                                                    |
| Serial port   | Host path, e.g. `/dev/ttyUSB0` (Linux), `/dev/cu.usbserial-130` (macOS) |
| Slave address | `160`                                                                   |
| Baud rate     | `38400`                                                                 |

### Modbus TCP (Ethernet adapter)

For an **RS-485↔Ethernet converter** (Modbus TCP gateway). The adapter converts Modbus TCP to RTU — the device firmware and its RS-485 settings stay unchanged.

| Field           | Value                                  |
| --------------- | -------------------------------------- |
| Device name     | Any label you prefer                   |
| Host / IP       | Adapter IP, e.g. `192.168.1.50`        |
| TCP port        | `502` (default Modbus TCP port)        |
| Slave address   | `160`                                  |

Notes:

- The adapter must be a **Modbus TCP ↔ RTU gateway** (most 485-to-Ethernet converters are). Configure the adapter's serial side to the device defaults: **38400 8N1**, and it must pass through the unit ID (`160`).
- **Enable External Control / ModBus RTU** in the Conow app is still required — the device sees plain RTU either way.

### Modbus TCP (direct to all-in-one machine)

Use this when the all-in-one machine exposes its own Modbus TCP port, with no RS-485↔Ethernet adapter in between.

| Field           | Value                                  |
| --------------- | -------------------------------------- |
| Device name     | Any label you prefer                   |
| Host / IP       | Machine IP, e.g. `192.168.1.60`        |
| TCP port        | `502` (default Modbus TCP port)        |
| Slave address   | `160`                                  |
| Verification code | 8-character hex code shown on the machine |

When you submit the form, the integration writes the verification code to holding registers **0x2701–0x2702** (9985–9986, uint32, high word first). The 8 characters are hexadecimal digits (`0-9`, `A-F`). The setup succeeds only when the device acknowledges the write; a rejected code shows a verification error instead of creating the entry.




### Finding the serial port

This integration uses **Modbus RTU over RS-485** — the **Serial port** field is the host **device path** for your USB-to-RS-485 adapter, not a TCP/HTTP port number.

1. Connect the RS-485 adapter to the Home Assistant host (or the machine where you run HA).
2. List serial devices **before and after** plugging in the adapter; the new entry is your port.

**Linux / Home Assistant OS / Supervised**

```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
# or watch kernel messages after plug-in:
dmesg | tail -20
```

Common paths: `/dev/ttyUSB0`, `/dev/ttyACM0`.

**macOS** (development / local testing)

```bash
ls /dev/cu.*
```

Prefer `/dev/cu.*` over `/dev/tty.*` — `cu` devices are call-out ports suitable for Modbus masters. Common names: `/dev/cu.usbserial-*`, `/dev/cu.wchusbserial*`, `/dev/cu.SLAB_USBtoUART`.

**Home Assistant in Docker**

The container must have the serial device passed through, e.g. `--device /dev/ttyUSB0:/dev/ttyUSB0`. Use the **same path inside the container** in the integration setup.

**Home Assistant OS add-on / VM**

Ensure USB passthrough is enabled for the adapter in your hypervisor or host settings; then use the path shown on the HA host (often `/dev/ttyUSB0`).

If setup fails with *cannot connect*, or sensor values look wrong (e.g. extremely large numbers), check:

1. **Enable External Control / ModBus RTU** is on in the App
2. Slave address is `160` and baud rate is `38400`
3. Only one program is using the serial port at a time
4. RS-485 A/B wiring and USB adapter driver are correct



## Project layout

The integration is organised by the five pipeline layers, so the directory
name tells you which stage a module belongs to:

```text
custom_components/conow_local/
├── maps/                      # Layers 1-2: map registration and parsing
│   ├── registry.py            # L1  v1/v2 files, firmware probe and routing
│   ├── model.py               # L2  JSON → registers/blocks, decode, bounds, encode
│   ├── entity_model.py        # L2  register → EntitySpec (platform, unique id, name key)
│   ├── registers.json         # L1  v1 map data
│   └── panel_registers.json   # L1  v2 map data
├── device/                    # Layer 3: Home Assistant device page helpers
│   ├── coordinator.py         #     polls the active map and serves decoded values
│   ├── descriptions.py        #     EntitySpec → HA entity descriptions
│   └── guard.py               #     refuses device-page writes and links to the panel
├── panel/                     # Layer 4: the Conow Local panel
│   ├── panel_api.py           #     websocket API, static assets, panel registration
│   ├── panel_functions.py     #     group rendering, validation and atomic writes
│   └── frontend/              #     panel JS and generated UI translations
├── sensor.py … time.py        # Layer 3: HA platform implementations
│                              #   sensor, binary_sensor, number, select,
│                              #   switch and time
├── strings.json               # Layer 5: source Home Assistant entity strings
├── translations/              # Layer 5: generated Home Assistant translations
├── __init__.py                # Home Assistant integration entry point
├── client.py                  # shared raw Modbus RTU/TCP I/O
├── const.py                   # shared constants
└── config_flow.py             # setup and reconfiguration dialog
```

Home Assistant imports platform modules by the path
`custom_components.conow_local.<platform>`, so the six platform modules
(`sensor.py`, `binary_sensor.py`, `number.py`, `select.py`, `switch.py`,
`time.py`) at the integration root are the platform entry points and entity
implementations; they use the helpers in `device/` for polling and entity
descriptions. All translations are generated from one catalog by
`tools/i18n/build_panel_i18n.py`.

## Polling & control read-back



### Scheduled polling (automatic read)

The integration polls the device on a fixed interval and refreshes all entities:

| Map | Interval | Meaning |
| --- | -------- | ------- |
| v1 (`maps/registers.json`) | **5 s** | Background read of every block of the v1 map |
| v2 (`maps/panel_registers.json`) | **30 s** | Background read of every block of the v2 map |

Protocol docs require a polling interval of **at least 2 s**; v1 keeps **5 s**
to reduce RS-485 bus load when communication is unstable. Each poll issues one
FC `0x03` read per map `blocks` entry; the read count is derived from the
highest register address in that block. Frames are spaced by a short
inter-frame delay.

### Writes

Device-page controls are **visible but do not write directly**: numbers,
selects, switches and times all refuse the write with a notification that links
to the grouping panel. All writes go through that panel, which sends a **whole
group** at once:

1. The group's writable registers are validated against their live limits
2. Contiguous registers are merged into one atomic FC `0x10` frame; groups with
   gaps fall back to back-to-back FC `0x06` writes
3. The panel state is re-read immediately, so the UI does not wait for the next
   poll

## Logging & Modbus frames

Enable integration logs in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.conow_local: info
```

For Modbus **read** hex dumps (scheduled poll and post-write read-back), also set:

```yaml
    custom_components.conow_local: debug
    custom_components.conow_local.client: debug
```

View logs: **Settings → System → Logs**, then filter by `conow_local` or `Modbus write`.

### Key log messages

| Level | Message | When |
|-------|---------|------|
| INFO | `Control write <name>: addr=... physical=... raw=...` | Before FC `0x06` |
| INFO | `Modbus write TX (FC 0x06): A0 06 ...` | **Outgoing RTU frame** (hex) |
| INFO | `Modbus write OK: ... expected RX echo: ...` | Device acknowledged the write |
| ERROR | `Modbus write failed: ... TX=...` | No reply or Modbus error |
| ERROR | `Read failed after 3 attempts ...` | Poll or read-back failed |
| DEBUG | `Coordinator: executing Modbus write then read-back` | You change a control entity |
| DEBUG | `Modbus read TX (FC 0x03): A0 03 ...` | Read request (poll or read-back) |
| DEBUG | `Modbus read OK: ... RX=...` | Read response RTU frame (hex) + decoded registers |
| DEBUG | `Coordinator: read-back control snapshot ...` | Control registers after a write |

### Example write frame (discharge power limit 700 W → register 10101)

```text
A0 06 27 75 02 BC 8B 04
│  │  └───┘  └───┘  └───┘
│  │    │      │      └── CRC16 (little-endian)
│  │    │      └── Value: 700 (0x02BC)
│  │    └── Address: 10101 (0x2775)
│  └── FC 0x06
└── Slave 160 (0xA0)
```

On success, the device normally **echoes the same 8 bytes** as the response.

## Register map routing

Two maps ship with the integration. They now share one schema, one model and
one entity classifier; only the data differs:

| Map | File | Used for |
|-----|------|----------|
| v1 | `maps/registers.json` | Firmware probe failed (fallback) |
| v2 (finalized) | `maps/panel_registers.json` | Firmware register responds (any value) |

The two maps are **mutually exclusive** for an entry: exactly one is loaded,
polled and rendered. The selection is made once at setup:

After setup begins, the integration reads the firmware register at
**10062 (0x274E)** before the first poll. The v2 map and its panel features
are used whenever the device answers this read — the value does not matter,
and current machines reply `0x0000`. A missing reply, timeout or Modbus
exception keeps `registers.json`; the integration never falls forward to the
finalized control addresses by accident. When the reply happens to contain a
version string (e.g. `1.2`), it is shown in the logs and the panel.

The panel asks for the map version reported by the active device, so it never
briefly renders the other map's groups. Every map file path lives in
`maps/registry.py`; no other module hardcodes a filename.

## Adding registers & entities

Entity platforms are **derived from the register metadata**, so adding a
Modbus point means editing JSON plus translations — no Python changes:

1. **`maps/registers.json` and/or `maps/panel_registers.json`** — address, scale,
   unit, `writable`, `device_class`/`state_class`, enum `values`, `bits`, etc.
2. **`tools/i18n/build_panel_i18n.py`** — add the register name (and enum labels,
   if any) to its catalogs for en/de/nl.
3. Run `python3 tools/i18n/build_panel_i18n.py` — it regenerates the panel i18n
   files **and** the `entity` sections of `strings.json` /
   `translations/*.json`.

The tool fails loudly when a register, group, enum or entity name is missing a
translation, so a half-translated map cannot ship. Chinese names come straight
from the map's `name`/`values` fields.

### Entity classification

| Register shape | Entity created |
| -------------- | -------------- |
| has `bits[]` | one read-only `binary_sensor` per bit (no raw register entity) |
| `writable` boolean | `switch` (device-page write refused; use the panel) |
| `format: "hhmm"` | `time` (device-page write refused; use the panel) |
| other `writable` numeric | `number` (device-page write refused; use the panel) |
| `writable` enum | `select` (device-page write refused; use the panel) |
| read-only boolean | `binary_sensor` |
| anything else read-only | `sensor` |

### `registers.json` structure

| Section | Purpose |
|---------|---------|
| `version` | Schema version |
| `meta` | Map label, source/firmware notes |
| `blocks` | Modbus read block names and start addresses; read count is **auto-calculated** from register addresses |
| `registers` | Modbus definition **and** entity metadata: `code`, `address`, `block`, `dtype`, `scale`, `unit`, `writable`, `name`, `device_class`, `state_class`, `entity_category`, `values`, `bits`, `format` |
| `groups` | Grouping-panel layout: members, subgroups, atomic write spans |

### Example — add a read-only sensor

In the map's `registers`:

```json
{
  "code": "new_metric",
  "name": "New Metric",
  "address": 10037,
  "block": "monitoring",
  "dtype": "uint16",
  "scale": 0.1,
  "unit": "W",
  "device_class": "power",
  "state_class": "measurement",
  "writable": false
}
```

Add `"new_metric": ("New Metric", "Neue Metrik", "Nieuwe metriek")` to the
tool's `REGISTERS` catalog (the Chinese name comes from `name`), then run the
i18n tool and **reload the integration**.

### Platform-specific fields

| Platform | Source fields |
|----------|---------------|
| `sensor` | `device_class`, `state_class`, `entity_category`, `unit`, `values` (enum/boolean) |
| `binary_sensor` | `bits[]` (`code`, `bit`, `name`, `device_class`) or boolean register `device_class` |
| `switch` | `writable: true` on a boolean register |
| `time` | `format: "hhmm"` |

## Q&A

### Why do App settings seem to have no effect while Home Assistant is connected?

The firmware runs **two independent control paths** that are **not merged**:

| Path | Description |
|------|-------------|
| **Modbus real-time control** | Registers **10100–10107** (and related monitoring reads). Used by this integration and other EMS hosts over RS-485. |
| **App / cloud target-driven logic** | Platform or App schedule and target parameters. |

**Modbus priority rule (firmware behaviour):**

- While **Modbus communication is active**, the device **only follows Modbus commands**. App / cloud instructions are not applied.
- After **Modbus communication ends** (serial unplugged, host stopped polling, or bus idle long enough for the firmware to drop the link), the device **falls back to App / self-consumption mode** by default.

**Practical implications for `conow_local` users:**

1. Keep **Enable External Control / ModBus RTU** on in the App (required for Modbus to work at all), but expect **runtime control** to come from Home Assistant while the integration is polling.
2. To let the App / cloud strategy drive the device again, **stop Home Assistant from holding the serial port** (disable/reload the integration, or disconnect RS-485).
3. Do not assume App slider changes and Modbus writes “add up” — only one path is active at a time.

## License

MIT
