import obspython as obs
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import urllib.parse
from pythonosc import udp_client

# ---------------------------------------------------------
# Global Configuration
# ---------------------------------------------------------
_xr18_ip = "192.168.1.15"
XR18_PORT = 10024
HTTP_PORT = 8080  # The dock will load http://localhost:8080
_client = None
_server = None
_server_thread = None


# ---------------------------------------------------------
# OSC Logic
# ---------------------------------------------------------
def _create_client():
    global _client
    _client = udp_client.SimpleUDPClient(_xr18_ip, XR18_PORT)


def load_snapshot(snap_id):
    if _client:
        try:
            _client.send_message("/-snap/load", int(snap_id))
            print(f"XR18: Loaded Snapshot {snap_id}")
        except:
            pass


# ---------------------------------------------------------
# Web Server (The Bridge)
# ---------------------------------------------------------
class DockHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Handle snapshot triggering from the Dock UI
        if self.path.startswith("/load?id="):
            query = urllib.parse.urlparse(self.path).query
            snap_id = urllib.parse.parse_qs(query).get("id", [None])[0]
            if snap_id:
                load_snapshot(snap_id)
            self.send_response(200)
            self.end_headers()
            return

        # Handle UI data request (Scenes + Mappings)
        if self.path == "/data":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()

            scenes = []
            sources = obs.obs_frontend_get_scenes()
            for s in sources:
                scenes.append(obs.obs_source_get_name(s))
            obs.source_list_release(sources)

            self.wfile.write(json.dumps({"scenes": scenes}).encode())
            return

        # Serve the UI (HTML/CSS/JS)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(self.get_html_content().encode())

    def log_message(self, format, *args):
        return  # Silent logs

    def get_html_content(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { background: #1a1a1a; color: white; font-family: sans-serif; padding: 10px; margin: 0; }
                .card { background: #2a2a2a; border-radius: 4px; padding: 10px; margin-bottom: 8px; border-left: 4px solid #3498db; }
                .scene-name { font-weight: bold; margin-bottom: 5px; font-size: 13px; }
                select { width: 100%; background: #333; color: white; border: 1px solid #444; padding: 5px; border-radius: 3px; }
                button { width: 100%; padding: 10px; background: #27ae60; border: none; color: white; font-weight: bold; border-radius: 4px; cursor: pointer; margin-bottom: 15px; }
                button:hover { background: #2ecc71; }
            </style>
        </head>
        <body>
            <button onclick="refresh()">⟳ Refresh Scene List</button>
            <div id="mapping-list">Loading...</div>

            <script>
                async function refresh() {
                    const res = await fetch('/data');
                    const data = await res.json();
                    const container = document.getElementById('mapping-list');
                    container.innerHTML = '';
                    
                    data.scenes.forEach(scene => {
                        const div = document.createElement('div');
                        div.className = 'card';
                        div.innerHTML = `<div class="scene-name">${scene}</div>
                            <select onchange="updateMapping('${scene}', this.value)">
                                <option value="0">(None)</option>
                                ${Array.from({length: 64}, (_, i) => `<option value="${i+1}">Snapshot ${i+1}</option>`).join('')}
                            </select>`;
                        container.appendChild(div);
                    });
                }
                function updateMapping(scene, id) {
                    // Logic to save mapping could go here (e.g., fetch('/save?scene=...'))
                    console.log("Mapped", scene, "to", id);
                }
                // When OBS switches scenes, the Python script handles the OSC, 
                // but this UI lets you set the ID.
                refresh();
            </script>
        </body>
        </html>
        """


def start_server():
    global _server, _server_thread
    _server = HTTPServer(("localhost", HTTP_PORT), DockHandler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()


# ---------------------------------------------------------
# OBS Script Hooks
# ---------------------------------------------------------
def on_event(event):
    if event == obs.OBS_FRONTEND_EVENT_SCENE_CHANGED:
        # In a full version, you'd lookup your saved mapping here
        # For now, let's just log it:
        source = obs.obs_frontend_get_current_scene()
        name = obs.obs_source_get_name(source)
        obs.obs_source_release(source)
        obs.script_log(obs.LOG_INFO, f"Scene Changed to: {name}")


def script_load(settings):
    _create_client()
    start_server()
    obs.obs_frontend_add_event_callback(on_event)


def script_unload():
    if _server:
        _server.shutdown()


def script_description():
    return "XR18 Sync Server running on http://localhost:8080"
