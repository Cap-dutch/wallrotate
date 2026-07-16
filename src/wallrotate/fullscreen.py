"""Deteccion de ventana en primer plano a pantalla completa, via un script
de KWin cargado dinamicamente (funciona en X11 y Wayland porque consulta
directamente al compositor, en vez de inspeccionar ventanas por fuera)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Slot
from PySide6.QtDBus import QDBusConnection

log = logging.getLogger("wallrotate")

_SCRIPT_PATH = Path(__file__).parent / "resources" / "check_fullscreen.js"
_SERVICE_NAME = "com.wallrotate.FullscreenCheck"
_OBJECT_PATH = "/FullscreenCheck"
_PLUGIN_NAME = "wallrotate-fullscreen-check"


class _ReportReceiver(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.result: bool | None = None

    @Slot(bool)
    def Report(self, is_fullscreen: bool) -> None:
        self.result = is_fullscreen
        app = QCoreApplication.instance()
        if app is not None:
            app.quit()


def is_fullscreen_active(timeout_ms: int = 1500) -> bool:
    """Le pregunta a KWin si la ventana activa esta en pantalla completa.
    Falla "cerrado" (devuelve False) ante cualquier problema -- KWin no
    disponible, timeout, script roto -- para no bloquear la rotacion
    normal por este chequeo opcional."""
    if not _SCRIPT_PATH.exists():
        return False

    app = QCoreApplication.instance() or QCoreApplication([])

    receiver = _ReportReceiver()
    conn = QDBusConnection.sessionBus()
    if not conn.registerObject(_OBJECT_PATH, receiver, QDBusConnection.RegisterOption.ExportAllSlots):
        return False
    if not conn.registerService(_SERVICE_NAME):
        conn.unregisterObject(_OBJECT_PATH)
        return False

    try:
        load = subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "loadScript", str(_SCRIPT_PATH), _PLUGIN_NAME],
            capture_output=True, text=True, timeout=3,
        )
        script_id = load.stdout.strip()
        if not script_id.lstrip("-").isdigit():
            return False
        subprocess.run(
            ["qdbus6", "org.kde.KWin", f"/Scripting/Script{script_id}", "org.kde.kwin.Script.run"],
            capture_output=True, timeout=3,
        )
        QTimer.singleShot(timeout_ms, app.quit)
        app.exec()
    except Exception:
        log.warning("No se pudo consultar el estado de pantalla completa via KWin", exc_info=True)
        return False
    finally:
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "unloadScript", _PLUGIN_NAME],
            capture_output=True, timeout=3,
        )
        conn.unregisterService(_SERVICE_NAME)
        conn.unregisterObject(_OBJECT_PATH)

    return bool(receiver.result)
