# SnapFrame – Turn Any Old Tablet or iPad into a Smart Digital Photo Frame for Home Assistant

**SnapFrame** is a self-hosted Home Assistant add-on that turns an old iPad, Android tablet, or any device with a browser into a beautiful wall-mounted **digital photo frame** — no cloud subscription, no proprietary frame hardware, no monthly fee. Point any browser at it and it becomes a fullscreen slideshow of your family photos, straight from your own Samba/CIFS share.

It watches an SMB share for photos (including **HEIC/HEIF from iPhone**), automatically converts them to JPG, and serves a fast, minimal, swipe-friendly slideshow with albums, EXIF date/GPS overlays, night mode, multi-language UI, and — new — a **motion-triggered weather screen** for a "smart mirror"-style morning briefing.

If you have a retired iPad, an old Android tablet, or any spare touchscreen gathering dust in a drawer, this is the easiest way to give it a second life as a proper **digital photo frame** running entirely on your local network.

---

## Features

- 📸 **Automatic HEIC → JPG conversion** – scans your SMB share on a configurable interval and converts every new HEIC/HEIF file (e.g. photos AirDropped or synced from an iPhone)
- 🖼️ **Fullscreen slideshow** – clean, minimal web UI that works great on an old iPad, Android tablet, or any modern browser mounted on a wall
- 📂 **Albums** – subfolders are automatically shown as albums with cover thumbnails and photo counts
- 📅 **EXIF overlay** – date and GPS location (via Nominatim reverse geocoding) shown on each photo
- ⬆️ **Web upload** – upload photos directly from a phone's browser without needing SMB access; supports multiple files and creating new albums on the fly
- 🌤️ **Motion-triggered weather screen** – trigger "weather mode" from a Home Assistant motion sensor (e.g. in the morning) so the slideshow inserts a nicely designed current-weather + today's forecast screen every few photos
- 🌙 **Night mode** – configurable sleep schedule blanks the screen (plain black or an animated starry sky) to save your display and avoid a glowing photo frame at 3am
- 🌍 **Multi-language UI** – Slovak, English, and German out of the box
- ⚙️ **In-app settings** – night-mode theme can be changed directly from the slideshow, no need to touch the Home Assistant add-on configuration
- 🔄 **Background thumbnail pre-generation** – thumbnails are generated in the background after each scan; no waiting on first open, fast even with thousands of photos
- 🗑️ **Trash** – long-press any photo to move it to `_kos/` subfolder (recoverable via SMB)
- 👆 **Swipe gestures** – left/right to navigate, swipe down to return to album selection
- 🔐 **Optional HTTP Basic Auth** – password-protect the web interface
- 📡 **REST API** – `/status`, `/scan`, `/upload`, `/weather-mode/*` endpoints for Home Assistant automations

> Looking for keywords: *Home Assistant photo frame*, *digital picture frame add-on*, *HEIC to JPG converter for Home Assistant*, *iPad photo frame without iCloud*, *self-hosted Aura/Skylight/Nixplay alternative*, *old tablet recycle project*, *smart mirror weather display*. If that's what brought you here — you're in the right place.

---

## Requirements

- Home Assistant OS or Supervised (needs `full_access` / CIFS mount support — see [Security notes](#security-notes))
- A Samba/CIFS share accessible from your HA instance (e.g. a NAS, a Windows PC share, or another HA Samba add-on)
- Any old tablet, iPad, or device with a modern browser to display the slideshow — it doesn't need to be fast, it just needs a screen

---

## Installation

SnapFrame is not published in the official Home Assistant add-on store (it needs `full_access`/`SYS_ADMIN` to mount CIFS, which isn't allowed for store add-ons — see [Security notes](#security-notes)). You can install it either by adding this GitHub repo as a **custom add-on repository** (recommended — gives you one-click updates), or as a **local add-on**.

### Method A — Add this GitHub repo as a custom repository (recommended)

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Tap the **⋮** (three dots) menu in the top-right corner → **Repositories**
3. Paste the repository URL and click **Add**:
   ```
   https://github.com/emo546/ha-snapframe
   ```
4. Close the dialog and refresh. A new **"SnapFrame Add-ons"** section appears in the store with **SnapFrame** in it.
5. Open it, click **Install**, then continue with [Step 3 below](#step-3--install-and-configure).

Whenever a new version is pushed to the repo, Home Assistant shows an **Update** button on the add-on — no manual file copying.

> This works because the repo has a `repository.yaml` at its root and the add-on lives in the `snapframe/` subfolder — the layout Home Assistant expects for a custom repository.

### Method B — Local add-on (manual copy)

Use this if you'd rather not add a repository, or want to hack on the files directly.

#### Step 1 — Get the files onto your Home Assistant instance

The add-on must live at `/addons/snapframe/` on the machine running Home Assistant (with `config.yaml` directly inside it). In this repo the add-on files are in the `snapframe/` subfolder, so copy **the contents of that subfolder**, not the whole repo. Pick whichever is easiest:

**Option A – Samba (easiest if you already use the HA Samba add-on)**
1. Connect to `\\YOUR_HA_IP\addons\` from your computer's file explorer
2. Create a new folder named `snapframe`
3. Copy the contents of this repo's `snapframe/` folder into it (so you end up with `/addons/snapframe/config.yaml`, etc.)

**Option B – SSH / Terminal add-on (recommended if you're comfortable with a shell)**
```bash
cd /tmp
git clone https://github.com/emo546/ha-snapframe
cp -r ha-snapframe/snapframe /addons/snapframe
```

**Option C – Studio Code Server add-on**
1. Install the "Studio Code Server" add-on from the store and open it
2. Open a terminal inside the code editor and run the same commands as above

#### Step 2 — Register the local add-on repository

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Tap the **⋮** (three dots) menu in the top-right corner → **Check for updates** (or just refresh the page)
3. A new **"Local add-ons"** section should now appear at the top of the store, showing SnapFrame

If it doesn't show up, double-check the folder is exactly `/addons/snapframe/` and contains `config.yaml` at its root.

### Step 3 — Install and configure

1. Open **"SnapFrame – Turn Any Old Tablet into a Smart Digital Photo Frame"** from Local add-ons and click **Install** (this builds the Docker image — can take a few minutes on a Raspberry Pi)
2. Go to the **Configuration** tab and fill in at minimum: `smb_server`, `smb_share`, `smb_username`, `smb_password` (see [Configuration](#configuration) below for everything else)
3. Click **Save**
4. Go to the **Info** tab and click **Start**
5. Check the **Log** tab — you should see `CIFS pripojené úspešne` (CIFS mounted successfully). If not, see [Troubleshooting](#troubleshooting)

### Step 4 — Open the slideshow on your old tablet/iPad

Navigate to `http://YOUR_HA_IP:8099` in the device's browser. On iPad/iOS Safari, tap **Share → Add to Home Screen** so it launches fullscreen without browser chrome, then leave the device permanently plugged in and mounted on a wall or stand.

You can also embed it as an `iframe` panel in your Lovelace dashboard if you'd rather view it inside Home Assistant itself.

---

## Configuration

| Option | Default | Description |
|---|---|---|
| `smb_server` | `192.168.1.100` | IP address or hostname of your SMB/CIFS server |
| `smb_share` | `Photos` | SMB share name |
| `smb_username` | *(required)* | SMB username |
| `smb_password` | *(required)* | SMB password |
| `watch_folder` | `/sambamount/upload` | Path inside the mounted share to watch for new HEIC files |
| `output_folder` | `/sambamount/converted` | Path inside the mounted share where converted JPGs are stored |
| `delete_original` | `true` | Delete original HEIC after successful conversion |
| `jpg_quality` | `92` | JPEG quality for converted full-size photos (1–100) |
| `thumb_quality` | `82` | JPEG quality for cached thumbnails (1–100) |
| `thumb_max_px` | `1024` | Longest edge in pixels for thumbnails (256–3840) |
| `scan_interval_hours` | `12` | How often to scan the watch folder (1–168 h) |
| `slideshow_seconds` | `30` | Seconds each photo is shown (3–300) |
| `web_port` | `8099` | Port for the web interface |
| `basic_auth_user` | *(empty)* | Username for HTTP Basic Auth; leave empty to disable |
| `basic_auth_password` | *(empty)* | Password for HTTP Basic Auth |
| `language` | `sk` | UI language: `sk`, `en`, or `de` |
| `sleep_start` | *(empty)* | Night mode start time, e.g. `23:00`; leave empty to disable |
| `sleep_end` | *(empty)* | Night mode end time, e.g. `07:00`; leave empty to disable |
| `weather_photo_interval` | `8` | How many photos to show between weather screens while weather mode is active (2–50) |
| `weather_mode_duration_minutes` | `120` | How long weather mode stays active after being triggered via `/weather-mode/on` (5–720) |

### Example configuration

```yaml
smb_server: "192.168.1.50"
smb_share: "MediaShare"
smb_username: "photouser"
smb_password: "yourpassword"
watch_folder: "/sambamount/iPhone/upload"
output_folder: "/sambamount/slideshow"
delete_original: true
jpg_quality: 92
thumb_quality: 82
thumb_max_px: 1024
scan_interval_hours: 12
slideshow_seconds: 20
web_port: 8099
basic_auth_user: ""
basic_auth_password: ""
language: "en"
sleep_start: "23:00"
sleep_end: "07:00"
weather_photo_interval: 8
weather_mode_duration_minutes: 120
```

Most of the above (except SMB credentials) can also be changed later — night-mode theme (black vs. starry sky) is even adjustable directly from the slideshow via the ⚙ settings icon, without touching the add-on config at all.

---

## Folder structure on the SMB share

```
your-smb-share/
├── upload/              ← drop HEIC files here (watch_folder)
└── slideshow/           ← converted JPGs are stored here (output_folder)
    ├── Holidays/        ← subfolder = album
    │   ├── IMG_001.jpg
    │   └── IMG_002.jpg
    ├── Family/
    │   └── ...
    ├── _kos/            ← trash (photos moved here via long-press)
    └── _thumbs/         ← auto-generated thumbnail cache (do not delete manually)
```

Albums are subfolders of `output_folder`. You can create them manually via SMB, or use the **web upload** form to create them on the fly.

---

## Usage

### Slideshow

Open `http://YOUR_HA_IP:8099` on your tablet/iPad (or any browser).

1. **Select order** – Chronological or Random
2. **Select album** – tap any album, or "All photos"
3. The slideshow starts immediately, with photos cross-fading using a mix of subtle pan/zoom/slide transitions

### Gestures (touch)

| Gesture | Action |
|---|---|
| Swipe left | Next photo |
| Swipe right | Previous photo |
| Swipe down | Back to album selection |
| Long press (0.75 s) | Move current photo to trash |

### Settings (⚙)

Tap the gear icon in the top-right corner of the album selection screen to open in-app settings. Currently this lets you switch the night-mode screen between a plain black background and an animated starry sky with occasional shooting stars — saved per device via `localStorage`, no restart required.

### Night mode

If `sleep_start` / `sleep_end` are configured, the screen automatically blanks during those hours instead of showing photos — handy if the frame is in a bedroom. Choose between plain black or the starry-sky theme in Settings.

### Web upload

At the bottom of the album selection screen, tap **"↑ Upload photos"** to expand the upload form:

1. Choose a **target album** from the dropdown (existing albums), or select **"— New album… —"** and type a name
2. Tap **"Select files"** – on iPhone this opens the Photos app; you can select multiple photos
3. Tap **"Upload"** – files are uploaded one by one with a progress indicator
4. HEIC files are converted to JPG on upload; JPG and PNG files are saved as-is

> **Location accuracy note:** iOS/Safari can strip or reduce the precision of GPS EXIF data on photos picked through a web upload form, for privacy reasons — you may see only the country/region instead of a city. The app now shows a hint about this directly in the upload form. If you want full, precise location on every photo, upload via the SMB share (Files app, Finder, or drag-and-drop) or AirDrop instead of the browser picker — those paths preserve the original file untouched. See [Troubleshooting](#troubleshooting) for more detail.

### Manual scan

Tap **"↻ Scan now"** on the album selection screen to trigger an immediate scan of the `watch_folder` without waiting for the next scheduled interval.

---

## Weather mode (motion-triggered morning briefing)

SnapFrame can turn into a lightweight "smart mirror" in the morning: when a **motion sensor** you already have in Home Assistant detects movement, an automation tells SnapFrame to start inserting a nicely designed **current weather + today's forecast** screen every few photos, for as long as you configure (`weather_mode_duration_minutes`, default 2 hours).

SnapFrame itself never talks to the Home Assistant API — it stays a simple, low-privilege web server. Instead, **you** create one or two small Home Assistant automations that push the trigger and the weather data to it over plain REST calls. This keeps the add-on's permissions exactly as they are today.

### How it fits together

```
binary_sensor.motion (morning) ──▶ Automation ──▶ POST /weather-mode/on   (SnapFrame)
weather.home (state change / every 30 min) ──▶ Automation ──▶ POST /weather-update (SnapFrame)
```

While weather mode is active, the slideshow inserts one weather screen after every `weather_photo_interval` photos (default: every 8 photos), showing a big weather icon, current temperature, condition text (translated to your UI language), and today's forecast high/low — then returns to normal photos automatically.

### 1. Add a `rest_command` for each call

In your Home Assistant `configuration.yaml` (replace `192.168.1.x` with your SnapFrame add-on's IP/hostname and port):

```yaml
rest_command:
  snapframe_weather_mode_on:
    url: "http://192.168.1.x:8099/weather-mode/on"
    method: POST

  snapframe_weather_update:
    url: "http://192.168.1.x:8099/weather-update"
    method: POST
    content_type: "application/json"
    payload: >
      {
        "temperature": {{ state_attr('weather.home', 'temperature') if state_attr('weather.home', 'temperature') is not none else 'null' }},
        "condition": "{{ states('weather.home') }}",
        "humidity": {{ state_attr('weather.home', 'humidity') if state_attr('weather.home', 'humidity') is not none else 'null' }},
        "hourly": {{ hourly | default([], true) | tojson }}
      }
```

Replace `weather.home` with your own weather entity (any weather integration works — Met.no, OpenWeatherMap, AccuWeather, etc.).

The current temperature, condition and humidity are read straight from the weather entity's state. The `hourly` field (next ~12 hours) is passed in as a variable from the automation below — SnapFrame renders a small hourly-forecast strip from it and auto-derives today's high/low from those hours (so you don't need to send `forecast_high`/`forecast_low` separately, though you still can if you prefer).

### 2. Automation: turn weather mode on when motion is detected in the morning

```yaml
automation:
  - alias: "SnapFrame – enable weather mode on morning motion"
    trigger:
      - platform: state
        entity_id: binary_sensor.hallway_motion
        to: "on"
    condition:
      - condition: time
        after: "06:00:00"
        before: "10:00:00"
    action:
      - service: rest_command.snapframe_weather_mode_on
```

### 3. Automation: keep the weather data fresh

This automation fetches the hourly forecast via `weather.get_forecasts` and passes both the current data and the next 12 hours to SnapFrame:

```yaml
automation:
  - alias: "SnapFrame – push weather update"
    trigger:
      - platform: time_pattern
        minutes: "/30"
    action:
      - service: weather.get_forecasts
        target:
          entity_id: weather.home
        data:
          type: hourly
        response_variable: fc
      - service: rest_command.snapframe_weather_update
        data:
          hourly: "{{ fc['weather.home'].forecast[:12] }}"
```

> **Why the extra `weather.get_forecasts` step?** Recent Home Assistant versions removed the `forecast` attribute from the weather entity's state — the forecast now has to be fetched explicitly via the `weather.get_forecasts` action, which returns it into `response_variable`. We take the first 12 hourly entries and hand them to SnapFrame. If your weather integration only offers a daily forecast, use `type: daily` instead (the strip will then show upcoming days rather than hours).

That's it — no token, no `homeassistant_api` permission, no entity IDs hard-coded into the add-on. You can freely change which motion sensor or weather entity triggers it, or add your own conditions (e.g. only on weekdays), entirely from Home Assistant's automation editor.

To turn weather mode off early (e.g. from another automation, or a script tied to a "goodnight" scene), call `rest_command` against `POST /weather-mode/off` the same way.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Slideshow web interface |
| `GET` | `/albums` | JSON list of albums with photo counts |
| `GET` | `/photos?album=X&order=date\|random` | JSON list of photo paths |
| `GET` | `/thumb/<path>` | Cached thumbnail (JPEG, max `thumb_max_px` px) |
| `GET` | `/photo/<path>` | Full-size photo |
| `GET` | `/exif/<path>` | JSON with `date` and `location` strings |
| `GET` | `/album-cover/<album>` | Thumbnail of the first photo in album |
| `POST` | `/delete/<path>` | Move photo to `_kos/` trash folder |
| `POST` | `/upload` | Upload a file (`multipart/form-data`: `file`, `album`) |
| `POST` | `/scan` | Trigger immediate scan |
| `GET` | `/status` | JSON with scan stats and thumbnail pre-generation progress |
| `POST` | `/weather-mode/on` | Activate weather mode for `weather_mode_duration_minutes` |
| `POST` | `/weather-mode/off` | Deactivate weather mode immediately |
| `POST` | `/weather-update` | Push current weather data (JSON body, see [Weather mode](#weather-mode-motion-triggered-morning-briefing)) |
| `GET` | `/weather` | JSON with weather-mode status and the last pushed weather data |

### `/status` response example

```json
{
  "last_scan": "2025-06-15 08:02:44",
  "last_scan_ago": "3.2 hours",
  "next_scan": "2025-06-15 20:02:44",
  "next_scan_in": "8.8 hours",
  "converted_total": 47,
  "scan_pending": false,
  "thumbs": {
    "running": true,
    "total": 3500,
    "done": 1240,
    "percent": 35
  }
}
```

### `/weather-update` request body

```json
{
  "temperature": 21.4,
  "condition": "partlycloudy",
  "forecast_high": 24,
  "forecast_low": 14,
  "humidity": 55,
  "hourly": [
    { "datetime": "2026-07-13T14:00:00+00:00", "temperature": 21, "condition": "sunny" },
    { "datetime": "2026-07-13T15:00:00+00:00", "temperature": 23, "condition": "partlycloudy" }
  ]
}
```

`condition` (and each `hourly[].condition`) should be one of the standard [Home Assistant weather conditions](https://www.home-assistant.io/integrations/weather/) (`sunny`, `cloudy`, `rainy`, `snowy`, `partlycloudy`, …) so it maps to a matching icon and translated label in the UI. Unknown conditions fall back to a generic icon.

- All fields are optional. If `hourly` is present (up to 12 entries are used), SnapFrame renders an hourly-forecast strip (time · icon · temperature) below the current conditions, and — when `forecast_high`/`forecast_low` are omitted — derives today's high/low from those hourly temperatures.
- `hourly[].datetime` accepts any ISO-8601 timestamp (the format Home Assistant's `weather.get_forecasts` returns); only the `HH:MM` part is shown. On narrow screens the strip samples every 2nd hour to stay readable.

---

## How it works

```
iPhone / tablet Photos app
      │  (SMB or web upload)
      ▼
 watch_folder/          ← watcher.py polls every N hours
      │  (HEIC → JPG conversion, EXIF preserved)
      ▼
 output_folder/
      │
      ├── Background thread: generate _thumbs/ for all photos
      │
      └── webserver.py (Waitress/Flask)
              │
              ▼
         Browser / old tablet
         (slideshow, upload UI, weather mode)
              ▲
              │ REST calls (weather-mode/on, weather-update)
     Home Assistant automations
     (motion sensor, weather entity)
```

- **`watcher.py`** – main process; mounts SMB share, runs scan loop, spawns webserver thread
- **`webserver.py`** – Flask app served by Waitress (8 threads); handles all HTTP routes and renders the slideshow UI
- **`state.py`** – shared in-process state (scan timestamps, thumbnail progress, manual scan flag, weather-mode status and cached weather data)

### Thumbnail caching

Thumbnails are stored in `output_folder/_thumbs/` on the SMB share. They are generated:
1. **On first request** (on-demand) if not yet cached
2. **In bulk** after every scan in a background thread – this pre-warms the cache so the slideshow is fast even for large collections (3000+ photos)

On the first ever run with an existing photo collection, pre-generation runs in the background. The slideshow is accessible immediately; photos without a cached thumbnail temporarily serve the full-size image as fallback.

### EXIF and GPS

EXIF metadata is read from the JPG files. GPS coordinates are reverse-geocoded via [Nominatim / OpenStreetMap](https://nominatim.openstreetmap.org/) with a polite 1-request-per-location rate (results are cached persistently in `/data/geocode_cache.json`).

---

## Troubleshooting

**The addon fails to start / SMB mount fails**
- Verify `smb_server`, `smb_share`, `smb_username`, `smb_password` in configuration
- Make sure the SMB share uses protocol version 3.0 (most modern NAS devices do)
- Check the addon log for the exact mount error

**Photos are not being converted**
- Check that the HEIC files land in `watch_folder` (not a subfolder of it)
- Tap "↻ Scan now" to trigger an immediate scan
- Check the addon log for conversion errors

**The web interface does not load**
- Confirm `web_port` (default 8099) is not blocked by a firewall
- Check the addon log – if you see `invalid literal for int()` errors, re-save your configuration to write the new fields

**Thumbnails are slow on first open**
- Normal behaviour for large collections; pre-generation runs in the background
- Check `/status` → `thumbs.percent` to see progress

**`Task queue depth is N` warnings in logs**
- Waitress warning that more requests are queued than can be served immediately
- Usually caused by SMB latency during thumbnail generation; resolves once pre-generation completes

**Photos uploaded via the web form only show a country/region, not a full city location**
- This is expected on iOS/Safari: for privacy reasons, iOS can strip or heavily reduce the precision of the GPS data embedded in a photo when it's picked through a web page's file upload form (`<input type="file">`), even though the app itself never touches or trims any EXIF data it receives.
- SnapFrame's server-side code copies whatever EXIF it's given untouched, so this cannot be fixed from the add-on side — it happens on the device before the file ever reaches SnapFrame.
- Workaround: upload those photos via the SMB share instead (copy from Files/Finder, or drag-and-drop onto the share), or AirDrop them to a computer first and copy from there — both preserve the original file, including full-precision GPS.

**Weather screen never appears / motion doesn't trigger it**
- Confirm the Home Assistant automation actually fired: check **Settings → Automations → (your automation) → Traces**
- Call `curl -X POST http://YOUR_HA_IP:8099/weather-mode/on` manually and then check `GET /weather` — if `active` becomes `true`, the add-on side is working and the issue is in the automation/motion sensor
- Make sure at least one `/weather-update` call has succeeded — without weather data, the slideshow has nothing to show and stays on normal photos even while weather mode is technically "active"

---

## Security notes

- The addon requires `full_access: true` and `SYS_ADMIN` privilege to mount CIFS shares inside the container. This is standard for any addon that needs to call `mount`. It **cannot** be installed from the official HA addon store for this reason.
- SMB credentials are stored in HA's encrypted addon configuration and are never logged.
- The web interface has **no authentication by default** – it is intended for use on a trusted local network. Enable `basic_auth_user` / `basic_auth_password` if you expose it externally.
- The `/weather-mode/*` and `/weather-update` endpoints have no authentication beyond whatever `basic_auth_user`/`basic_auth_password` you've set — if you enable Basic Auth, remember to add the credentials to your `rest_command` definitions too (`headers: {Authorization: "Basic ..."}`).
- SnapFrame never calls out to the Home Assistant API and needs no `homeassistant_api`/`hassio_api` permission or long-lived token — all HA integration is one-directional (HA → SnapFrame) via plain REST calls you configure yourself.
- The geocoding cache (`/data/geocode_cache.json`) stores GPS coordinates rounded to 2 decimal places (~1 km precision). It does not contain any other personal data.

---

## Contributing

Pull requests are welcome. Some ideas:
- Additional UI languages (i18n)
- Trash management UI (empty trash, restore from trash)
- Video support
- AppArmor profile to reduce required privileges
- Additional weather-slide layouts / themes

---

## License

MIT – see [LICENSE](LICENSE)
