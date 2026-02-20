# obs-mixer-osc-plugin

**OBS Studio Python Script – Behringer XR18 Snapshot Sync via OSC**

Automatically loads a snapshot on a Behringer XR18 (X Air) mixer whenever the active scene changes in OBS. All settings (IP, port, scene→snapshot mappings) are configurable through the OBS Scripts UI.

## Features

- **Automatic snapshot loading** – triggers an XR18 snapshot recall on every OBS scene change
- **Per-scene mapping** – map up to 20 OBS scenes to XR18 snapshots (1–64) via dropdown rows in the UI
- **JSON mapping editor** – advanced users can paste or edit a JSON object directly for bulk configuration
- **Enable/disable toggle** – quickly turn the plugin on or off without removing it
- **Scene dropdown lists** – mapping rows auto-populate with your current OBS scene names

## Requirements

- **OBS Studio** with Python scripting support
- **Python 3** (configured in OBS under _Tools → Scripts → Python Settings_)
- **python-osc** (`pip install python-osc`)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Installation

1. Clone or download this repository.
2. In OBS, go to **Tools → Scripts**.
3. Set your Python install path under the **Python Settings** tab if not already configured.
4. Click **+** and add `obs_xr18_sync.py`.

## Configuration

Once the script is loaded, its settings appear in the Scripts window:

| Setting             | Default        | Description                                      |
| ------------------- | -------------- | ------------------------------------------------ |
| **Enable plugin**   | On             | Master on/off switch                             |
| **XR18 IP Address** | `192.168.1.15` | IP address of the Behringer XR18 on your network |
| **XR18 OSC Port**   | `10024`        | OSC port the mixer listens on                    |

### Scene → Snapshot Mappings

Use the **Mapping 1–20** rows to pair an OBS scene with a snapshot number (1–64). Each row provides:

- A **Scene** dropdown pre-filled with your current OBS scenes (also accepts manual text entry)
- A **Snapshot #** selector (0 = unused, 1–64 = valid snapshot)

### Advanced: JSON Mapping Editor

For bulk editing or more than 20 mappings, use the JSON text field. The format is:

```json
{
  "My OBS Scene": 1,
  "Another Scene": 12
}
```

When individual rows are populated they take precedence; the JSON field is used as a fallback when all rows are empty.

## How It Works

The script listens for the `OBS_FRONTEND_EVENT_SCENE_CHANGED` event. On each scene change it:

1. Reads the new scene name.
2. Looks it up in the scene→snapshot map.
3. Sends an OSC message `/-snap/load <index>` (0-based) to the XR18 via UDP.

## License

See [LICENSE](LICENSE) for details.
