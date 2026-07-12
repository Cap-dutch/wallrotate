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


def _scatter_positions(n: int, canvas_size: tuple[int, int], photo_size: tuple[int, int], rng: random.Random) -> list[tuple[int, int]]:
    """Reparte n posiciones en una grilla con jitter, para que las fotos queden esparcidas."""
    w, h = canvas_size
    cols = max(1, round((n * w / h) ** 0.5))
    rows = max(1, -(-n // cols))  # ceil

    cell_w, cell_h = w / cols, h / rows
    positions = []
    for i in range(n):
        col = i % cols
        row = i // cols
        cx = cell_w * (col + 0.5) + rng.uniform(-cell_w * 0.22, cell_w * 0.22)
        cy = cell_h * (row + 0.5) + rng.uniform(-cell_h * 0.22, cell_h * 0.22)
        x = int(cx - photo_size[0] / 2)
        y = int(cy - photo_size[1] / 2)
        positions.append((x, y))
    return positions


def generate_collage(image_paths: list[Path], params: CollageParams) -> Image.Image:
    """Genera una imagen tipo "pila de fotos" a partir de una lista de rutas de imagenes."""
    if not image_paths:
        raise ValueError("Se necesita al menos una imagen para armar el collage")

    rng = random.Random(params.seed)
    canvas = _make_background(params.canvas_size, image_paths, params).convert("RGBA")

    chosen = image_paths[:]
    rng.shuffle(chosen)
    chosen = chosen[: params.max_photos]

    target_width = int(params.canvas_size[0] * params.photo_scale)
    layers: list[Image.Image] = []
    for path in chosen:
        try:
            framed = _framed_photo(path, target_width, params)
        except Exception:
            continue
        layer = _with_shadow(framed, params)

        angle = rng.uniform(-params.max_rotation_deg, params.max_rotation_deg)
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
        layers.append(layer)

    approx_size = (target_width, int(target_width * 0.75))
    positions = _scatter_positions(len(layers), params.canvas_size, approx_size, rng)

    for layer, (x, y) in zip(layers, positions):
        canvas.alpha_composite(layer, dest=(x, y))

    return canvas.convert("RGB")


def collage_from_folder(folder: Path, params: CollageParams, extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")) -> Image.Image:
    photos = [p for p in folder.rglob("*") if p.suffix.lower() in extensions and p.is_file()]
    return generate_collage(photos, params)
