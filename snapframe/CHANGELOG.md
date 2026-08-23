# Changelog

All notable changes to this project will be documented in this file.

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
