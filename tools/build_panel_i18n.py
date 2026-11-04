"""Generate the grouping panel's i18n JSON files.

Run from the repository root:
    python tools/build_panel_i18n.py

Chinese names/labels come straight from ``panel_registers.json``; English,
German and Dutch are looked up here so the panel can follow the Home
Assistant language instead of always rendering Chinese.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "custom_components/conow_local/panel/panel_registers.json"
V1_MAP_PATH = ROOT / "custom_components/conow_local/registers.json"
OUT_DIR = ROOT / "custom_components/conow_local/panel/frontend/i18n"

LANGS = ("en", "de", "nl")

# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
# One entry per category column of each table.  Both maps now share the same
# category names, so most ids are used by v1 and v2 alike.
GROUPS = {
    "system": ("System", "System", "Systeem"),
    "realtime": ("Real-time Monitoring", "Echtzeitüberwachung", "Realtime bewaking"),
    "monitor_detail": (
        "Detailed Monitoring",
        "Detaillierte Überwachung",
        "Gedetailleerde bewaking",
    ),
    "device_info": (
        "Operating Parameters & Device Information",
        "Betriebsparameter & Geräteinformationen",
        "Bedrijfsparameters & apparaatinformatie",
    ),
    "lifetime_energy": ("Cumulative Energy", "Kumulierte Energie", "Cumulatieve energie"),
    "power_limit": (
        "Power & SoC Settings",
        "Leistungs- & SoC-Einstellungen",
        "Vermogen & SoC-instellingen",
    ),
    "force_control": ("Real-time Control", "Echtzeitsteuerung", "Realtime besturing"),
    "work_strategy": ("Work Strategy", "Arbeitsstrategie", "Werkstrategie"),
    "generator_do": ("Generator & DO", "Generator & DO", "Generator & DO"),
    "base_load": ("Base Load", "Grundlast", "Basislast"),
    "base_load_schedule": (
        "Base Load Schedule",
        "Grundlast-Zeitplan",
        "Basislast-schema",
    ),
    "tou_schedule": ("TOU Schedule", "TOU-Zeitplan", "TOU-schema"),
}

SUBGROUPS = {
    "en": {"slot": "Slot {n}", "strategy": "Strategy {n}"},
    "de": {"slot": "Zeitfenster {n}", "strategy": "Strategie {n}"},
    "nl": {"slot": "Tijdslot {n}", "strategy": "Strategie {n}"},
}

# ---------------------------------------------------------------------------
# Register names: code -> (en, de, nl)
# ---------------------------------------------------------------------------
REGISTERS = {
    "device_status": ("Device Status", "Gerätestatus", "Apparaatstatus"),
    "device_fault_code": ("Device Fault Code", "Gerätefehlercode", "Apparaatfoutcode"),
    "system_soc": ("System SoC", "System-SoC", "Systeem-SoC"),
    "meter_connection_state": (
        "Meter Connection State",
        "Zählerverbindungsstatus",
        "Meterverbindingsstatus",
    ),
    "meter_total_power": (
        "Meter Total Power",
        "Zählergesamtleistung",
        "Metertotaalvermogen",
    ),
    "grid_active_power": (
        "Grid Active Power",
        "Netz-Wirkleistung",
        "Net actief vermogen",
    ),
    "pv_total_power": ("PV Total Power", "PV-Gesamtleistung", "PV-totaalvermogen"),
    "battery_work_state": (
        "Battery Work State",
        "Batteriebetriebsstatus",
        "Accuwerkstatus",
    ),
    "battery_power": ("Battery Power", "Batterieleistung", "Accuvermogen"),
    "bypass_switch_state": (
        "Bypass Switch State",
        "Bypass-Schaltstatus",
        "Bypass-schakelstatus",
    ),
    "bypass_power": ("Bypass Power", "Bypass-Leistung", "Bypass-vermogen"),
    "grid_voltage": ("Grid Voltage", "Netzspannung", "Netspanning"),
    "grid_current": ("Grid Current", "Netzstrom", "Netstroom"),
    "grid_frequency": ("Grid Frequency", "Netzfrequenz", "Netfrequentie"),
    "phase_a_power": ("Phase A Power", "Phase-A-Leistung", "Fase A vermogen"),
    "phase_b_power": ("Phase B Power", "Phase-B-Leistung", "Fase B vermogen"),
    "phase_c_power": ("Phase C Power", "Phase-C-Leistung", "Fase C vermogen"),
    "pv_string_count": ("PV String Count", "Anzahl PV-Strings", "Aantal PV-strings"),
    "pv1_voltage": ("PV1 Voltage", "PV1-Spannung", "PV1-spanning"),
    "pv1_current": ("PV1 Current", "PV1-Strom", "PV1-stroom"),
    "pv1_energy": ("PV1 Energy", "PV1-Energie", "PV1-energie"),
    "pv2_voltage": ("PV2 Voltage", "PV2-Spannung", "PV2-spanning"),
    "pv2_current": ("PV2 Current", "PV2-Strom", "PV2-stroom"),
    "pv2_energy": ("PV2 Energy", "PV2-Energie", "PV2-energie"),
    "pv3_voltage": ("PV3 Voltage", "PV3-Spannung", "PV3-spanning"),
    "pv3_current": ("PV3 Current", "PV3-Strom", "PV3-stroom"),
    "pv3_energy": ("PV3 Energy", "PV3-Energie", "PV3-energie"),
    "pv4_voltage": ("PV4 Voltage", "PV4-Spannung", "PV4-spanning"),
    "pv4_current": ("PV4 Current", "PV4-Strom", "PV4-stroom"),
    "pv4_energy": ("PV4 Energy", "PV4-Energie", "PV4-energie"),
    "battery_voltage": ("Battery Voltage", "Batteriespannung", "Accuspanning"),
    "battery_current": ("Battery Current", "Batteriestrom", "Accustroom"),
    "cell_temp_max": (
        "Max. Cell Temperature",
        "Max. Zelltemperatur",
        "Max. celtemperatuur",
    ),
    "cell_temp_min": (
        "Min. Cell Temperature",
        "Min. Zelltemperatur",
        "Min. celtemperatuur",
    ),
    "battery_max_charge_power": (
        "Current Max. Battery Charge Power",
        "Aktuelle max. Batterieladeleistung",
        "Huidig max. acculaadvermogen",
    ),
    "battery_max_discharge_power": (
        "Current Max. Battery Discharge Power",
        "Aktuelle max. Batterieentladeleistung",
        "Huidig max. accuontlaadvermogen",
    ),
    "bypass_voltage": ("Bypass Voltage", "Bypass-Spannung", "Bypass-spanning"),
    "bypass_current": ("Bypass Current", "Bypass-Strom", "Bypass-stroom"),
    "bypass_frequency": ("Bypass Frequency", "Bypass-Frequenz", "Bypass-frequentie"),
    "design_capacity": (
        "Design Capacity",
        "Auslegungskapazität",
        "Ontwerpcapaciteit",
    ),
    "remaining_capacity": (
        "Remaining Capacity",
        "Restkapazität",
        "Resterende capaciteit",
    ),
    "system_backup_soc": (
        "System Backup SoC",
        "System-Reserve-SoC",
        "Systeem-reserve-SoC",
    ),
    "soh": ("SOH", "SOH", "SOH"),
    "hardware_max_ac_charge_power": (
        "Hardware Max. AC Charge Power",
        "Hardware max. AC-Ladeleistung",
        "Hardware max. AC-laadvermogen",
    ),
    "hardware_max_ac_discharge_power": (
        "Hardware Max. AC Discharge Power",
        "Hardware max. AC-Entladeleistung",
        "Hardware max. AC-ontlaadvermogen",
    ),
    "grid_code_export_limit": (
        "Grid Code Export Limit",
        "Netzeinspeise-Grenzwert",
        "Netcode-exportlimiet",
    ),
    "global_ac_charge_power_limit": (
        "Global Max. AC Charge Power",
        "Globale max. AC-Ladeleistung",
        "Globaal max. AC-laadvermogen",
    ),
    "global_ac_discharge_power_limit": (
        "Global Max. AC Discharge Power",
        "Globale max. AC-Entladeleistung",
        "Globaal max. AC-ontlaadvermogen",
    ),
    "wifi_signal": (
        "Wi-Fi Signal Strength",
        "Wi-Fi-Signalstärke",
        "Wi-Fi-signaalsterkte",
    ),
    "device_serial": (
        "Device Serial Number",
        "Geräteseriennummer",
        "Serienummer apparaat",
    ),
    "firmware_version": ("Firmware Version", "Firmware-Version", "Firmwareversie"),
    "grid_import_energy_total": (
        "Total Grid Import Energy",
        "Netzbezug gesamt",
        "Totaal netimport",
    ),
    "grid_export_energy_total": (
        "Total Grid Export Energy",
        "Netzeinspeisung gesamt",
        "Totaal netexport",
    ),
    "meter_import_energy_total": (
        "Meter Total Import Energy",
        "Zählerbezug gesamt",
        "Totaal meterimport",
    ),
    "meter_export_energy_total": (
        "Meter Total Export Energy",
        "Zählereinspeisung gesamt",
        "Totaal meterexport",
    ),
    "pv_energy_total": ("Total PV Energy", "PV-Gesamtenergie", "Totaal PV-energie"),
    "battery_charge_energy_total": (
        "Total Battery Charge Energy",
        "Batterie-Ladeenergie gesamt",
        "Totaal acculaadenergie",
    ),
    "battery_discharge_energy_total": (
        "Total Battery Discharge Energy",
        "Batterie-Entladeenergie gesamt",
        "Totaal accuontlaadenergie",
    ),
    "bypass_output_energy_total": (
        "Total Bypass Output Energy",
        "Bypass-Ausgangsenergie gesamt",
        "Totaal bypass-uitgangsenergie",
    ),
    "bypass_input_energy_total": (
        "Total Bypass Input Energy",
        "Bypass-Eingangsenergie gesamt",
        "Totaal bypass-ingangsenergie",
    ),
    "ac_charge_power_limit": (
        "AC Charge Power Limit",
        "AC-Ladeleistungsgrenze",
        "AC-laadvermogenlimiet",
    ),
    "ac_discharge_power_limit": (
        "AC Discharge Power Limit",
        "AC-Entladeleistungsgrenze",
        "AC-ontlaadvermogenlimiet",
    ),
    "safety_soc": ("Safety SoC", "Sicherheits-SoC", "Veiligheids-SoC"),
    "charge_discharge_direction": (
        "Charge/Discharge Direction",
        "Lade-/Entladerichtung",
        "Laad-/ontlaadrichting",
    ),
    "battery_target_power": (
        "Target Charge/Discharge Power",
        "Ziel-Lade-/Entladeleistung",
        "Doel laad-/ontlaadvermogen",
    ),
    "charge_discharge_cutoff_soc": (
        "Charge/Discharge Cutoff SoC",
        "Lade-/Entlade-Abschalt-SoC",
        "Laad-/ontlaadafslag-SoC",
    ),
    "charge_discharge_duration": (
        "Charge/Discharge Duration",
        "Lade-/Entladedauer",
        "Laad-/ontlaadduur",
    ),
    "work_mode": ("Work Mode", "Arbeitsmodus", "Werkmodus"),
    "base_load_setpoint": ("Base Load", "Grundlast", "Basislast"),
    "backup_soc": ("Backup SoC", "Reserve-SoC", "Reserve-SoC"),
    "allow_reverse_power": (
        "Allowed Reverse Power",
        "Zulässige Rückspeiseleistung",
        "Toegestaan terugleververmogen",
    ),
    "allow_battery_export": (
        "Allow Battery Export",
        "Batterieeinspeisung erlauben",
        "Accu-export toestaan",
    ),
    "bypass_enable": ("Bypass Switch", "Bypass-Schalter", "Bypass-schakelaar"),
    "off_grid_output_enable": (
        "Off-Grid Output Switch",
        "Off-Grid-Ausgangsschalter",
        "Off-grid-uitgangsschakelaar",
    ),
    "pv_curtailment_enable": (
        "PV Curtailment",
        "PV-Abregelung",
        "PV-beperking",
    ),
    "modbus_timeout": ("Modbus Timeout", "Modbus-Timeout", "Modbus-time-out"),
    "generator_enable": ("Generator Switch", "Generator-Schalter", "Generator-schakelaar"),
    "generator_start_time": (
        "Generator Start Time",
        "Generator-Startzeit",
        "Generator-starttijd",
    ),
    "generator_end_time": (
        "Generator End Time",
        "Generator-Endzeit",
        "Generator-eindtijd",
    ),
    "generator_power": ("Generator Power", "Generatorleistung", "Generatorvermogen"),
    "generator_start_soc": (
        "Generator Start SoC",
        "Generator-Start-SoC",
        "Generator-start-SoC",
    ),
    "generator_stop_soc": (
        "Generator Stop SoC",
        "Generator-Stopp-SoC",
        "Generator-stop-SoC",
    ),
    "do1_state": ("DO1 Control", "DO1-Steuerung", "DO1-besturing"),
    "do2_state": ("DO2 Control", "DO2-Steuerung", "DO2-besturing"),
    "base_load_slot_count": (
        "Base Load Slot Count",
        "Anzahl Grundlast-Zeitfenster",
        "Aantal basislast-tijdsloten",
    ),
    "tou_slot_count": ("TOU Slot Count", "Anzahl TOU-Zeitfenster", "Aantal TOU-tijdsloten"),
}

# Formulaic slot registers (1-8) are generated.
BASE_SLOT_TEMPLATES = {
    "start": (
        "Base Load Slot {n} Start Time",
        "Grundlast Zeitfenster {n} Startzeit",
        "Basislast tijdslot {n} starttijd",
    ),
    "end": (
        "Base Load Slot {n} End Time",
        "Grundlast Zeitfenster {n} Endzeit",
        "Basislast tijdslot {n} eindtijd",
    ),
    "power": (
        "Base Load Slot {n} Power",
        "Grundlast Zeitfenster {n} Leistung",
        "Basislast tijdslot {n} vermogen",
    ),
}
TOU_SLOT_TEMPLATES = {
    "start": (
        "Manual Charge/Discharge Strategy {n} Start Time",
        "Manuelle Lade-/Entladestrategie {n} Startzeit",
        "Handmatige laad-/ontlaadstrategie {n} starttijd",
    ),
    "end": (
        "Manual Charge/Discharge Strategy {n} End Time",
        "Manuelle Lade-/Entladestrategie {n} Endzeit",
        "Handmatige laad-/ontlaadstrategie {n} eindtijd",
    ),
    "mode": (
        "Manual Charge/Discharge Strategy {n} Work Mode",
        "Manuelle Lade-/Entladestrategie {n} Arbeitsmodus",
        "Handmatige laad-/ontlaadstrategie {n} werkmodus",
    ),
    "target_soc": (
        "Manual Charge/Discharge Strategy {n} Target SoC",
        "Manuelle Lade-/Entladestrategie {n} Ziel-SoC",
        "Handmatige laad-/ontlaadstrategie {n} doel-SoC",
    ),
    "power": (
        "Manual Charge/Discharge Strategy {n} Discharge Power",
        "Manuelle Lade-/Entladestrategie {n} Entladeleistung",
        "Handmatige laad-/ontlaadstrategie {n} ontlaadvermogen",
    ),
}

for _n in range(1, 9):
    for _field, _templates in BASE_SLOT_TEMPLATES.items():
        REGISTERS[f"base_load_slot{_n}_{_field}"] = tuple(
            value.format(n=_n) for value in _templates
        )
    for _field, _templates in TOU_SLOT_TEMPLATES.items():
        REGISTERS[f"tou_slot{_n}_{_field}"] = tuple(
            value.format(n=_n) for value in _templates
        )

# ---------------------------------------------------------------------------
# Enum values: code -> raw -> (en, de, nl)
# ---------------------------------------------------------------------------
VALUES = {
    "meter_connection_state": {
        "0": ("Paired & connected", "Gekoppelt & verbunden", "Gekoppeld & verbonden"),
        "1": (
            "Paired, not connected",
            "Gekoppelt, nicht verbunden",
            "Gekoppeld, niet verbonden",
        ),
        "2": (
            "Unpaired, not connected",
            "Nicht gekoppelt, nicht verbunden",
            "Niet gekoppeld, niet verbonden",
        ),
    },
    "battery_work_state": {
        "0": ("idle", "idle", "idle"),
        "1": ("chg", "chg", "chg"),
        "2": ("dchg", "dchg", "dchg"),
    },
    "bypass_switch_state": {
        "0": ("off", "aus", "uit"),
        "1": ("on", "an", "aan"),
    },
    "charge_discharge_direction": {
        "0": ("idle", "idle", "idle"),
        "1": ("chg", "chg", "chg"),
        "2": ("dchg", "dchg", "dchg"),
        "3": ("exit", "exit", "exit"),
    },
    "work_mode": {
        "1": ("Self-consumption", "Eigenverbrauch", "Eigen verbruik"),
        "2": ("Manual schedule", "Manueller Zeitplan", "Handmatig schema"),
        "3": ("idle", "idle", "idle"),
    },
    "allow_battery_export": {
        "0": (
            "Battery export disabled",
            "Batterieeinspeisung deaktiviert",
            "Accu-export uitgeschakeld",
        ),
        "1": (
            "Battery export enabled",
            "Batterieeinspeisung aktiviert",
            "Accu-export ingeschakeld",
        ),
    },
    "bypass_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "off_grid_output_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "pv_curtailment_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "generator_enable": {
        "0": ("Disabled", "Deaktiviert", "Uitgeschakeld"),
        "1": ("Enabled", "Aktiviert", "Ingeschakeld"),
    },
    "do1_state": {"0": ("off", "aus", "uit"), "1": ("on", "an", "aan")},
    "do2_state": {"0": ("off", "aus", "uit"), "1": ("on", "an", "aan")},
}
for _n in range(1, 9):
    VALUES[f"tou_slot{_n}_mode"] = {
        "0": ("Charge", "Laden", "Laden"),
        "1": ("Discharge", "Entladen", "Ontladen"),
    }

# ---------------------------------------------------------------------------
# UI strings
# ---------------------------------------------------------------------------
UI = {
    "en": {
        "title": "Conow Local Grouped Panel",
        "loadingRegisters": "Reading device registers…",
        "loadingMap": "Loading grouped map…",
        "errorDeviceNotFound": "Device not found or the integration is not loaded.",
        "errorUnknownCommand": (
            "Panel WebSocket commands are not registered — restart Home Assistant "
            "and open this page again."
        ),
        "addressHint": "Address {address} ({hex}) · {dtype}{length} · {access}",
        "addressAccessWritable": "writable",
        "addressAccessReadonly": "read-only",
        "invalidTimeHint": (
            "Device value {raw} is not a valid HH:MM time (00:00–23:59); it is "
            "hidden — set a new time before applying."
        ),
        "entityHint": "Click to open the details of {entity}",
        "valueOn": "On",
        "valueOff": "Off",
        "changedFromTo": "{name}: {old} → {new}",
        "changedSeparator": "; ",
        "codeSeparator": ", ",
        "groupHintInvalidTime": "Invalid time readings, set them again: {codes}",
        "groupHintOutOfRange": "Outside the allowed range, adjust: {codes}",
        "groupHintIncomplete": "Fill in every writable field",
        "groupHintUnchanged": "No changes",
        "noticeInvalidTimes": (
            "Found {count} time registers with invalid readings ({preview}{more}); "
            "their values are hidden — set new times in those groups before applying."
        ),
        "noticeInvalidTimesMore": ", …",
        "warningInvalidTime": "Invalid reading — set again",
        "noticeClamped": "{name} limited to {value} ({min}–{max})",
        "noticeTimeClamped": "Time limited to {value} (valid range 00:00–23:59)",
        "confirmWrite": "Write group “{group}” to the device?\n\n{preview}",
        "noticeApplied": "{group}: sent",
        "noticeFailed": "{group}: {error}",
        "actionApplying": "Sending…",
        "actionApply": "Apply group",
        "titleExpandGroup": "Expand group",
        "titleCollapseGroup": "Collapse group",
        "mapMismatchV1": (
            "Device firmware {firmware} is below {minimum}, which is required for "
            "the finalized register map (panel_registers.json); entities are read "
            "from registers.json (v1) and the grouped panel is unavailable."
        ),
        "mapUnreadable": (
            "The device answers Modbus, but none of the finalized map addresses could "
            "be read — it probably still speaks the v1 protocol "
            "(10000–10036 / 10100–10107). Pick a v2 entry or point this entry at a "
            "server that serves the finalized map."
        ),
        "emptyNoGroups": "No matching groups.",
        "comboNoMatch": "No matches",
        "modeTcpDirect": "TCP direct",
        "stateOffline": " (offline)",
        "stateUnloaded": " (not loaded)",
        "allGroups": "All groups",
        "allEntities": "All entities",
        "accessAll": "All (read/write)",
        "accessRw": "Writable only",
        "accessRo": "Read-only only",
        "selectDevice": "Select device…",
        "refresh": "Refresh",
        "entityOption": "{name} ({code})",
        "unknownFirmware": "unknown",
    },
    "de": {
        "title": "Conow Local Gruppenpanel",
        "loadingRegisters": "Geräteregister werden gelesen…",
        "loadingMap": "Gruppierte Zuordnung wird geladen…",
        "errorDeviceNotFound": "Gerät nicht gefunden oder Integration nicht geladen.",
        "errorUnknownCommand": (
            "Panel-WebSocket-Befehle sind nicht registriert – starten Sie Home "
            "Assistant neu und öffnen Sie diese Seite erneut."
        ),
        "addressHint": "Adresse {address} ({hex}) · {dtype}{length} · {access}",
        "addressAccessWritable": "beschreibbar",
        "addressAccessReadonly": "nur lesen",
        "invalidTimeHint": (
            "Gerätewert {raw} ist keine gültige Uhrzeit (00:00–23:59); er wird "
            "ausgeblendet – stellen Sie vor dem Senden eine neue Zeit ein."
        ),
        "entityHint": "Klicken, um die Details von {entity} zu öffnen",
        "valueOn": "An",
        "valueOff": "Aus",
        "changedFromTo": "{name}: {old} → {new}",
        "changedSeparator": "; ",
        "codeSeparator": ", ",
        "groupHintInvalidTime": "Ungültige Zeitwerte, bitte erneut einstellen: {codes}",
        "groupHintOutOfRange": (
            "Außerhalb des zulässigen Bereichs, bitte anpassen: {codes}"
        ),
        "groupHintIncomplete": "Füllen Sie alle beschreibbaren Felder aus",
        "groupHintUnchanged": "Keine Änderungen",
        "noticeInvalidTimes": (
            "{count} Zeitregister mit ungültigen Werten gefunden ({preview}{more}); "
            "die Werte werden ausgeblendet – stellen Sie in diesen Gruppen neue "
            "Zeiten ein, bevor Sie senden."
        ),
        "noticeInvalidTimesMore": " usw.",
        "warningInvalidTime": "Ungültiger Wert – erneut einstellen",
        "noticeClamped": "{name} auf {value} begrenzt ({min}–{max})",
        "noticeTimeClamped": "Zeit auf {value} begrenzt (gültig 00:00–23:59)",
        "confirmWrite": "Gruppe „{group}“ auf das Gerät schreiben?\n\n{preview}",
        "noticeApplied": "{group}: gesendet",
        "noticeFailed": "{group}: {error}",
        "actionApplying": "Wird gesendet…",
        "actionApply": "Gruppe senden",
        "titleExpandGroup": "Gruppe ausklappen",
        "titleCollapseGroup": "Gruppe einklappen",
        "mapMismatchV1": (
            "Die Gerätefirmware {firmware} ist niedriger als die für die "
            "endgültigen Registerzuordnung (panel_registers.json) erforderliche Version "
            "{minimum}; Entitäten werden aus registers.json (v1) gelesen und das "
            "Gruppenpanel ist nicht verfügbar."
        ),
        "mapUnreadable": (
            "Das Gerät antwortet auf Modbus, aber keine Adresse der endgültigen Zuordnung "
            "konnte gelesen werden – es spricht vermutlich noch das v1-Protokoll "
            "(10000–10036 / 10100–10107). Wählen Sie einen v2-Eintrag oder verweisen "
            "Sie diesen Eintrag auf einen Server mit der endgültigen Zuordnung."
        ),
        "emptyNoGroups": "Keine passenden Gruppen.",
        "comboNoMatch": "Keine Treffer",
        "modeTcpDirect": "TCP direkt",
        "stateOffline": " (offline)",
        "stateUnloaded": " (nicht geladen)",
        "allGroups": "Alle Gruppen",
        "allEntities": "Alle Entitäten",
        "accessAll": "Alle (lesen/schreiben)",
        "accessRw": "Nur beschreibbar",
        "accessRo": "Nur lesen",
        "selectDevice": "Gerät auswählen…",
        "refresh": "Aktualisieren",
        "entityOption": "{name} ({code})",
        "unknownFirmware": "unbekannt",
    },
    "nl": {
        "title": "Conow Local groepenpaneel",
        "loadingRegisters": "Apparaatregisters lezen…",
        "loadingMap": "Gegroepeerde map laden…",
        "errorDeviceNotFound": (
            "Apparaat niet gevonden of integratie niet geladen."
        ),
        "errorUnknownCommand": (
            "Paneel-WebSocket-opdrachten zijn niet geregistreerd — herstart Home "
            "Assistant en open deze pagina opnieuw."
        ),
        "addressHint": "Adres {address} ({hex}) · {dtype}{length} · {access}",
        "addressAccessWritable": "beschrijfbaar",
        "addressAccessReadonly": "alleen lezen",
        "invalidTimeHint": (
            "Apparaatwaarde {raw} is geen geldige tijd (00:00–23:59); deze is "
            "verborgen — stel een nieuwe tijd in voordat u verzendt."
        ),
        "entityHint": "Klik om de details van {entity} te openen",
        "valueOn": "Aan",
        "valueOff": "Uit",
        "changedFromTo": "{name}: {old} → {new}",
        "changedSeparator": "; ",
        "codeSeparator": ", ",
        "groupHintInvalidTime": "Ongeldige tijdwaarden, stel ze opnieuw in: {codes}",
        "groupHintOutOfRange": "Buiten het toegestane bereik, pas aan: {codes}",
        "groupHintIncomplete": "Vul alle beschrijfbare velden in",
        "groupHintUnchanged": "Geen wijzigingen",
        "noticeInvalidTimes": (
            "{count} tijdregisters met ongeldige waarden gevonden ({preview}{more}); "
            "de waarden zijn verborgen — stel in die groepen nieuwe tijden in "
            "voordat u verzendt."
        ),
        "noticeInvalidTimesMore": " enz.",
        "warningInvalidTime": "Ongeldige waarde — opnieuw instellen",
        "noticeClamped": "{name} beperkt tot {value} ({min}–{max})",
        "noticeTimeClamped": "Tijd beperkt tot {value} (geldig 00:00–23:59)",
        "confirmWrite": "Groep “{group}” naar het apparaat schrijven?\n\n{preview}",
        "noticeApplied": "{group}: verzonden",
        "noticeFailed": "{group}: {error}",
        "actionApplying": "Verzenden…",
        "actionApply": "Groep verzenden",
        "titleExpandGroup": "Groep uitvouwen",
        "titleCollapseGroup": "Groep invouwen",
        "mapMismatchV1": (
            "Apparaatfirmware {firmware} is lager dan {minimum}, de vereiste versie "
            "voor de definitieve registermap (panel_registers.json); entiteiten worden "
            "uit registers.json (v1) gelezen en het groepenpaneel is niet beschikbaar."
        ),
        "mapUnreadable": (
            "Het apparaat antwoordt op Modbus, maar geen enkel adres van de "
            "definitieve map kon worden gelezen — het spreekt waarschijnlijk nog het "
            "v1-protocol (10000–10036 / 10100–10107). Kies een v2-item of laat dit "
            "item naar een server wijzen die de definitieve map aanbiedt."
        ),
        "emptyNoGroups": "Geen overeenkomende groepen.",
        "comboNoMatch": "Geen resultaten",
        "modeTcpDirect": "TCP direct",
        "stateOffline": " (offline)",
        "stateUnloaded": " (niet geladen)",
        "allGroups": "Alle groepen",
        "allEntities": "Alle entiteiten",
        "accessAll": "Alles (lezen/schrijven)",
        "accessRw": "Alleen beschrijfbaar",
        "accessRo": "Alleen lezen",
        "selectDevice": "Selecteer apparaat…",
        "refresh": "Vernieuwen",
        "entityOption": "{name} ({code})",
        "unknownFirmware": "onbekend",
    },
    "zh-Hans": {
        "title": "Conow Local 分组面板",
        "loadingRegisters": "读取设备寄存器…",
        "loadingMap": "加载分组表…",
        "errorDeviceNotFound": "设备不存在或集成未加载。",
        "errorUnknownCommand": (
            "面板 WebSocket 命令未注册 —— 请重启 Home Assistant 后再打开本页。"
        ),
        "addressHint": "地址 {address}（{hex}）· {dtype}{length} · {access}",
        "addressAccessWritable": "可写",
        "addressAccessReadonly": "只读",
        "invalidTimeHint": (
            "设备读数 {raw} 不是合法的时分（范围 00:00–23:59），已隐藏，"
            "请重新设置后下发"
        ),
        "entityHint": "点击查看 {entity} 的实体详情",
        "valueOn": "开",
        "valueOff": "关",
        "changedFromTo": "{name}：从 {old} 到 {new}",
        "changedSeparator": "；",
        "codeSeparator": "、",
        "groupHintInvalidTime": "时间读数非法，请重新设置：{codes}",
        "groupHintOutOfRange": "超出允许范围，请调整：{codes}",
        "groupHintIncomplete": "请填写完整所有可写字段",
        "groupHintUnchanged": "无改动",
        "noticeInvalidTimes": (
            "检测到 {count} 个时间寄存器读数非法（{preview}{more}），已隐藏原值；"
            "请在对应分组重新设置时间后再下发。"
        ),
        "noticeInvalidTimesMore": " 等",
        "warningInvalidTime": "读数非法，请重新设置",
        "noticeClamped": "{name} 已限制为 {value}（{min}–{max}）",
        "noticeTimeClamped": "时间已限制为 {value}（有效范围 00:00–23:59）",
        "confirmWrite": "确认把分组「{group}」写入设备？\n\n{preview}",
        "noticeApplied": "{group}：已下发",
        "noticeFailed": "{group}：{error}",
        "actionApplying": "下发中…",
        "actionApply": "批量下发",
        "titleExpandGroup": "展开分组",
        "titleCollapseGroup": "折叠分组",
        "mapMismatchV1": (
            "设备固件版本 {firmware}，低于启用定稿寄存器映射"
            "（panel_registers.json）所需的 {minimum}；已按 registers.json（v1）"
            "读取实体，分组面板不可用。"
        ),
        "mapUnreadable": (
            "设备有 Modbus 响应，但定稿映射的地址全部读不到 —— 多半仍在 v1 协议"
            "（10000–10036 / 10100–10107）。请选择配置为 v2 的条目，"
            "或把该条目指向提供定稿映射的服务端。"
        ),
        "emptyNoGroups": "没有匹配的分组。",
        "comboNoMatch": "没有匹配项",
        "modeTcpDirect": "TCP 直连",
        "stateOffline": "（离线）",
        "stateUnloaded": "（未加载）",
        "allGroups": "全部分组",
        "allEntities": "全部实体",
        "accessAll": "全部读写",
        "accessRw": "仅可写",
        "accessRo": "仅只读",
        "selectDevice": "选择设备…",
        "refresh": "刷新",
        "entityOption": "{name}（{code}）",
        "unknownFirmware": "未知",
    },
}


def _existing_translations(lang: str) -> dict:
    """Load the current output file so v1-only names survive regeneration."""
    path = OUT_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    v2 = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    v1 = json.loads(V1_MAP_PATH.read_text(encoding="utf-8"))
    entries = {
        item["code"]: item
        for item in (*v1["registers"], *v2["registers"])
    }
    all_codes = [item["code"] for item in v2["registers"]] + [
        item["code"]
        for item in v1["registers"]
        if item["code"] not in {reg["code"] for reg in v2["registers"]}
    ]
    group_ids = [item["id"] for item in v2["groups"]] + [
        item["id"]
        for item in v1["groups"]
        if item["id"] not in {group["id"] for group in v2["groups"]}
    ]
    existing = {
        lang: _existing_translations(lang) for lang in (*LANGS, "zh-Hans")
    }

    missing = [
        code
        for code in all_codes
        if code not in REGISTERS
        and code not in existing["en"].get("registers", {})
    ]
    if missing:
        raise SystemExit(f"Missing register translations: {missing}")
    unknown = [code for code in REGISTERS if code not in entries]
    if unknown:
        raise SystemExit(f"Unknown register translations: {unknown}")
    missing_groups = [
        group
        for group in group_ids
        if group not in GROUPS and group not in existing["en"].get("groups", {})
    ]
    if missing_groups:
        raise SystemExit(f"Missing group translations: {missing_groups}")
    for code, item in entries.items():
        if item.get("values") and code not in VALUES:
            raise SystemExit(f"Missing enum translations: {code}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Chinese: names/labels/enums come straight from the maps (v2 wins).
    zh_registers = {item["code"]: item["name"] for item in v1["registers"]}
    zh_registers.update(
        {item["code"]: item["name"] for item in v2["registers"]}
    )
    zh_groups = {item["id"]: item["label"] for item in v1["groups"]}
    zh_groups.update({item["id"]: item["label"] for item in v2["groups"]})
    zh_values = {
        code: {str(raw): label for raw, label in item["values"].items()}
        for code, item in entries.items()
        if item.get("values")
    }
    zh_payload = {
        "language": "zh-Hans",
        "ui": UI["zh-Hans"],
        "groups": zh_groups,
        "subgroups": {"slot": "时段 {n}", "strategy": "策略 {n}"},
        "registers": zh_registers,
        "values": zh_values,
    }
    (OUT_DIR / "zh-Hans.json").write_text(
        json.dumps(zh_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for index, lang in enumerate(LANGS):
        registers_out = {}
        for code in all_codes:
            if code in REGISTERS:
                registers_out[code] = REGISTERS[code][index]
            else:
                registers_out[code] = existing[lang]["registers"][code]
        groups_out = {}
        for group in group_ids:
            if group in GROUPS:
                groups_out[group] = GROUPS[group][index]
            else:
                groups_out[group] = existing[lang]["groups"][group]
        values_out = {
            code: {raw: labels[index] for raw, labels in options.items()}
            for code, options in VALUES.items()
        }
        for code, item in entries.items():
            if item.get("values") and code not in VALUES:
                values_out[code] = existing[lang]["values"][code]
        payload = {
            "language": lang,
            "ui": UI[lang],
            "groups": groups_out,
            "subgroups": SUBGROUPS[lang],
            "registers": registers_out,
            "values": values_out,
        }
        (OUT_DIR / f"{lang}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Wrote {len(all_codes)} register names and {len(group_ids)} groups to {OUT_DIR}")


if __name__ == "__main__":
    main()
