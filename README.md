# SnapFrame – Home Assistant Add-on Repository

Turn any old tablet or iPad into a smart **digital photo frame** for Home Assistant. SnapFrame watches a Samba/CIFS share, converts HEIC/HEIF photos to JPG, and serves a fullscreen slideshow with albums, EXIF date/GPS overlay, night mode, multi-language UI, and a motion-triggered weather screen.

This repository is a **Home Assistant custom add-on repository**. The add-on itself lives in the [`snapframe/`](snapframe/) folder — see its [full README](snapframe/README.md) for features, configuration, weather-mode automations, and troubleshooting.

## Install into Home Assistant (recommended: via URL)

1. In Home Assistant, go to **Settings → Add-ons → Add-on Store**
2. Tap the **⋮** (three dots) menu top-right → **Repositories**
3. Paste this URL and click **Add**:
   ```
   https://github.com/emo546/ha-snapframe
   ```
4. Refresh the store — a **"SnapFrame Add-ons"** section appears with **SnapFrame** in it. Click **Install**.

You'll then get one-click **Update** whenever a new version is pushed here. Full configuration and usage docs are in [`snapframe/README.md`](snapframe/README.md).

> Prefer a manual/local install instead? That's documented as **Method B** in the [add-on README](snapframe/README.md#installation).

## Repository layout

```
ha-snapframe/
├── repository.yaml        ← marks this repo as an HA add-on repository
├── README.md              ← this file
├── LICENSE
└── snapframe/             ← the add-on
    ├── config.yaml
    ├── build.yaml
    ├── Dockerfile
    ├── CHANGELOG.md
    ├── README.md          ← full add-on documentation
    └── rootfs/…
```

## License

MIT – see [LICENSE](LICENSE)
