# Changelog

All notable changes to this project will be documented in this file.

## [3.1.0] – 2026

### Fixed

- **The big temperature on the weather screen was the temperature at push time, not now.** `/weather-update` carries whatever `weather.home` read when Home Assistant sent it, and the frame displayed that value unchanged for as long as it stood — so a frame running since the morning kept showing the morning's temperature, with nothing on screen to suggest it was old. The frame now decides for itself: a push younger than 20 minutes is used as-is (it is a measurement), an older one has the current temperature and condition **interpolated from the hourly forecast that arrived with it**, so the number moves smoothly through the day instead of jumping on the hour. Once the current time runs past the end of that forecast — nothing pushed for roughly 12 hours — it shows `--°` rather than a number it can no longer stand behind. The freshness rule needs no new setting: it is bounded by the length of the forecast itself.
- **`/weather` now reports `age_seconds`.** The age is computed on the server (a difference between two readings of one clock), and the frame adds the time elapsed since its own fetch, so a tablet with badly set clocks still gets the age right. The weather screen prints it underneath (`updated 12 min ago`, or `from the hourly forecast · updated 4 h ago`) — a stalled automation is now visible instead of silent.
- **The hourly strip could start in the past.** The forecast arrives with the push, so hours before *now* were still drawn after a few hours without one — and the first card, highlighted as "now", showed an hour long gone. Past hours are dropped before the strip is laid out.

### Added

- **Weather badge in the top-right corner** (`weather_display_mode`: `slide` / `badge` / `both`). Weather mode is short-lived by design — motion starts it in the morning, it stops itself a couple of hours later — so there was no way to keep the weather on screen for the rest of the day short of leaving the full-screen slide cycling. The badge mirrors the waste-collection badge in the opposite corner (same layout, same old-iPad-Safari fallbacks) and shows icon, temperature and today's high/low over the photos. It is driven by the data that is already there, so it needs no new endpoint and no second automation; the photo counter steps aside while it is up. Default stays `slide`, so an existing frame looks exactly as it did until the option is changed.
- **`weather_badge_hours`** (default `6-22`, may wrap past midnight, empty = all day) bounds when the badge may appear, independently of weather mode's own duration.
- **`weather_badge_alerts_only`** turns the badge into a notification rather than a readout: it stays hidden until the hourly forecast shows rain, snow or a storm within 3 hours, or frost or heat within 6, and its accent colour matches what it is warning about.
- The condition translations are now handed to the page in full, not just the label of the pushed condition — the frame derives conditions from the forecast too, and needs to name them.
- 12 new tests: the badge-hour window (including wrap-past-midnight and nonsense input, which must not silently disable the badge for a whole day), `/weather` age reporting, the hourly payload surviving a push intact, and the page config carrying the new settings. 105 tests in total.

### Changed

- The recommended weather automation in the documentation now also triggers on a state change of the weather entity, not only every 30 minutes, so a fresh measurement reaches the frame as soon as one exists.

## [3.0.3] – 2026

### Added

- **Waste reminder now has an end time, not just a start time.** `show_on_day` used to keep the badge/full-screen reminder up all day once collection day started. A new `end_hour` setting (mirroring the existing day-before `start_hour`) hides it again after a chosen hour, since the bin is presumably already out and collected by then.

### Fixed

- **Some waste types showed no icon at all on older iPad Safari.** Plastic (🥤), metal (🥫) and drink cartons (🧃) used Emoji 5.0/12.0 glyphs (2017/2019) that Safari before iOS 11.1/13.2 can't render, so those three types silently showed no icon while the rest (all Emoji 1.0, 2015) worked fine. Replaced with equally old glyphs (shopping bags, nut and bolt, package) that render everywhere the others already do.

## [3.0.2] – 2026

### Changed

- **Opening a large album took a long time to start playing.** Listing photos still did a filesystem check per file to see whether the 3.0.0 photo index was up to date — `Path.iterdir()` + `.is_file()` + `.stat()` + `.resolve()`, none of which cache anything, so each photo cost two to four round trips to the SMB share before the slideshow could even ask for the first image. Listing now uses `os.scandir()`, whose `DirEntry` remembers its own `stat()` result, cutting that to about one round trip per photo. Measured with a simulated 3 ms per-call network delay (representative of a real CIFS share) and 400 photos: 6.3 s → 0.04 s to list the same album, byte-identical result.
- The same change also means the trash folder (`_kos`) is no longer walked at all when listing "all photos" or counting an album on the selection screen — previously every file in it was visited and then discarded by path, which got slower the fuller the trash was.
- 5 new tests cover the scan behaviour directly: hidden folders are never descended into (not just filtered afterwards), an album listing still doesn't recurse into subfolders, the "all photos" view still does, trash doesn't count toward an album's photo count, and a 150-photo album lists every file. 88 → 93 tests.

## [3.0.1] – 2026

### Fixed

- **The hourly weather strip showed the wrong time.** Home Assistant sends the hourly forecast in UTC, but the label was only ever built from that UTC string without converting to local time — the data itself was correct, only mislabelled, by exactly the UTC offset (2 hours in summer, 1 in winter). The server now converts using the container's own timezone when it has one (`TZ`, which the Supervisor normally sets), and the hourly payload also carries the raw ISO timestamp so the browser — which, like the tablet driving the waste-collection reminders, has a timezone the container can't be sure of — computes the label itself.

## [3.0.0] – 2026

### Security

- **URL paths could reach outside the photo library.** Flask's `<path:>` converter hands `../..` (and its `%2e%2e` form) straight to the handler, so every route that built a filesystem path from the URL could step out of `output_folder`: `POST /delete/<path>` renamed the target into `_kos/`, `/thumb/<path>` wrote a JPEG next to it, and `/exif/<path>` read it. `/photo/<path>` was safe only because `send_from_directory` does its own `safe_join`. All of them now resolve through one helper that rejects anything outside the library, album names from the URL and from the upload form are reduced to a single folder name, and the regression tests cover each escape form.
- **New `api_token` option protects everything that writes.** Uploading, deleting, triggering a scan, saving or importing the waste calendar and pushing weather data required no credentials at all unless Basic Auth was on — and Basic Auth is off by default, which left those endpoints open to anyone who could reach the port. Set `api_token` and those calls need `X-SnapFrame-Token`; reading stays open so the frame still needs no login, and the app asks for the token only when a write comes back 401. Add-ons log a warning at startup when the token is unset.
- Basic Auth now compares credentials with `hmac.compare_digest` instead of `==`.
- Python dependencies are pinned (`snapframe/requirements.txt`). The add-on is built on the user's own device, so an unpinned dependency could break installs at any time without a single change in this repo.

### Added

- **Home Assistant ingress** – the add-on now offers a protected UI inside Home Assistant (Open Web UI / sidebar panel), while the mapped port stays available for the tablets. Every request the page makes is relative to the page, so both routes work unchanged.
- **MQTT discovery** – with the Mosquitto add-on running, SnapFrame publishes the next waste collection (with `days_until` and the waste types as attributes), the photo count, the last scan time and whether weather mode is active. The entities appear on their own; no hand-written REST sensor in `configuration.yaml`. Off when no broker is configured (`mqtt_enabled`, plus manual `mqtt_host`/`mqtt_port`/`mqtt_username`/`mqtt_password` for a broker outside HA).
- **Health check** – a Docker `HEALTHCHECK` probes the new unauthenticated `GET /health`, so the Supervisor restarts a frozen add-on instead of leaving it to quietly serve nothing. The probe is deliberately exempt from Basic Auth: it has no credentials, and a 401 would restart-loop the add-on. (The `watchdog:` config key would have been the obvious place for this, but it is obsolete and the add-on linter rejects it.)
- **CIFS mount watchdog** – `run.sh` mounted the share once at startup and never looked again, so a NAS that went away left the add-on running blind. A background check every minute verifies both that the mount exists and that it can actually be read (a dead server leaves the mount entry behind) and remounts. The password is written to a credentials file per attempt and shredded straight after.
- **`smb_version` option** – SMB 3.0 was hard-coded; older NAS boxes and Windows shares need 2.1 or 1.0.
- **Prebuilt images** – a release workflow builds both architectures and pushes them to GHCR, so an update no longer means minutes of compiling on a Raspberry Pi. Turn it on by uncommenting the `image:` line in `config.yaml` once the workflow has published the current version.
- **Translated options** – `translations/{en,sk,de}.yaml` name and describe all 29 options in the add-on configuration screen, instead of showing bare field names.
- `thumb_cache` option (`addon` / `share`) and a `?w=` parameter on `/thumb/<path>`.

### Changed

- **Photo metadata is indexed in `/data` instead of being re-read over the network.** `/photos` sorts by EXIF date, which meant opening every photo — over CIFS, on every request, for every tablet, every five minutes. The in-memory LRU held 250 entries, which a library of a few thousand photos thrashes completely, and a restart emptied it anyway. A SQLite index now holds the date and GPS per photo, keyed by path and mtime, filled by the background pass that already walks every file; a listing is one query plus a stat per file. `/exif` reads from the same index and remembers the geocoded place name. If `/data` is unwritable the add-on silently falls back to the old behaviour.
- **Thumbnails moved out of the photo library into `/data`** – on the share they were read and written over the network and cluttered the user's photo folder. They are also always written as JPEG (a thumbnail of a `.png` used to be served as `image/png` with JPEG bytes inside), and are generated in several widths so a Retina iPad can ask for the size it actually displays instead of upscaling 1024 px. `thumb_cache: share` restores the old location for libraries larger than the free space on the HA disk; the old `output_folder/_thumbs/` folder can be deleted by hand.
- **The frame survives a slow share and a restart.** The transition used to start before the photo was fetched, so a slow share faded in an empty frame; each photo is now preloaded and the next one is fetched while the current is on screen. A single failed request used to leave the frame frozen until someone reloaded it by hand; requests now retry with backoff and a small notice appears while the server is unreachable. The page also reloads itself once a day (during night mode when one is configured), which clears the memory drift of a browser open for months and picks up add-on updates.
- **The scan no longer waits 5 seconds per file.** The check that a file is fully copied ran unconditionally on every file, so 500 new photos meant over 40 minutes of waiting alone. Files whose mtime is older than two minutes are not being uploaded any more and are converted straight away.
- **The page is no longer a 2450-line string inside `webserver.py`.** HTML, CSS and JS live in `/usr/share/snapframe`; only the language pack and a handful of config values are injected. The page itself stays uncached, but CSS and JS are now static files the browser keeps, invalidated by a `?v=` derived from the asset mtimes — a reload used to pull the whole UI again every time.
- `/thumb`, `/photo` and `/album-cover` send cache headers, so a wall display stops re-fetching the same photo every cycle.
- Image files are closed after reading EXIF and after writing a thumbnail; at a few thousand photos the leaked handles were real.

### Fixed

- A thumbnail whose source could not be read no longer falls back to a path built from the raw URL.
- `zip()` in the schedule parser is explicit about length mismatches.

### Development

- Unit tests for the web layer (path traversal, auth and the token gate, uploads, the index, thumbnails) and for MQTT discovery — 78 tests in total.
- A test fails the build if an option is added to `config.yaml` without a schema entry or a translation in every language, or if the watchdog is ever pointed at an authenticated route.
- Ruff runs a curated rule set (E4/E7/E9/F/W/B) at the project's real line length instead of four rules, CI lints `app.js`, and Dependabot watches the actions and the pinned dependencies.

## [2.11.0] – 2026

### Added
- **Import the municipal collection schedule from a file** – upload the leaflet in the app (Settings → *Waste collection…* → *"Import from schedule…"*) and SnapFrame reads the collection dates out of it, instead of you typing a year's worth of dates by hand.
  - **Vector PDFs are parsed locally – no OCR, no network, no API key.** Municipal schedules are grid calendars where the meaning is carried by the *colour of the cell*, not by text: OCR would return the day numbers with no idea which of them are collections. A vector PDF, though, contains both the day numbers and the coloured rectangles with their coordinates, so they can be matched directly. Row = ISO week number and column = weekday, so **(ISO week + weekday) gives the exact date**, and the printed day number is then used as a checksum — a cell that doesn't agree is discarded rather than guessed.
  - **Detects series, not waste types.** The palette is deliberately not hard-coded: one village marks plastic yellow, the next marks it blue, and the *same* leaflet routinely carries several schedules at once (a fortnightly and a monthly mixed-waste round, for instance) — which one applies to a given household is something only the resident knows. The import lists every colour series it found, with a swatch, how often it recurs and its date range, and you tick the ones that apply and assign each a waste type.
  - **Understands cell outlines.** A coloured border around a cell marks a subset or an add-on rather than a separate waste type (on a real leaflet: a green outline on a black cell = the monthly-frequency round, a brown outline on a yellow cell = "bio *and* plastic on the same day"). Both the per-colour total and the exact fill/outline combination are offered, so either reading can be picked.
  - **Nothing is ever saved automatically** – the parsed dates land in the editor for confirmation first. A misread date means a missed bin, which is precisely what this feature exists to prevent.
  - Concrete dates are imported rather than an inferred recurrence rule, so real-world exceptions survive: a fortnightly round that skips New Year's Eve stays skipped instead of producing a phantom reminder.
- **Optional fallback for scans and photos** – if the layout isn't one the parser recognises, or you upload a JPG/PNG instead of a vector PDF, SnapFrame can send the file to Claude to extract the dates. This is **off unless you set `anthropic_api_key`**, and it is the only path in SnapFrame that sends anything outside your network — the parser above needs no key and no internet.
- New config option: `anthropic_api_key` (optional, empty by default).
- New endpoint: `POST /waste/import` (returns detected series; saves nothing).
- 15 further unit tests covering the parser, built on generated PDFs whose marked days are known exactly.
- Documentation: a full *Importing the municipal schedule* section, troubleshooting entries for a schedule that can't be read or whose colours map to the wrong type, and security notes covering the one optional feature that can send data off your network.

### Fixed
- The grid-cell radius used when matching colour marks to days is now derived from the page's own row/column pitch instead of a fixed point value, so the same schedule laid out at a different page size no longer risks attaching a mark to the neighbouring day.

## [2.10.0] – 2026

### Added
- **Waste collection calendar** – set up which days of the year each waste type is collected (mixed, bio, plastic, paper, glass, metal, drink cartons, e-waste, bulky, other) and the frame reminds you the day before, so the bin actually makes it to the kerb.
  - **Rules, not endless date lists.** Real municipal schedules are almost always *"every other Thursday"* or *"first Monday of the month"*, so a collection is defined as a rule: **every N weeks** on a weekday (with a reference date that fixes which week is the right one), **monthly** by position (*first / last Monday…*, optionally limited to certain months) or by day number, or a plain **list of specific dates** for irregular pickups. Every rule can additionally have a validity range (*valid from / until*), **exceptions** (public holidays – no collection) and **extra one-off dates**.
  - **Two reminder styles, configurable** – a discreet **corner badge** shown on top of the photos the whole time, a **full-screen reminder** injected every *N* photos (same pattern as the weather screen), or both at once.
  - **Configurable lead time** – remind 0–7 days ahead, optionally also on the collection day itself, and optionally only from a given hour (so the "tomorrow" reminder doesn't nag from 6 a.m.).
  - **Set up entirely in the app** – a full editor behind Settings → *Waste collection…*, so no add-on restart and no hand-editing YAML with dozens of dates. The schedule is stored in `/data/waste_schedule.json` and shared by every tablet pointed at the add-on.
  - The frame decides what "tomorrow" means using the *tablet's* local time, not the container's – the server only ships the expanded list of upcoming collection days, so a container running in UTC can't shift the reminder by a day.
- New endpoints: `GET`/`POST` `/waste/config`, `GET /waste/status`, and `GET /waste/next` – the last one is shaped for a Home Assistant REST sensor (`state` is the next collection date, with `days_until` and the waste types), so you can also send a phone notification or drive automations from the same schedule.
- Slovak, English and German translations for the whole feature, including waste-type names and human-readable rule summaries.
- **Unit tests** for the schedule engine (`tests/test_waste.py`, 30 cases covering recurrence phases, month-edge cases, exceptions/extras and config sanitisation) plus a CI step that runs them.

### Changed
- The weather screen and the waste reminder never overlap: while the weather screen is up (or during night mode, or outside the slideshow) the corner badge stays hidden, and each keeps its own photo counter so both interleave cleanly.

## [2.9.1] – 2026

### Fixed
- **Weather screen on old iPad Safari** – the portrait hourly forecast rendered as an ugly full-width boxy "table" on older iPads. Root cause: the layout relied on flexbox features that old iPad Safari (9–13) handles poorly or not at all — flex `gap` (unsupported before Safari 14.1) and buggy flexbox sizing — on top of the already-fallbacked `clamp()`/`min()`. The portrait hourly rows are now built with `display: table`/`table-cell` (rock-solid on ancient Safari) instead of flexbox, the MAX/MIN line no longer depends on flex `gap`, and the whole weather screen degrades cleanly to a centered block layout even with no flexbox support at all. Verified by simulating flexbox-off + no `clamp/min/gap`.
- **Stale cache on wall displays** – the slideshow HTML (which embeds all CSS/JS) is now served with `Cache-Control: no-store`, so a mounted tablet picks up new versions after an add-on update/rebuild without manually clearing Safari's website data.

## [2.9.0] – 2026

### Added
- **Weather mode with hourly forecast** – trigger the weather screen (via motion → HA automation) and it shows current conditions plus the next ~12 hours as a row of large forecast cards (hour · icon · temperature), with the nearest hour highlighted.
- The `/weather-update` endpoint now accepts an `hourly` array (list of `{datetime, temperature, condition}` — exactly the shape Home Assistant's `weather.get_forecasts` returns). Up to 12 entries are used.
- When `forecast_high`/`forecast_low` are not provided, today's high/low is now auto-derived from the hourly temperatures.

### Changed
- **Redesigned weather screen for legibility from across the room** – a large hero (icon + oversized temperature), fluid `clamp()`/viewport-based typography that scales up on bigger displays, and 6 big hourly forecast items sampled evenly across the full 12 h span. Higher-contrast text, modern rounded cards, and a subtle highlight on the upcoming hour. Pure CSS, no external assets.
- **Orientation-aware layout** – in landscape (typical wall-mounted frame) the hourly forecast is a row of cards; in portrait (tablet/phone on end) it flips to compact rows stacked top-to-bottom (time · icon · temperature), sized to fit the screen without scrolling. Re-lays out automatically on rotation.
- **Old-Safari fallbacks for the weather screen** – the redesigned weather screen used `clamp()`/`min()`, which older iPad Safari (9–12, a common photo-frame device) doesn't support, causing it to drop those declarations and render a tiny, broken layout. Every fluid size now has a plain-px fallback before the `clamp()`/`min()`, so old Safari gets a correct fixed-size layout while modern browsers still scale fluidly.
- README weather-mode example updated to fetch the hourly forecast via `weather.get_forecasts` (required on recent HA versions, which removed the `forecast` state attribute) and pass it to SnapFrame.

## [2.8.0] – 2026

### Added
- **Weather mode** – a Home Assistant automation (e.g. triggered by a motion sensor in the morning) can call the new `POST /weather-mode/on` endpoint to make the slideshow insert a nicely designed current-weather + today's-forecast screen every `weather_photo_interval` photos (default 8), for `weather_mode_duration_minutes` (default 120 min). A second automation pushes weather data periodically via `POST /weather-update`. No `homeassistant_api` permission or token needed – integration is one-directional (HA → SnapFrame) over plain REST, matching the existing `/scan` pattern.
- New endpoints: `POST /weather-mode/on`, `POST /weather-mode/off`, `POST /weather-update`, `GET /weather`.
- New config options: `weather_photo_interval` (2–50, default 8), `weather_mode_duration_minutes` (5–720, default 120).
- Weather condition icons and translated condition labels (SK/EN/DE) for all standard Home Assistant weather conditions.
- **GPS/location hint in the upload form** – explains that iOS/Safari may strip or reduce GPS precision on photos picked through the web upload form (privacy behaviour on the OS/browser side, not something the add-on can control), and suggests using SMB or AirDrop for full-precision location instead.

### Changed
- **README rewritten** – reframed around "turn any old tablet into a digital photo frame" instead of iPhone/iPad-only, with SEO-friendly language, a much more detailed step-by-step install/configuration guide, and documentation for previously undocumented features (multi-language UI, night mode with starry sky, in-app settings, weather mode with Home Assistant automation examples).

## [2.7.0] – 2026

### Added
- **In-app settings panel** – gear icon (⚙) on the album selection screen opens a settings dialog directly in the web UI, no need to touch the Home Assistant addon configuration.
- **Sleep screen theme** – choose between a plain black screen or an animated starry sky during sleep hours. Preference is saved per device (`localStorage`) and applies instantly.
- **Starry sky sleep screen** – soft dark-blue gradient background, ~70–180 stars (density scales with screen size) with a gentle twinkle animation, plus occasional shooting stars. Pure CSS/SVG, no canvas redraw loop, so it stays battery/performance friendly on iPad.
- New translation strings for the settings panel in SK/EN/DE.

## [2.6.0] – 2025

### Added
- **Web upload** – upload HEIC/JPG/PNG photos directly from the browser (including iPhone Safari). Sequential upload with per-file progress indicator (`Uploading 3 / 12: photo.heic`).
- **New album creation on upload** – type a new subfolder name directly in the upload form; the folder is created automatically.
- **Background thumbnail pre-generation** – after every scan, missing thumbnails are generated in a background thread so the slideshow is always responsive. Progress is visible in `/status`.
- **`/status` endpoint** – JSON with last scan time, next scan countdown, total converted count, thumbnail pre-generation progress.
- **`/scan` endpoint (POST)** – triggers an immediate scan without waiting for the interval.
- **"Scan now" button** in the album selection screen.
- **Photo counter overlay** – `12 / 47` shown in the top-right corner of the slideshow.
- **Album cover thumbnails** – album buttons show the first photo of each album as a background image.
- **Photo count per album** – displayed on each album button.
- **Persistent geocoding cache** – GPS reverse-geocoding results are saved to `/data/geocode_cache.json` and survive restarts.
- **LRU EXIF cache** – bounded in-memory cache (250 entries) using `OrderedDict`; prevents unbounded memory growth with large collections.
- **Configurable thumbnail size** (`thumb_max_px`, default 1024) and thumbnail quality (`thumb_quality`, default 82) via addon configuration.
- **Optional HTTP Basic Auth** – set `basic_auth_user` and `basic_auth_password` in configuration to password-protect the web interface.
- **Waitress thread count increased** to 8 to handle concurrent SMB-backed requests.
- **`state.py`** – shared inter-thread state module for scan status and thumbnail pre-generation progress.
- **`.dockerignore`** – excludes `__pycache__` and `.pyc` files from Docker build.

### Fixed
- **Space in generated filename** – duplicate HEIC filenames produced `photo_1. jpg` (with a space); now correctly `photo_1.jpg`.
- **Refresh timer** – previously only updated the photo list when the count *increased*; now always syncs, correctly handling deletions from another client.
- **`bashio::config` returning `"null"`** – new optional config fields return the string `"null"` on existing installations; both `run.sh` and `webserver.py` now handle this gracefully with fallback defaults.
- **JavaScript regex broken by Python string escaping** – replaced regex character class with a character-by-character loop to avoid shell/Python escaping issues.

## [2.0.0] – 2024

### Added
- Recursive subfolder scanning (preserves album structure)
- Fullscreen slideshow web interface optimised for iPad/Safari 9
- EXIF date and GPS location overlay
- Nominatim reverse geocoding with Slovak country name translations
- Album selection screen with random/chronological ordering
- Swipe navigation (left/right = prev/next, swipe down = back)
- Long-press to move photo to trash (`_kos/` subfolder)
- CIFS/SMB auto-mount on addon start
- Configurable scan interval, JPEG quality, slideshow duration

## [1.0.0] – 2024

### Added
- Initial release: watch folder → convert HEIC → save JPG, delete original
