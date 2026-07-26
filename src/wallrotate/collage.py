"""Generador de collages estilo "pila de fotos" (polaroid pile)."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps

LAYOUTS = ("scatter", "bands", "lines_h", "lines_v", "diagonal", "diagonal_rev", "x", "oval")


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
    frame_aspect: float = 1.0  # alto/ancho del area de foto dentro del marco (1.0 = cuadrado, como un polaroid real)
    photo_fit: str = "contain"  # "contain" = se ve la foto completa (con fondo blanco a los costados) | "cover" = recorta para llenar el marco
    background: str = "blurred"  # "blurred" | "solid"
    background_color: tuple[int, int, int] = (24, 24, 26)
    background_blur_radius: int = 40
    background_darken: float = 0.55  # 1.0 = sin oscurecer, 0.0 = negro
    min_spacing: float = 0.55  # distancia minima entre centros de fotos, como fraccion del tamano del marco (0 = sin restriccion, permite superposicion total)
    layout: str = "scatter"  # ver LAYOUTS: forma en la que se distribuyen las fotos en el canvas
    band_top_fraction: float = 0.5  # solo "bands": alto de la banda superior, como fraccion del canvas (0..1); el resto es la banda inferior
    line_count: int = 2  # solo "lines_h"/"lines_v": cantidad de lineas (1-3)
    path_jitter: float = 0.12  # solo "lines_*"/"diagonal*"/"x"/"oval": dispersion alrededor de la linea/curva, como fraccion del canvas
    oval_fill: bool = False  # solo "oval": False = fotos sobre el borde de la elipse, True = rellenan el interior
    seed: int | None = None


@dataclass
class PhotoPlacement:
    """Posicion final de una foto en el collage: centro, rotacion y escala
    (multiplicador sobre el tamano base de foto de CollageParams). Es la
    unidad editable -- el editor interactivo de la GUI ajusta estos valores
    y `render_from_layout` los usa para dibujar el resultado final."""

    path: Path
    cx: float
    cy: float
    angle: float = 0.0
    scale: float = 1.0


@dataclass
class CollageLayout:
    """Layout completo y reproducible de un collage: que fotos, donde, y
    cual se uso de fondo. `auto_layout` lo genera al azar; el editor
    interactivo de la GUI edita `placements` y pasa el mismo layout de
    vuelta a `render_from_layout` -- el fondo no cambia solo entre la
    vista previa y el resultado final editado."""

    placements: list[PhotoPlacement]
    background_path: Path | None = None


def _make_background(canvas_size: tuple[int, int], bg_path: Path | None, params: CollageParams) -> Image.Image:
    w, h = canvas_size
    if params.background == "solid" or bg_path is None:
        return Image.new("RGB", (w, h), params.background_color)

    with Image.open(bg_path) as im:
        im = ImageOps.exif_transpose(im.convert("RGB"))
        bg = ImageOps.fit(im, (w, h), method=Image.LANCZOS)

    bg = bg.filter(ImageFilter.GaussianBlur(params.background_blur_radius))
    if params.background_darken < 1.0:
        bg = ImageEnhance.Brightness(bg).enhance(params.background_darken)
    return bg


def _framed_photo(path: Path, content_width: int, content_height: int, params: CollageParams) -> Image.Image:
    """Abre una foto y la ubica en un marco de tamano fijo (como un polaroid
    real: el marco siempre mide lo mismo, sea la foto vertical, horizontal o
    cuadrada). En modo "contain" se ve la foto completa, sin recortar, con
    fondo blanco donde sobre espacio; en "cover" se recorta para llenar todo
    el marco."""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im.convert("RGB"))
        if params.photo_fit == "cover":
            im = ImageOps.fit(im, (content_width, content_height), method=Image.LANCZOS)
        else:
            fitted = ImageOps.contain(im, (content_width, content_height), method=Image.LANCZOS)
            canvas = Image.new("RGB", (content_width, content_height), (250, 250, 248))
            canvas.paste(fitted, ((content_width - fitted.width) // 2, (content_height - fitted.height) // 2))
            im = canvas

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


def _layer_size_before_rotation(content_size: tuple[int, int], params: CollageParams) -> tuple[int, int]:
    """Tamano del marco+sombra (sin rotar todavia), calculado analiticamente
    a partir del tamano del area de foto, sin necesidad de renderizar nada."""
    cw, ch = content_size
    if params.border:
        bw = params.border_width
        bottom = bw + params.bottom_border_extra
        fw, fh = cw + bw * 2, ch + bw + bottom
    else:
        fw, fh = cw, ch
    if params.shadow:
        pad = params.shadow_blur * 3 + max(params.shadow_offset)
        fw, fh = fw + pad * 2, fh + pad * 2
    return fw, fh


def _rotated_bbox_size(w: int, h: int, angle_deg: float) -> tuple[int, int]:
    """Tamano del rectangulo que contiene a un WxH rotado angle_deg grados,
    igual al que produce Image.rotate(expand=True) pero sin renderizar."""
    rad = math.radians(angle_deg)
    new_w = abs(w * math.cos(rad)) + abs(h * math.sin(rad))
    new_h = abs(w * math.sin(rad)) + abs(h * math.cos(rad))
    return max(int(round(new_w)), 1), max(int(round(new_h)), 1)


def _scatter_center(
    region: tuple[float, float, float, float],
    layer_size: tuple[int, int],
    rng: random.Random,
    existing: list[tuple[float, float]],
    min_dist: float,
    attempts: int = 25,
) -> tuple[float, float]:
    """Elige un centro al azar dentro de `region` (rx0, rx1, ry0, ry1),
    evitando quedar demasiado cerca de fotos ya colocadas -- permite
    superposicion parcial (da el aspecto de pila) pero no que una foto tape
    a otra por completo. Si no encuentra un lugar libre tras varios
    intentos, usa el mejor candidato encontrado. Con region = (0, w, 0, h)
    se comporta igual que la dispersion original en todo el canvas."""
    rx0, rx1, ry0, ry1 = region
    lw, lh = layer_size
    margin_x = min(lw * 0.3, (rx1 - rx0) / 2)
    margin_y = min(lh * 0.3, (ry1 - ry0) / 2)
    lo_x, hi_x = rx0 + margin_x, max(rx1 - margin_x, rx0 + margin_x)
    lo_y, hi_y = ry0 + margin_y, max(ry1 - margin_y, ry0 + margin_y)

    best_pos = None
    best_score = -1.0
    for _ in range(attempts):
        cx = rng.uniform(lo_x, hi_x)
        cy = rng.uniform(lo_y, hi_y)
        if not existing:
            return cx, cy
        nearest = min(((cx - ex) ** 2 + (cy - ey) ** 2) ** 0.5 for ex, ey in existing)
        if nearest >= min_dist:
            return cx, cy
        if nearest > best_score:
            best_score = nearest
            best_pos = (cx, cy)
    return best_pos


def _region_for_index(
    layout: str,
    index: int,
    total: int,
    canvas_size: tuple[int, int],
    rng: random.Random,
    params: CollageParams,
) -> tuple[float, float, float, float]:
    """Region (rx0, rx1, ry0, ry1) dentro de la cual puede caer la foto
    `index` de `total`, segun el layout elegido. Cada foto sigue teniendo
    dispersion/repulsion dentro de su region via `_scatter_center`."""
    w, h = canvas_size
    total = max(total, 1)

    if layout == "bands":
        top_h = h * params.band_top_fraction
        if (index / total) < params.band_top_fraction:
            return (0, w, 0, top_h)
        return (0, w, top_h, h)

    if layout in ("lines_h", "lines_v"):
        k = max(1, min(3, params.line_count))
        li = min(int(index * k / total), k - 1)
        if layout == "lines_h":
            line_y = (li + 0.5) / k * h
            thickness = max(params.path_jitter * h, 1.0)
            return (0, w, line_y - thickness / 2, line_y + thickness / 2)
        line_x = (li + 0.5) / k * w
        thickness = max(params.path_jitter * w, 1.0)
        return (line_x - thickness / 2, line_x + thickness / 2, 0, h)

    if layout in ("diagonal", "diagonal_rev", "x"):
        if layout == "x":
            half = total // 2
            if index < half:
                t = (index + 0.5) / max(half, 1)
                sub = "diagonal"
            else:
                t = (index - half + 0.5) / max(total - half, 1)
                sub = "diagonal_rev"
        else:
            t = (index + 0.5) / total
            sub = layout
        cx = t * w if sub == "diagonal" else w - t * w
        cy = t * h
        thickness = max(params.path_jitter * min(w, h), 1.0)
        return (cx - thickness, cx + thickness, cy - thickness, cy + thickness)

    if layout == "oval":
        cx0, cy0 = w / 2, h / 2
        a, b = w * 0.38, h * 0.38
        angle = 2 * math.pi * (index + 0.5) / total
        radius_frac = math.sqrt(rng.random()) if params.oval_fill else 1.0
        cx = cx0 + radius_frac * a * math.cos(angle)
        cy = cy0 + radius_frac * b * math.sin(angle)
        thickness = max(params.path_jitter * min(w, h), 1.0)
        return (cx - thickness, cx + thickness, cy - thickness, cy + thickness)

    # "scatter" (default): toda la region del canvas, comportamiento original
    return (0, w, 0, h)


def _render_placement(
    placement: PhotoPlacement, base_content_size: tuple[int, int], params: CollageParams
) -> tuple[Image.Image, int, int]:
    """Renderiza una foto (marco + sombra + rotacion) segun su PhotoPlacement.
    Devuelve la capa ya rotada y la posicion (x, y) de su esquina superior
    izquierda en el canvas."""
    cw = max(int(base_content_size[0] * placement.scale), 20)
    ch = max(int(base_content_size[1] * placement.scale), 20)
    framed = _framed_photo(placement.path, cw, ch, params)
    layer = _with_shadow(framed, params)
    layer = layer.rotate(placement.angle, expand=True, resample=Image.BICUBIC)
    x = int(placement.cx - layer.width / 2)
    y = int(placement.cy - layer.height / 2)
    return layer, x, y


def render_photo_base(path: Path, content_size: tuple[int, int], scale: float, params: CollageParams) -> Image.Image:
    """Renderiza una foto con marco y sombra, SIN rotar (angulo=0) -- pensado
    para editores interactivos (Qt) que aplican rotacion/escala ellos mismos
    via transformaciones del canvas, en vez de rotar el raster con Pillow en
    cada frame de arrastre."""
    cw = max(int(content_size[0] * scale), 20)
    ch = max(int(content_size[1] * scale), 20)
    framed = _framed_photo(path, cw, ch, params)
    return _with_shadow(framed, params)


def render_background(background_path: Path | None, canvas_size: tuple[int, int], params: CollageParams) -> Image.Image:
    """Wrapper publico sobre el fondo difuminado/solido, para editores
    interactivos que necesitan mostrarlo como base del lienzo."""
    return _make_background(canvas_size, background_path, params)


def base_content_size(params: CollageParams) -> tuple[int, int]:
    """Tamano base (escala 1.0) del area de foto dentro del marco, segun el
    ancho del canvas configurado."""
    return _frame_content_size(params, params.canvas_size[0])


def auto_layout(image_paths: list[Path], params: CollageParams) -> CollageLayout:
    """Elige fotos y calcula su posicion/rotacion al azar (sin renderizar
    nada todavia), respetando el layout elegido (bandas, lineas, etc.) y la
    separacion minima entre fotos. El orden de la lista es el orden de
    dibujado (z-order): las ultimas quedan arriba de las primeras. Tambien
    elige (una sola vez) la foto de fondo difuminado."""
    if not image_paths:
        raise ValueError("Se necesita al menos una imagen para armar el collage")

    rng = random.Random(params.seed)
    background_path = rng.choice(image_paths)

    chosen = image_paths[:]
    rng.shuffle(chosen)
    chosen = chosen[: params.max_photos]

    canvas_w, canvas_h = params.canvas_size
    base_content_size = _frame_content_size(params, canvas_w)
    pre_rotation_size = _layer_size_before_rotation(base_content_size, params)

    placements: list[PhotoPlacement] = []
    centers: list[tuple[float, float]] = []
    total = len(chosen)
    for index, path in enumerate(chosen):
        angle = rng.uniform(-params.max_rotation_deg, params.max_rotation_deg)
        layer_w, layer_h = _rotated_bbox_size(pre_rotation_size[0], pre_rotation_size[1], angle)

        min_dist = max(base_content_size) * params.min_spacing
        region = _region_for_index(params.layout, index, total, params.canvas_size, rng, params)
        cx, cy = _scatter_center(region, (layer_w, layer_h), rng, centers, min_dist)
        centers.append((cx, cy))
        placements.append(PhotoPlacement(path=path, cx=cx, cy=cy, angle=angle, scale=1.0))

    # orden aleatorio de dibujado, para que no siempre la ultima foto quede arriba de todas
    rng.shuffle(placements)
    return CollageLayout(placements=placements, background_path=background_path)


def render_from_layout(layout: CollageLayout, params: CollageParams) -> Image.Image:
    """Renderiza la imagen final a partir de un CollageLayout ya definido
    (generado por auto_layout, o editado a mano por el usuario). El orden
    de `layout.placements` determina el z-order (ultimas = arriba)."""
    canvas_w = params.canvas_size[0]
    base_content_size = _frame_content_size(params, canvas_w)
    canvas = _make_background(params.canvas_size, layout.background_path, params).convert("RGBA")

    for placement in layout.placements:
        try:
            layer, x, y = _render_placement(placement, base_content_size, params)
        except Exception:
            continue
        canvas.alpha_composite(layer, dest=(x, y))

    return canvas.convert("RGB")


def generate_collage(image_paths: list[Path], params: CollageParams) -> Image.Image:
    """Genera una imagen tipo "pila de fotos" a partir de una lista de rutas de imagenes."""
    layout = auto_layout(image_paths, params)
    return render_from_layout(layout, params)


def collage_from_folder(folder: Path, params: CollageParams, extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")) -> Image.Image:
    photos = [p for p in folder.rglob("*") if p.suffix.lower() in extensions and p.is_file()]
    return generate_collage(photos, params)
