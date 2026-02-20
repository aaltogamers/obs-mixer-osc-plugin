"""
OBS Studio Python Script – Behringer XR18 Snapshot Sync via OSC & Native Dock (PyQt6)
"""

import json
import socket
import time
import obspython as obs  # type: ignore

try:
    from PyQt6 import QtWidgets, QtCore, QtGui

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    obs.script_log(
        obs.LOG_WARNING,
        "PyQt6 is missing! Native dock will not load. Run: sudo apt install python3-pyqt6",
    )

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
_dock = None


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
    names = []
    obs.script_log(obs.LOG_INFO, f"Fetching snapshots from {ip}:{XR18_PORT}...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        sock.bind(("", 0))

        for i in range(1, 65):
            address = f"/-snap/{i:02d}/name"
            builder = OscMessageBuilder(address=address)
            sock.sendto(builder.build().dgram, (ip, XR18_PORT))
            time.sleep(0.005)

        while True:
            try:
                data, _ = sock.recvfrom(1024)
                try:
                    reply = OscMessage(data)
                except Exception:
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


def get_cached_snapshots():
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
# Native OBS Dock UI (PyQt6)
# ---------------------------------------------------------------------------
if PYQT_AVAILABLE:

    class XR18Dock(QtWidgets.QDockWidget):
        def __init__(self, parent=None):
            super().__init__("XR18 Snapshot Sync", parent)
            self.setObjectName("XR18_Snapshot_Sync_Dock")

            # FIX 2: Enforce a minimum width so the Pop-Out and Close buttons don't overlap
            self.setMinimumWidth(280)

            self.main_widget = QtWidgets.QWidget()
            self.main_layout = QtWidgets.QVBoxLayout()

            self.fetch_btn = QtWidgets.QPushButton("⟳ Sync XR18 Snapshots")
            font = self.fetch_btn.font()
            font.setBold(True)
            self.fetch_btn.setFont(font)
            self.fetch_btn.setMinimumHeight(35)

            self.fetch_btn.clicked.connect(self.on_fetch_clicked)
            self.main_layout.addWidget(self.fetch_btn)

            self.scroll = QtWidgets.QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.container = QtWidgets.QWidget()
            self.form_layout = QtWidgets.QFormLayout()
            self.container.setLayout(self.form_layout)
            self.scroll.setWidget(self.container)

            self.main_layout.addWidget(self.scroll)
            self.main_widget.setLayout(self.main_layout)
            self.setWidget(self.main_widget)

        def on_fetch_clicked(self):
            global _settings
            if not _settings:
                return
            ip = obs.obs_data_get_string(_settings, "xr18_ip") or "192.168.1.15"
            self.fetch_btn.setText("Fetching...")
            QtWidgets.QApplication.processEvents()

            fetched = fetch_snapshot_names(ip)
            if fetched:
                obs.obs_data_set_string(
                    _settings, "cached_snapshots", json.dumps(fetched)
                )
                self.populate_ui()

            self.fetch_btn.setText("⟳ Sync XR18 Snapshots")

        def populate_ui(self):
            global _settings
            if not _settings:
                return

            while self.form_layout.count():
                item = self.form_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            scene_names = []
            sources = obs.obs_frontend_get_scenes()
            if sources:
                for src in sources:
                    scene_names.append(obs.obs_source_get_name(src))
                obs.source_list_release(sources)

            current_snapshots = get_cached_snapshots()

            for sn in scene_names:
                setting_key = f"map_scene_{sn}"
                combo = QtWidgets.QComboBox()
                combo.addItem("(None)", 0)

                current_val = obs.obs_data_get_int(_settings, setting_key)
                current_idx = 0

                for idx, (snap_id, snap_name) in enumerate(current_snapshots):
                    combo.addItem(f"{snap_id:02d}: {snap_name}", snap_id)
                    if snap_id == current_val:
                        current_idx = idx + 1

                combo.setCurrentIndex(current_idx)

                combo.currentIndexChanged.connect(
                    lambda index, key=setting_key, cb=combo: obs.obs_data_set_int(
                        _settings, key, cb.itemData(index)
                    )
                )

                self.form_layout.addRow(sn, combo)


def setup_dock():
    global _dock
    if not PYQT_AVAILABLE or _dock is not None:
        return

    app = QtWidgets.QApplication.instance()
    if not app:
        return

    main_window = None
    for widget in app.topLevelWidgets():
        if isinstance(widget, QtWidgets.QMainWindow):
            main_window = widget
            break

    if not main_window:
        return

    _dock = XR18Dock(main_window)
    main_window.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, _dock)

    # FIX 1: Aggressively hunt for the Docks menu instead of relying on exact object name
    docks_menu = None
    for menu in main_window.findChildren(QtWidgets.QMenu):
        menu_title = menu.title().replace(
            "&", ""
        )  # Handle alt-key shortcuts like "&Docks"
        if menu.objectName() == "viewMenuDocks" or "Docks" in menu_title:
            docks_menu = menu
            break

    if docks_menu:
        toggle_action = _dock.toggleViewAction()
        toggle_action.setText("XR18 Snapshot Sync")
        docks_menu.addAction(toggle_action)
    else:
        obs.script_log(
            obs.LOG_WARNING,
            "Could not locate the 'Docks' menu to add the toggle action.",
        )

    _dock.populate_ui()


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
# OBS Script API
# ---------------------------------------------------------------------------
def script_description():
    return (
        "<h2>Behringer XR18 – Snapshot Sync</h2>"
        "<p>Loads an XR18 snapshot whenever the active OBS scene changes.</p>"
        "<hr/>"
        "<p><strong>Note:</strong> Mappings are now managed via a native OBS Dock. "
        "You can show or hide it using the <strong>Docks</strong> menu at the top of OBS.</p>"
    )


def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "xr18_ip", "192.168.1.15")
    obs.obs_data_set_default_bool(settings, "enabled", True)


def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_bool(props, "enabled", "Enable plugin")
    obs.obs_properties_add_text(
        props, "xr18_ip", "XR18 IP Address", obs.OBS_TEXT_DEFAULT
    )
    return props


def script_update(settings):
    global _xr18_ip, _enabled, _settings
    _settings = settings
    _enabled = obs.obs_data_get_bool(settings, "enabled")
    _xr18_ip = obs.obs_data_get_string(settings, "xr18_ip") or "192.168.1.15"

    _create_client()

    if PYQT_AVAILABLE and _dock is None:
        setup_dock()


def script_load(settings):
    global _settings
    _settings = settings
    obs.obs_frontend_add_event_callback(on_event)


def script_unload():
    global _dock
    if _dock:
        _dock.setParent(None)
        _dock.deleteLater()
        _dock = None
