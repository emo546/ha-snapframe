# Changelog

All notable changes to this project will be documented in this file.

## [2.9.0] – 2026

### Added
- **Weather mode with hourly forecast** – trigger the weather screen (via motion → HA automation) and it shows current conditions plus the next ~12 hours as a row of large forecast cards (hour · icon · temperature), with the nearest hour highlighted.
- The `/weather-update` endpoint now accepts an `hourly` array (list of `{datetime, temperature, condition}` — exactly the shape Home Assistant's `weather.get_forecasts` returns). Up to 12 entries are used.
- When `forecast_high`/`forecast_low` are not provided, today's high/low is now auto-derived from the hourly temperatures.

### Changed
- **Redesigned weather screen for legibility from across the room** – a large hero (icon + oversized temperature), fluid `clamp()`/viewport-based typography that scales up on bigger displays, and 6 big hourly forecast items sampled evenly across the full 12 h span. Higher-contrast text, modern rounded cards, and a subtle highlight on the upcoming hour. Pure CSS, no external assets.
- **Orientation-aware layout** – in landscape (typical wall-mounted frame) the hourly forecast is a row of cards; in portrait (tablet/phone on end) it flips to full-width rows stacked top-to-bottom (time · icon · temperature), sized to fit the screen without scrolling. Re-lays out automatically on rotation.
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
