"""
OBS Studio Python Script – Behringer XR18 Snapshot Sync via OSC

Automatically loads a snapshot on a Behringer XR18 (X Air) whenever
the active scene changes in OBS. All settings, including dynamic
snapshot fetching, are configured in the Scripts UI.

Requirements:
    pip install python-osc
"""

import json
import socket
import time
import obspython as obs  # type: ignore
from pythonosc import udp_client
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import OscMessageBuilder

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_client = None
_xr18_ip = "192.168.1.15"
XR18_PORT = 10024
_enabled = True

_settings = None


# ---------------------------------------------------------------------------
# OSC / Network Helpers
# ---------------------------------------------------------------------------


def _create_client():
    global _client
    try:
        _client = udp_client.SimpleUDPClient(_xr18_ip, XR18_PORT)
    except Exception:
        _client = None


def fetch_snapshot_names(ip):
    """Sends OSC requests to fetch all 64 snapshot names from the XR18."""
    names = []
    obs.script_log(obs.LOG_INFO, f"Fetching snapshots from {ip}:{XR18_PORT}...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        sock.bind(("", 0))

        # Burst out requests with a small delay.
        for i in range(1, 65):
            address = f"/-snap/{i:02d}/name"
            builder = OscMessageBuilder(address=address)
            sock.sendto(builder.build().dgram, (ip, XR18_PORT))
            time.sleep(0.005)

        # Read incoming responses until the socket times out
        while True:
            try:
                data, _ = sock.recvfrom(1024)
                try:
                    reply = OscMessage(data)
                except Exception as parse_exc:
                    obs.script_log(
                        obs.LOG_INFO, f"Skipped malformed packet: {parse_exc}"
                    )
                    continue

                addr = reply.address
                if addr.startswith("/-snap/") and addr.endswith("/name"):
                    parts = addr.split("/")
                    if len(parts) >= 4:
                        idx_str = parts[2]
                        if idx_str.isdigit() and reply.params:
                            snap_name = str(reply.params[0]).strip()
                            if snap_name:
                                names.append((int(idx_str), snap_name))
            except socket.timeout:
                break

        sock.close()
    except Exception as exc:
        obs.script_log(obs.LOG_ERROR, f"Network error fetching snapshots: {exc}")

    names.sort(key=lambda x: x[0])

    if names:
        obs.script_log(obs.LOG_INFO, f"Success! Fetched {len(names)} snapshots.")
    else:
        obs.script_log(
            obs.LOG_ERROR,
            "No snapshots found. Connection timed out or blocked by firewall.",
        )

    return names


def load_snapshot(snapshot_id):
    if _client is None:
        return

    osc_index = int(snapshot_id)
    if osc_index < 1 or osc_index > 64:
        return

    try:
        _client.send_message("/-snap/load", osc_index)
        obs.script_log(obs.LOG_INFO, f"XR18 ← /-snap/load {osc_index}")
    except Exception as exc:
        obs.script_log(obs.LOG_ERROR, f"OSC send failed: {exc}")


# ---------------------------------------------------------------------------
# Data Handlers
# ---------------------------------------------------------------------------


def get_cached_snapshots():
    """Safely pulls the most recently fetched snapshots from OBS internal data."""
    global _settings
    if _settings is not None:
        cached = obs.obs_data_get_string(_settings, "cached_snapshots")
        if cached:
            try:
                return [tuple(item) for item in json.loads(cached)]
            except Exception:
                pass
    return []


# ---------------------------------------------------------------------------
# OBS Event Handling
# ---------------------------------------------------------------------------


def on_event(event):
    if event == obs.OBS_FRONTEND_EVENT_SCENE_CHANGED:
        handle_scene_change()


def handle_scene_change():
    if not _enabled or _settings is None:
        return

    current_scene_source = obs.obs_frontend_get_current_scene()
    if current_scene_source is None:
        return

    scene_name = obs.obs_source_get_name(current_scene_source)
    obs.obs_source_release(current_scene_source)

    setting_key = f"map_scene_{scene_name}"
    snap_id = obs.obs_data_get_int(_settings, setting_key)

    if snap_id > 0:
        load_snapshot(snap_id)


# ---------------------------------------------------------------------------
# OBS Script API & UI
# ---------------------------------------------------------------------------


def script_description():
    return (
        "<h2>Behringer XR18 – Snapshot Sync</h2>"
        "<p>Automatically loads an XR18 snapshot whenever the active OBS scene changes.</p>"
        "<hr/>"
        "<p><strong>Instructions:</strong></p>"
        "<ol>"
        "<li>Set your XR18 IP.</li>"
        "<li>Click <strong>Fetch Snapshots from XR18</strong> to populate the menus.</li>"
        "<li>Use the dropdowns to assign snapshots.</li>"
        "<li><strong>IMPORTANT:</strong> If you add, rename, or delete scenes in OBS, you must click the native <strong>Reload Scripts (↺)</strong> icon at the bottom-left of this window to update the scene list!</li>"
        "</ol>"
    )


def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "xr18_ip", "192.168.1.15")
    obs.obs_data_set_default_bool(settings, "enabled", True)


def on_fetch_snapshots(props, prop):
    """Callback for the 'Fetch Snapshots' button."""
    global _settings
    if _settings is not None:
        ip = obs.obs_data_get_string(_settings, "xr18_ip") or "192.168.1.15"
        fetched = fetch_snapshot_names(ip)
        if fetched:
            # Hard-save the fetched list to OBS settings immediately
            obs.obs_data_set_string(_settings, "cached_snapshots", json.dumps(fetched))

            # Actively reach into the UI to update the existing dropdowns in place
            scene_names = []
            sources = obs.obs_frontend_get_scenes()
            if sources:
                for src in sources:
                    scene_names.append(obs.obs_source_get_name(src))
                obs.source_list_release(sources)

            for sn in scene_names:
                setting_key = f"map_scene_{sn}"
                p = obs.obs_properties_get(props, setting_key)
                if p:
                    obs.obs_property_list_clear(p)
                    obs.obs_property_list_add_int(p, "(None)", 0)
                    for snap_idx, snap_name in fetched:
                        obs.obs_property_list_add_int(
                            p, f"{snap_idx:02d}: {snap_name}", snap_idx
                        )

    # Returning True tells OBS to paint our in-place UI changes
    return True


def script_properties():
    """Builds the UI from scratch."""
    props = obs.obs_properties_create()

    obs.obs_properties_add_bool(props, "enabled", "Enable plugin")
    obs.obs_properties_add_text(
        props, "xr18_ip", "XR18 IP Address", obs.OBS_TEXT_DEFAULT
    )

    # Action Button
    obs.obs_properties_add_button(
        props, "btn_fetch", "Fetch Snapshots from XR18", on_fetch_snapshots
    )

    obs.obs_properties_add_text(
        props, "_label_mappings", "── Scene to Snapshot Mappings ──", obs.OBS_TEXT_INFO
    )

    # Ask OBS for the current master list of scenes
    scene_names = []
    sources = obs.obs_frontend_get_scenes()
    if sources:
        for src in sources:
            scene_names.append(obs.obs_source_get_name(src))
        obs.source_list_release(sources)

    # Pull the most recent safe snapshot data from OBS settings
    current_snapshots = get_cached_snapshots()

    # Build a dropdown for every scene currently in OBS
    for sn in scene_names:
        setting_key = f"map_scene_{sn}"
        p = obs.obs_properties_add_list(
            props, setting_key, sn, obs.OBS_COMBO_TYPE_LIST, obs.OBS_COMBO_FORMAT_INT
        )

        obs.obs_property_list_add_int(p, "(None)", 0)

        # Populate the dropdown with whatever is cached
        for snap_idx, snap_name in current_snapshots:
            obs.obs_property_list_add_int(p, f"{snap_idx:02d}: {snap_name}", snap_idx)

    return props


def script_update(settings):
    global _xr18_ip, _enabled, _settings

    _settings = settings
    _enabled = obs.obs_data_get_bool(settings, "enabled")
    _xr18_ip = obs.obs_data_get_string(settings, "xr18_ip") or "192.168.1.15"

    _create_client()


def script_load(settings):
    global _settings
    _settings = settings
    obs.obs_frontend_add_event_callback(on_event)
