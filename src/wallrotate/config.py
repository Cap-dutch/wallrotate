"""Almacenamiento de configuracion: perfiles de fondo de pantalla por monitor."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "wallrotate"
CONFIG_PATH = CONFIG_DIR / "config.json"
STATE_PATH = CONFIG_DIR / "state.json"
CACHE_DIR = Path.home() / ".cache" / "wallrotate"

SOURCE_TYPES = ("single_image", "folder_slideshow", "collage")


@dataclass
class CollageSettings:
    max_photos: int = 7
    max_rotation_deg: float = 18.0
    shadow: bool = True
    border: bool = True
    photo_scale: float = 0.32
    background: str = "blurred"  # "blurred" | "solid"
    photo_fit: str = "contain"  # "contain" = foto completa con fondo blanco | "cover" = recorta y llena el marco
    min_spacing: float = 0.55  # separacion minima entre fotos (0 = pueden superponerse del todo, 1+ = casi sin superposicion)
    layout: str = "scatter"  # scatter | bands | lines_h | lines_v | diagonal | diagonal_rev | x | oval
    band_top_fraction: float = 0.5  # solo "bands": alto de la banda superior (0..1)
    line_count: int = 2  # solo "lines_h"/"lines_v": cantidad de lineas (1-3)
    path_jitter: float = 0.12  # solo layouts con linea/curva: dispersion alrededor de la misma
    oval_fill: bool = False  # solo "oval": rellenar el interior en vez de solo el borde


@dataclass
class ScreenProfile:
    desktop_index: int
    screen_name: str = ""
    enabled: bool = True
    source_type: str = "folder_slideshow"
    source_path: str = ""
    interval_minutes: int = 30
    fill_mode: str = "rellenar"
    paused: bool = False
    collage: CollageSettings = field(default_factory=CollageSettings)

    @classmethod
    def from_dict(cls, data: dict) -> "ScreenProfile":
        collage_data = data.pop("collage", {})
        profile = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        profile.collage = CollageSettings(**collage_data)
        return profile


@dataclass
class Config:
    profiles: list[ScreenProfile] = field(default_factory=list)

    def profile_for(self, desktop_index: int) -> ScreenProfile | None:
        return next((p for p in self.profiles if p.desktop_index == desktop_index), None)


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    data = json.loads(CONFIG_PATH.read_text())
    profiles = [ScreenProfile.from_dict(dict(p)) for p in data.get("profiles", [])]
    return Config(profiles=profiles)


def save_config(config: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {"profiles": [asdict(p) for p in config.profiles]}
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text())


def save_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False))
