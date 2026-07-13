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
    frame_aspect: float = 0.72  # alto/ancho del area de foto dentro del marco (fijo, como un polaroid real)
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


def _framed_photo(path: Path, content_width: int, content_height: int, params: CollageParams) -> Image.Image:
    """Abre una foto y la recorta/escala para llenar un marco de tamano fijo
    (como un polaroid real: el marco siempre mide lo mismo, sea la foto
    vertical, horizontal o cuadrada)."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im.convert("RGB"))
        im = ImageOps.fit(im, (content_width, content_height), method=Image.LANCZOS)

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


def _frame_content_size(params: CollageParams, canvas_width: int) -> tuple[int, int]:
    """Tamano (fijo, para todas las fotos) del area de imagen dentro del marco.
    Depende solo de photo_scale, nunca se recorta por una grilla."""
    content_width = max(int(canvas_width * params.photo_scale), 40)
    content_height = int(content_width * params.frame_aspect)
    return content_width, content_height


def _scatter_center(canvas_size: tuple[int, int], layer_size: tuple[int, int], rng: random.Random) -> tuple[float, float]:
    """Elige un centro al azar en todo el canvas, dejando que las fotos se
    superpongan libremente (estilo pila real), con un margen para que la
    mayor parte de cada foto quede visible."""
    w, h = canvas_size
    lw, lh = layer_size
    margin_x = min(lw * 0.3, w / 2)
    margin_y = min(lh * 0.3, h / 2)
    cx = rng.uniform(margin_x, max(w - margin_x, margin_x))
    cy = rng.uniform(margin_y, max(h - margin_y, margin_y))
    return cx, cy


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
    content_width, content_height = _frame_content_size(params, canvas_w)

    positioned: list[tuple[Image.Image, int, int]] = []
    for path in chosen:
        try:
            framed = _framed_photo(path, content_width, content_height, params)
        except Exception:
            continue
        layer = _with_shadow(framed, params)

        angle = rng.uniform(-params.max_rotation_deg, params.max_rotation_deg)
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)

        cx, cy = _scatter_center(params.canvas_size, layer.size, rng)
        x = int(cx - layer.width / 2)
        y = int(cy - layer.height / 2)
        positioned.append((layer, x, y))

    # orden aleatorio de dibujado, para que no siempre la ultima foto quede arriba de todas
    rng.shuffle(positioned)
    for layer, x, y in positioned:
        canvas.alpha_composite(layer, dest=(x, y))

    return canvas.convert("RGB")


def collage_from_folder(folder: Path, params: CollageParams, extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")) -> Image.Image:
    photos = [p for p in folder.rglob("*") if p.suffix.lower() in extensions and p.is_file()]
    return generate_collage(photos, params)
