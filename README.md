# obs-mixer-osc-plugin

**OBS Studio Python Script: Behringer XR18 Snapshot Sync**

Automatically switches to snapshot on your Behringer XR18 mixer whenever the active OBS scene changes.

---

## Quick Start

1. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```
2. In OBS, go to **Tools → Scripts** and add `obs_xr18_sync.py`.

- If on Windows -> Make sure to add the Python Install Path\* in Tools -> Scripts -> Python Settings

3. Set your XR18 IP address in the script settings. You can see this from the X-AIR-Edit app on the Setup -> Connection tab next to the model name
4. Click **Fetch Snapshots from XR18** to load snapshot names.
5. Assign snapshots to your OBS scenes using the dropdowns.
6. Enable the plugin (toggle in settings).

**Note:** If you add/rename/delete scenes, click the **Reload Scripts (↺)** button in OBS to update the scene list.

---

## How it Works

- On every scene change, the script checks if a snapshot is mapped to the new scene and sends an OSC recall to the XR18.

---

## Requirements

- OBS Studio with Python scripting
- Python 3 (tested with Python 3.12)
- `python-osc` (see requirements.txt)

---

## License

See [LICENSE](LICENSE).
