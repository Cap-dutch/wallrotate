"""Motor de rotacion: revisa los perfiles y aplica el siguiente fondo si corresponde.

Tambien expone funciones para las acciones manuales del icono de bandeja:
siguiente/anterior fondo, pausar, y consultar la imagen actual. El historial
de fondos aplicados se guarda en state.json para poder navegar hacia atras
sin tener que regenerar nada.
"""

from __future__ import annotations

import logging
import random
import subprocess
import time
from pathlib import Path

from PIL import Image

from . import plasma_bridge
from .collage import CollageParams, generate_collage
from .config import (
    CACHE_DIR,
    ScreenProfile,
    load_config,
    load_state,
    save_config,
    save_state,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("wallrotate.engine")

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MAX_HISTORY = 30


def _list_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]


def _pick_next_image(profile: ScreenProfile, state: dict) -> Path | None:
    images = _list_images(Path(profile.source_path))
    if not images:
        log.warning("Sin imagenes en %s (pantalla %s)", profile.source_path, profile.desktop_index)
        return None

    history = _get_history(state, profile.desktop_index)
    last = history[-1] if history else None
    choices = [p for p in images if str(p) != last] or images
    return random.choice(choices)


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
        layout=profile.collage.layout,
        band_top_fraction=profile.collage.band_top_fraction,
        line_count=profile.collage.line_count,
        path_jitter=profile.collage.path_jitter,
        oval_fill=profile.collage.oval_fill,
    )
    img = generate_collage(images, params)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Nombre unico por generacion: Plasma cachea la imagen por ruta y no la
    # vuelve a leer si el nombre de archivo no cambia, aunque el contenido si.
    out_path = CACHE_DIR / f"collage_{profile.desktop_index}_{int(time.time())}.png"
    img.save(out_path)
    return out_path


def _generate_new(profile: ScreenProfile, state: dict) -> Path | None:
    """Elige/genera una imagen NUEVA (no del historial) para el perfil."""
    if profile.source_type == "single_image":
        image_path = Path(profile.source_path)
        return image_path if image_path.is_file() else None
    if profile.source_type == "folder_slideshow":
        return _pick_next_image(profile, state)
    if profile.source_type == "collage":
        return _build_collage(profile)
    log.warning("source_type desconocido: %s", profile.source_type)
    return None


# --- historial ---------------------------------------------------------

def _get_history(state: dict, desktop_index: int) -> list[str]:
    return state.get(f"history_{desktop_index}", [])


def _get_position(state: dict, desktop_index: int) -> int:
    history = _get_history(state, desktop_index)
    return state.get(f"position_{desktop_index}", max(len(history) - 1, 0))


def _push_history(state: dict, desktop_index: int, path: Path) -> None:
    history = _get_history(state, desktop_index)
    history.append(str(path))

    while len(history) > MAX_HISTORY:
        old = history.pop(0)
        old_path = Path(old)
        if old_path.parent == CACHE_DIR:
            old_path.unlink(missing_ok=True)

    state[f"history_{desktop_index}"] = history
    state[f"position_{desktop_index}"] = len(history) - 1


# --- aplicar -------------------------------------------------------------

def _make_notification_thumbnail(profile: ScreenProfile, path: Path) -> Path | None:
    """Miniatura chica para incrustar en el cuerpo de la notificacion con
    <img>. El daemon de notificaciones de Plasma ignora los atributos
    width/height del tag <img> y los hints image-path/icon (los renderiza
    en el slot chico del icono de la app) -- el unico control real del
    tamano visual es pre-escalar el archivo antes de mandarlo."""
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((200, 200))
            thumb_path = CACHE_DIR / f"notif_thumb_{profile.desktop_index}.png"
            im.save(thumb_path)
        return thumb_path
    except Exception:
        log.warning("No se pudo generar la miniatura de la notificacion", exc_info=True)
        return None


def _notify_new_wallpaper(profile: ScreenProfile, path: Path) -> None:
    """Notificacion de escritorio con miniatura del fondo recien aplicado.
    Via notify-send (no via QSystemTrayIcon) porque este codigo corre tanto
    desde la GUI como desde wallrotate-engine, un proceso separado sin tray
    ni ventana -- notify-send le habla directo a notificaciones de KDE."""
    screen = profile.screen_name or f"pantalla {profile.desktop_index}"
    thumb_path = _make_notification_thumbnail(profile, path)
    body = f'<img src="file://{thumb_path}"/>Nuevo fondo en {screen}' if thumb_path else f"Nuevo fondo en {screen}"
    try:
        subprocess.run(
            ["notify-send", "--app-name=WallRotate", "--expire-time=5000", "WallRotate", body],
            capture_output=True, timeout=3,
        )
    except Exception:
        log.warning("No se pudo mostrar la notificacion de escritorio", exc_info=True)


def _apply_path(profile: ScreenProfile, path: Path, state: dict) -> None:
    plasma_bridge.set_wallpaper(profile.desktop_index, path, fill_mode=profile.fill_mode)
    state[f"last_applied_{profile.desktop_index}"] = time.time()
    log.info("Pantalla %s -> %s", profile.desktop_index, path)
    _notify_new_wallpaper(profile, path)


def apply_profile(profile: ScreenProfile, state: dict) -> None:
    """Genera y aplica un fondo nuevo, agregandolo al historial."""
    image_path = _generate_new(profile, state)
    if image_path is None:
        return
    _apply_path(profile, image_path, state)
    _push_history(state, profile.desktop_index, image_path)


def run_once(force: bool = False) -> None:
    config = load_config()
    state = load_state()
    now = time.time()

    if config.pause_on_fullscreen and not force:
        from .fullscreen import is_fullscreen_active
        if is_fullscreen_active():
            log.info("Rotacion pausada: hay una ventana en pantalla completa")
            return

    for profile in config.profiles:
        if not profile.enabled or not profile.source_path or profile.paused:
            continue
        last_applied = state.get(f"last_applied_{profile.desktop_index}", 0)
        due = force or (now - last_applied) >= profile.interval_minutes * 60
        if due:
            apply_profile(profile, state)

    save_state(state)


# --- acciones manuales (menu de bandeja) ---------------------------------

def go_next(desktop_index: int) -> bool:
    """Avanza al siguiente fondo: si hay uno mas nuevo en el historial lo
    reaplica, si no, genera uno nuevo."""
    config = load_config()
    profile = config.profile_for(desktop_index)
    if profile is None or not profile.source_path:
        return False

    state = load_state()
    history = _get_history(state, desktop_index)
    position = _get_position(state, desktop_index)

    if position < len(history) - 1:
        position += 1
        _apply_path(profile, Path(history[position]), state)
        state[f"position_{desktop_index}"] = position
    else:
        image_path = _generate_new(profile, state)
        if image_path is None:
            return False
        _apply_path(profile, image_path, state)
        _push_history(state, desktop_index, image_path)

    save_state(state)
    return True


def go_previous(desktop_index: int) -> bool:
    """Vuelve al fondo anterior del historial, si existe."""
    config = load_config()
    profile = config.profile_for(desktop_index)
    if profile is None:
        return False

    state = load_state()
    history = _get_history(state, desktop_index)
    position = _get_position(state, desktop_index)

    if position <= 0 or not history:
        log.info("Pantalla %s: no hay fondo anterior en el historial", desktop_index)
        return False

    position -= 1
    _apply_path(profile, Path(history[position]), state)
    state[f"position_{desktop_index}"] = position
    save_state(state)
    return True


def toggle_pause(desktop_index: int) -> bool:
    """Pausa/reanuda la rotacion automatica de una pantalla. Devuelve el
    nuevo estado (True = pausado)."""
    config = load_config()
    profile = config.profile_for(desktop_index)
    if profile is None:
        return False
    profile.paused = not profile.paused
    save_config(config)
    return profile.paused


def toggle_pause_all() -> bool:
    """Pausa/reanuda la rotacion automatica de todas las pantallas a la vez.
    Si ya estan todas pausadas, las reanuda; en cualquier otro caso, pausa
    todas. Devuelve el nuevo estado (True = todas pausadas)."""
    config = load_config()
    if not config.profiles:
        return False
    new_state = not all(profile.paused for profile in config.profiles)
    for profile in config.profiles:
        profile.paused = new_state
    save_config(config)
    return new_state


def current_image_path(desktop_index: int) -> Path | None:
    state = load_state()
    history = _get_history(state, desktop_index)
    position = _get_position(state, desktop_index)
    if not history or position < 0 or position >= len(history):
        return None
    return Path(history[position])


def main() -> None:
    run_once()


if __name__ == "__main__":
    main()
