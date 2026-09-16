#!/usr/bin/env python3
"""
SnapFrame – filter pomocných súborov, ktoré nie sú fotky.

Prečo:
    macOS pri kopírovaní na SMB share necháva vedľa každej fotky súbor
    AppleDouble s metadátami – rovnaké meno s predponou "._" (napr.
    "._IMG_0137.JPG"). Podľa prípony je to nerozoznateľné od skutočnej
    fotky, takže bez tohto filtra takéto súbory skončia v zozname albumov,
    v počte fotiek, v indexe aj pri generovaní thumbnailov – kde PIL zlyhá,
    lebo v súbore nie je žiadny obrázok.

    Modul je zámerne triviálny a bez závislostí, aby si ho mohli webserver.py
    aj watcher.py len naimportovať bez rizika cyklického importu alebo
    ťažších závislostí (Pillow a pod.).
"""


def is_apple_double(name: str) -> bool:
    """True pre pomocné súbory macOS AppleDouble (`._*`) – metadáta, nie obrázky.

    Berie sa čisto meno súboru (basename), nie celá cesta – bodkočiarka
    "._" na začiatku priečinka nič neznamená a schválne sa nekontroluje.
    Rovnako sa zámerne netýka bežných "skrytých" súborov (".DS_Store" a
    pod.) – tie začínajú jednou bodkou, nie "._".
    """
    return name.startswith("._")
