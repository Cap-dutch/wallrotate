"""Bridge para aplicar fondos de pantalla por monitor en KDE Plasma via D-Bus."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

QDBUS = "qdbus6"
PLASMA_SERVICE = "org.kde.plasmashell"
PLASMA_PATH = "/PlasmaShell"
PLASMA_IFACE = "org.kde.PlasmaShell.evaluateScript"

# Qt Image.fillMode: 0 Stretch, 1 PreserveAspectFit, 2 PreserveAspectCrop,
# 3 Tile, 4 TileVertically, 5 TileHorizontally, 6 Pad (centrado)
FILL_MODES = {
    "estirar": 0,
    "ajustar": 1,
    "rellenar": 2,
    "mosaico": 3,
    "mosaico_vertical": 4,
    "mosaico_horizontal": 5,
    "centrado": 6,
}


@dataclass
class ScreenInfo:
    desktop_index: int
    screen_num: int
    name: str
    width: int
    height: int


def _run_script(script: str) -> str:
    result = subprocess.run(
        [QDBUS, PLASMA_SERVICE, PLASMA_PATH, PLASMA_IFACE, script],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def list_screens() -> list[ScreenInfo]:
    """Detecta los monitores conectados, combinando kscreen-doctor y Plasma."""
    kscreen = subprocess.run(["kscreen-doctor", "-j"], capture_output=True, text=True, check=True)
    outputs = json.loads(kscreen.stdout)["outputs"]
    connected = [o for o in outputs if o.get("connected") and o.get("enabled")]

    n_desktops = int(_run_script("print(desktops().length)"))

    screens = []
    for i in range(n_desktops):
        screen_num = int(_run_script(f"print(desktops()[{i}].screen)"))
        output = connected[screen_num] if screen_num < len(connected) else None
        if output is not None:
            mode = next((m for m in output["modes"] if m["id"] == output["currentModeId"]), None)
            name = output.get("name", f"pantalla-{screen_num}")
            width = mode["size"]["width"] if mode else 0
            height = mode["size"]["height"] if mode else 0
        else:
            name, width, height = f"pantalla-{screen_num}", 0, 0
        screens.append(ScreenInfo(desktop_index=i, screen_num=screen_num, name=name, width=width, height=height))
    return screens


def set_wallpaper(desktop_index: int, image_path: Path, fill_mode: str = "rellenar") -> None:
    """Aplica una imagen estatica como fondo de pantalla en un monitor especifico."""
    fill_mode_value = FILL_MODES.get(fill_mode, FILL_MODES["rellenar"])
    image_url = f"file://{Path(image_path).resolve()}"

    script = f"""
var d = desktops()[{desktop_index}];
d.wallpaperPlugin = "org.kde.image";
d.currentConfigGroup = Array("Wallpaper", "org.kde.image", "General");
d.writeConfig("Image", {json.dumps(image_url)});
d.writeConfig("FillMode", {fill_mode_value});
"""
    _run_script(script)


def get_current_image(desktop_index: int) -> str | None:
    out = subprocess.run(
        [QDBUS, PLASMA_SERVICE, PLASMA_PATH, "org.kde.PlasmaShell.wallpaper", str(desktop_index)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("Image:"):
            return line.split("Image:", 1)[1].strip() or None
    return None
