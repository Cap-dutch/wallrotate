"""Motor de rotacion: revisa los perfiles y aplica el siguiente fondo si corresponde."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

from . import plasma_bridge
from .collage import CollageParams, generate_collage
from .config import CACHE_DIR, ScreenProfile, load_config, load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wallrotate.engine")

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def _list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]


def _pick_next_image(profile: ScreenProfile, state: dict) -> Path | None:
    images = _list_images(Path(profile.source_path))
    if not images:
        log.warning("Sin imagenes en %s (pantalla %s)", profile.source_path, profile.desktop_index)
        return None

    key = f"last_image_{profile.desktop_index}"
    last = state.get(key)
    choices = [p for p in images if str(p) != last] or images
    chosen = random.choice(choices)
    state[key] = str(chosen)
    return chosen


def _build_collage(profile: ScreenProfile) -> Path | None:
    folder = Path(profile.source_path)
    images = _list_images(folder)
    if not images:
        log.warning("Sin imagenes para collage en %s (pantalla %s)", profile.source_path, profile.desktop_index)
        return None

    screens = plasma_bridge.list_screens()
    screen = next((s for s in screens if s.desktop_index == profile.desktop_index), None)
    canvas_size = (screen.width, screen.height) if screen and screen.width else (1920, 1080)

    params = CollageParams(
        canvas_size=canvas_size,
        max_photos=profile.collage.max_photos,
        max_rotation_deg=profile.collage.max_rotation_deg,
        shadow=profile.collage.shadow,
        border=profile.collage.border,
        photo_scale=profile.collage.photo_scale,
        photo_fit=profile.collage.photo_fit,
        min_spacing=profile.collage.min_spacing,
        background=profile.collage.background,
    )
    img = generate_collage(images, params)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Nombre unico por generacion: Plasma cachea la imagen por ruta y no la
    # vuelve a leer si el nombre de archivo no cambia, aunque el contenido si.
    out_path = CACHE_DIR / f"collage_{profile.desktop_index}_{int(time.time())}.png"
    img.save(out_path)
    return out_path


def _cleanup_old_collages(desktop_index: int, keep: Path) -> None:
    for old in CACHE_DIR.glob(f"collage_{desktop_index}_*.png"):
        if old != keep:
            old.unlink(missing_ok=True)


def apply_profile(profile: ScreenProfile, state: dict) -> None:
    if profile.source_type == "single_image":
        image_path = Path(profile.source_path)
        if not image_path.is_file():
            log.warning("Imagen no encontrada: %s", profile.source_path)
            return
    elif profile.source_type == "folder_slideshow":
        image_path = _pick_next_image(profile, state)
        if image_path is None:
            return
    elif profile.source_type == "collage":
        image_path = _build_collage(profile)
        if image_path is None:
            return
    else:
        log.warning("source_type desconocido: %s", profile.source_type)
        return

    plasma_bridge.set_wallpaper(profile.desktop_index, image_path, fill_mode=profile.fill_mode)
    state[f"last_applied_{profile.desktop_index}"] = time.time()
    log.info("Pantalla %s -> %s", profile.desktop_index, image_path)

    if profile.source_type == "collage":
        _cleanup_old_collages(profile.desktop_index, keep=image_path)


def run_once(force: bool = False) -> None:
    config = load_config()
    state = load_state()
    now = time.time()

    for profile in config.profiles:
        if not profile.enabled or not profile.source_path:
            continue
        last_applied = state.get(f"last_applied_{profile.desktop_index}", 0)
        due = force or (now - last_applied) >= profile.interval_minutes * 60
        if due:
            apply_profile(profile, state)

    save_state(state)


def main() -> None:
    run_once()


if __name__ == "__main__":
    main()
