"""Generador de collages estilo "pila de fotos" (polaroid pile)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps


@dataclass
class CollageParams:
    canvas_size: tuple[int, int] = (1920, 1080)
    max_photos: int = 8
    max_rotation_deg: float = 18.0
    shadow: bool = True
    shadow_blur: int = 14
    shadow_opacity: int = 140  # 0-255
    shadow_offset: tuple[int, int] = (10, 14)
    border: bool = True
    border_width: int = 16
    bottom_border_extra: int = 54  # borde inferior mas grueso, estilo polaroid
    photo_scale: float = 0.32  # ancho de cada foto como fraccion del ancho del canvas
    background: str = "blurred"  # "blurred" | "solid"
    background_color: tuple[int, int, int] = (24, 24, 26)
    background_blur_radius: int = 40
    background_darken: float = 0.55  # 1.0 = sin oscurecer, 0.0 = negro
    seed: int | None = None


def _make_background(canvas_size: tuple[int, int], image_paths: list[Path], params: CollageParams) -> Image.Image:
    w, h = canvas_size
    if params.background == "solid" or not image_paths:
        return Image.new("RGB", (w, h), params.background_color)

    bg_path = random.choice(image_paths)
    with Image.open(bg_path) as im:
        im = ImageOps.exif_transpose(im.convert("RGB"))
        bg = ImageOps.fit(im, (w, h), method=Image.LANCZOS)

    bg = bg.filter(ImageFilter.GaussianBlur(params.background_blur_radius))
    if params.background_darken < 1.0:
        bg = ImageEnhance.Brightness(bg).enhance(params.background_darken)
    return bg


def _framed_photo(path: Path, target_width: int, params: CollageParams) -> Image.Image:
    """Abre una foto, la redimensiona y le agrega marco tipo polaroid."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im.convert("RGB"))
        ratio = im.height / im.width
        target_height = int(target_width * ratio)
        im = im.resize((target_width, max(target_height, 1)), Image.LANCZOS)

    if not params.border:
        return im.convert("RGBA")

    bw = params.border_width
    bottom = bw + params.bottom_border_extra
    framed = Image.new("RGB", (im.width + bw * 2, im.height + bw + bottom), (250, 250, 248))
    framed.paste(im, (bw, bw))
    return framed.convert("RGBA")


def _with_shadow(photo: Image.Image, params: CollageParams) -> Image.Image:
    """Agrega sombra difusa detras de la foto, devuelve una capa RGBA mas grande."""
    if not params.shadow:
        return photo

    pad = params.shadow_blur * 3 + max(params.shadow_offset)
    layer = Image.new("RGBA", (photo.width + pad * 2, photo.height + pad * 2), (0, 0, 0, 0))

    shadow_shape = Image.new("RGBA", photo.size, (0, 0, 0, params.shadow_opacity))
    ox, oy = params.shadow_offset
    layer.paste(shadow_shape, (pad + ox, pad + oy), shadow_shape)
    layer = layer.filter(ImageFilter.GaussianBlur(params.shadow_blur))

    layer.paste(photo, (pad, pad), photo)
    return layer


def _grid(n: int, canvas_size: tuple[int, int]) -> tuple[int, int, float, float]:
    """Calcula columnas/filas y el tamano de celda para repartir n fotos en el canvas."""
    w, h = canvas_size
    cols = max(1, round((n * w / h) ** 0.5))
    rows = max(1, -(-n // cols))  # ceil
    return cols, rows, w / cols, h / rows


def _photo_aspect_ratio(path: Path) -> float | None:
    """Alto/ancho de la imagen, leyendo solo el encabezado (rapido)."""
    try:
        with Image.open(path) as probe:
            w, h = ImageOps.exif_transpose(probe).size
            return h / w if w else None
    except Exception:
        return None


def generate_collage(image_paths: list[Path], params: CollageParams) -> Image.Image:
    """Genera una imagen tipo "pila de fotos" a partir de una lista de rutas de imagenes."""
    if not image_paths:
        raise ValueError("Se necesita al menos una imagen para armar el collage")

    rng = random.Random(params.seed)
    canvas = _make_background(params.canvas_size, image_paths, params).convert("RGBA")

    chosen = image_paths[:]
    rng.shuffle(chosen)
    chosen = chosen[: params.max_photos]

    canvas_w, canvas_h = params.canvas_size
    cols, rows, cell_w, cell_h = _grid(len(chosen), params.canvas_size)
    global_target_width = int(canvas_w * params.photo_scale)

    # espacio fijo que suman el marco y la sombra, para descontarlo del alto disponible
    border_extra_h = (params.border_width * 2 + params.bottom_border_extra) if params.border else 0
    shadow_pad = (params.shadow_blur * 3 + max(params.shadow_offset)) * 2 if params.shadow else 0
    # margen de seguridad para el jitter vertical de la posicion
    max_row_height = cell_h * 0.8

    positioned: list[tuple[Image.Image, int, int]] = []
    for i, path in enumerate(chosen):
        ratio = _photo_aspect_ratio(path)
        if ratio is None:
            continue

        max_content_h = max(max_row_height - border_extra_h - shadow_pad, 40)
        width_for_row = int(max_content_h / ratio)
        target_width = max(min(global_target_width, width_for_row), 40)

        try:
            framed = _framed_photo(path, target_width, params)
        except Exception:
            continue
        layer = _with_shadow(framed, params)

        angle = rng.uniform(-params.max_rotation_deg, params.max_rotation_deg)
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)

        col = i % cols
        row = i // cols
        cx = cell_w * (col + 0.5) + rng.uniform(-cell_w * 0.18, cell_w * 0.18)
        cy = cell_h * (row + 0.5) + rng.uniform(-cell_h * 0.12, cell_h * 0.12)
        x = int(cx - layer.width / 2)
        y = int(cy - layer.height / 2)
        positioned.append((layer, x, y))

    for layer, x, y in positioned:
        canvas.alpha_composite(layer, dest=(x, y))

    return canvas.convert("RGB")


def collage_from_folder(folder: Path, params: CollageParams, extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")) -> Image.Image:
    photos = [p for p in folder.rglob("*") if p.suffix.lower() in extensions and p.is_file()]
    return generate_collage(photos, params)
