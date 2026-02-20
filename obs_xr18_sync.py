"""
OBS Studio Python Script – Behringer XR18 Snapshot Sync via OSC

Automatically loads a snapshot on a Behringer XR18 (X Air) mixer whenever
the active scene changes in OBS.  All settings (IP, port, scene→snapshot
mappings) are configurable through the OBS Scripts UI.

Requirements:
    pip install python-osc
"""

import json
import obspython as obs  # type: ignore
from pythonosc import udp_client

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_client = None  # pythonosc UDP client (re-created on settings change)
_xr18_ip = "192.168.1.15"
_xr18_port = 10024
_scene_map = {}  # {"OBS Scene Name": snapshot_id (1-64), …}
_scene_map_json = ""  # raw JSON kept in sync with _scene_map
_enabled = True  # master on/off switch exposed in UI

# Maximum number of individual scene→snapshot rows shown in the UI.
# Users who need more can fall back to the JSON editor.
MAX_SCENE_ROWS = 20

# ---------------------------------------------------------------------------
# OSC helpers
# ---------------------------------------------------------------------------


def _create_client():
    """(Re-)create the OSC UDP client with the current settings."""
    global _client
    try:
        _client = udp_client.SimpleUDPClient(_xr18_ip, _xr18_port)
        obs.script_log(obs.LOG_INFO, f"OSC client created → {_xr18_ip}:{_xr18_port}")
    except Exception as exc:
        _client = None
        obs.script_log(obs.LOG_ERROR, f"Failed to create OSC client: {exc}")


def load_snapshot(snapshot_id):
    """Send the /-snap/load OSC command to the XR18.

    *snapshot_id* uses **1-based** numbering (matching the mixer UI).
    The command is sent as 0-based internally.
    """
    if _client is None:
        obs.script_log(
            obs.LOG_WARNING, "OSC client not initialised – skipping snapshot load."
        )
        return

    osc_index = int(snapshot_id) - 1
    if osc_index < 0 or osc_index > 63:
        obs.script_log(obs.LOG_WARNING, f"Snapshot {snapshot_id} out of range (1-64).")
        return

    try:
        _client.send_message("/-snap/load", osc_index)
        obs.script_log(
            obs.LOG_INFO, f"XR18 ← /-snap/load {osc_index}  (Snapshot #{snapshot_id})"
        )
    except Exception as exc:
        obs.script_log(obs.LOG_ERROR, f"OSC send failed: {exc}")


# ---------------------------------------------------------------------------
# OBS event handling
# ---------------------------------------------------------------------------


def on_event(event):
    """Called by OBS on every front-end event."""
    if event == obs.OBS_FRONTEND_EVENT_SCENE_CHANGED:
        handle_scene_change()


def handle_scene_change():
    """Look up the current scene in _scene_map and load the snapshot."""
    if not _enabled:
        return

    current_scene_source = obs.obs_frontend_get_current_scene()
    if current_scene_source is None:
        return
    scene_name = obs.obs_source_get_name(current_scene_source)
    obs.obs_source_release(current_scene_source)

    obs.script_log(obs.LOG_DEBUG, f"Scene changed → '{scene_name}'")

    if scene_name in _scene_map:
        snap_id = _scene_map[scene_name]
        load_snapshot(snap_id)
    else:
        obs.script_log(obs.LOG_DEBUG, f"No XR18 mapping for scene '{scene_name}'.")


# ---------------------------------------------------------------------------
# Helpers for scene→snapshot mapping
# ---------------------------------------------------------------------------


def _build_scene_map_from_rows(settings):
    """Read the individual scene_name_N / snapshot_id_N pairs from *settings*
    and rebuild *_scene_map* + the JSON mirror."""
    global _scene_map, _scene_map_json
    new_map = {}
    for i in range(1, MAX_SCENE_ROWS + 1):
        name = obs.obs_data_get_string(settings, f"scene_name_{i}").strip()
        snap = obs.obs_data_get_int(settings, f"snapshot_id_{i}")
        if name and 1 <= snap <= 64:
            new_map[name] = snap
    _scene_map = new_map
    _scene_map_json = json.dumps(_scene_map, indent=2)
    obs.obs_data_set_string(settings, "scene_map_json", _scene_map_json)


def _build_scene_map_from_json(settings):
    """Parse the JSON text field and rebuild *_scene_map* + the row fields."""
    global _scene_map, _scene_map_json
    raw = obs.obs_data_get_string(settings, "scene_map_json").strip()
    if not raw:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        obs.script_log(obs.LOG_WARNING, f"Invalid JSON in mapping: {exc}")
        return
    if not isinstance(parsed, dict):
        obs.script_log(obs.LOG_WARNING, "JSON mapping must be an object.")
        return

    new_map = {}
    for name, snap in parsed.items():
        try:
            snap = int(snap)
        except (ValueError, TypeError):
            continue
        if 1 <= snap <= 64:
            new_map[str(name)] = snap
    _scene_map = new_map
    _scene_map_json = json.dumps(_scene_map, indent=2)

    # Mirror back into the row fields
    items = list(_scene_map.items())
    for i in range(1, MAX_SCENE_ROWS + 1):
        if i <= len(items):
            obs.obs_data_set_string(settings, f"scene_name_{i}", items[i - 1][0])
            obs.obs_data_set_int(settings, f"snapshot_id_{i}", items[i - 1][1])
        else:
            obs.obs_data_set_string(settings, f"scene_name_{i}", "")
            obs.obs_data_set_int(settings, f"snapshot_id_{i}", 0)


# ---------------------------------------------------------------------------
# OBS Script API
# ---------------------------------------------------------------------------


def script_description():
    return (
        "<h2>Behringer XR18 – Snapshot ↔ Scene Sync</h2>"
        "<p>Automatically loads an XR18 snapshot whenever the active OBS "
        "scene changes.</p>"
        "<p>Configure the mixer IP/port and map each OBS scene to a "
        "snapshot number (1-64).</p>"
    )


def script_defaults(settings):
    """Set sensible defaults the first time the script is added."""
    obs.obs_data_set_default_string(settings, "xr18_ip", "192.168.1.15")
    obs.obs_data_set_default_int(settings, "xr18_port", 10024)
    obs.obs_data_set_default_bool(settings, "enabled", True)
    obs.obs_data_set_default_string(settings, "scene_map_json", "{\n}")


def script_properties():
    """Build the properties UI shown in Tools → Scripts."""
    props = obs.obs_properties_create()

    # --- Connection settings ---
    obs.obs_properties_add_bool(props, "enabled", "Enable plugin")
    obs.obs_properties_add_text(
        props, "xr18_ip", "XR18 IP Address", obs.OBS_TEXT_DEFAULT
    )
    obs.obs_properties_add_int(props, "xr18_port", "XR18 OSC Port", 1, 65535, 1)

    # --- Scene → Snapshot rows ---
    obs.obs_properties_add_text(
        props, "_label_rows", "── Scene → Snapshot Mappings ──", obs.OBS_TEXT_INFO
    )

    # Fetch current OBS scene names for dropdown lists
    scene_names = []
    sources = obs.obs_frontend_get_scenes()
    if sources:
        for src in sources:
            scene_names.append(obs.obs_source_get_name(src))
        obs.source_list_release(sources)

    for i in range(1, MAX_SCENE_ROWS + 1):
        grp = obs.obs_properties_create()

        scene_list = obs.obs_properties_add_list(
            grp,
            f"scene_name_{i}",
            "Scene",
            obs.OBS_COMBO_TYPE_EDITABLE,
            obs.OBS_COMBO_FORMAT_STRING,
        )
        obs.obs_property_list_add_string(scene_list, "(none)", "")
        for sn in scene_names:
            obs.obs_property_list_add_string(scene_list, sn, sn)

        obs.obs_properties_add_int(grp, f"snapshot_id_{i}", "Snapshot #", 0, 64, 1)

        obs.obs_properties_add_group(
            props, f"mapping_{i}", f"Mapping {i}", obs.OBS_GROUP_NORMAL, grp
        )

    # --- Advanced: raw JSON editor ---
    obs.obs_properties_add_text(
        props, "_label_json", "── Advanced: JSON Mapping Editor ──", obs.OBS_TEXT_INFO
    )
    obs.obs_properties_add_text(props, "scene_map_json", "JSON", obs.OBS_TEXT_MULTILINE)

    return props


def script_update(settings):
    """Called whenever any setting is changed in the UI (or on load)."""
    global _xr18_ip, _xr18_port, _enabled, _scene_map_json

    _enabled = obs.obs_data_get_bool(settings, "enabled")
    _xr18_ip = obs.obs_data_get_string(settings, "xr18_ip") or "192.168.1.15"
    _xr18_port = obs.obs_data_get_int(settings, "xr18_port") or 10024

    _create_client()

    # Get the JSON currently sitting in the UI text box
    current_ui_json = obs.obs_data_get_string(settings, "scene_map_json").strip()

    # Detect if the user manually typed into the JSON box by comparing it
    # to the last generated state we have in memory.
    if current_ui_json != _scene_map_json.strip() and current_ui_json != "":
        # The user edited the JSON box; parse it and push the changes up to the UI rows.
        _build_scene_map_from_json(settings)
    else:
        # Otherwise, assume the user was using the UI rows. Read the rows and
        # push the changes down to the JSON box.
        _build_scene_map_from_rows(settings)

    obs.script_log(
        obs.LOG_INFO, f"Settings updated – {len(_scene_map)} mapping(s) active."
    )


def script_load(settings):
    """Called once when OBS loads the script."""
    obs.script_log(obs.LOG_INFO, "XR18 Snapshot Sync script loaded.")
    obs.obs_frontend_add_event_callback(on_event)


def script_unload():
    """Called when the script is removed or OBS shuts down."""
    obs.script_log(obs.LOG_INFO, "XR18 Snapshot Sync script unloaded.")
