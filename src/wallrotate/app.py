"""GUI de configuracion de WallRotate."""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import plasma_bridge
from .collage import CollageParams, generate_collage
from .config import CACHE_DIR, CONFIG_PATH, Config, ScreenProfile, load_config, save_config
from .engine import apply_profile, current_image_path, go_next, go_previous, run_once, toggle_pause
from .config import load_state, save_state

AUTOSTART_PATH = Path.home() / ".config" / "autostart" / "wallrotate.desktop"
_AUTOSTART_CONTENT = """[Desktop Entry]
Type=Application
Name=WallRotate
Comment=Rotador de fondos de pantalla con collage, por monitor
Exec=wallrotate
Icon=preferences-desktop-wallpaper
Terminal=false
Categories=Utility;DesktopSettings;
X-GNOME-Autostart-enabled=true
"""


def is_autostart_enabled() -> bool:
    return AUTOSTART_PATH.exists()


def set_autostart(enabled: bool) -> None:
    if enabled:
        AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_PATH.write_text(_AUTOSTART_CONTENT)
    else:
        AUTOSTART_PATH.unlink(missing_ok=True)

APP_ICON_PATH = Path(__file__).parent / "resources" / "icon.svg"
APP_ICON_NAMES = ("preferences-desktop-wallpaper", "image-x-generic", "applications-graphics")
# tamanos tipicos que pide el protocolo StatusNotifierItem (bandeja del sistema)
_TRAY_ICON_SIZES = (16, 22, 24, 32, 48, 64, 128)


def _app_icon() -> QIcon:
    if APP_ICON_PATH.exists():
        # Renderizar el SVG a pixmaps concretos en los tamanos que pide la
        # bandeja del sistema. Dejar que Qt convierta el SVG "al vuelo" al
        # exportar el icono por D-Bus (StatusNotifierItem) da pixeles vacios
        # en algunos tamanos (bug observado con QIcon(svg_path) directo).
        renderer_icon = QIcon(str(APP_ICON_PATH))
        if not renderer_icon.isNull():
            icon = QIcon()
            for size in _TRAY_ICON_SIZES:
                pixmap = renderer_icon.pixmap(QSize(size, size))
                if not pixmap.isNull():
                    icon.addPixmap(pixmap)
            if not icon.isNull():
                return icon
    for name in APP_ICON_NAMES:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    return QIcon.fromTheme("image")

SOURCE_LABELS = {
    "single_image": "Imagen fija",
    "folder_slideshow": "Carpeta (slideshow)",
    "collage": "Collage",
}
SOURCE_KEYS = {v: k for k, v in SOURCE_LABELS.items()}

FIT_LABELS = {
    "contain": "Foto completa (fondo blanco a los costados)",
    "cover": "Recortar y llenar el marco",
}
FIT_KEYS = {v: k for k, v in FIT_LABELS.items()}

FILL_LABELS = {
    "rellenar": "Rellenar (recorta)",
    "ajustar": "Ajustar (con bordes)",
    "estirar": "Estirar",
    "centrado": "Centrado",
    "mosaico": "Mosaico",
}

LAYOUT_LABELS = {
    "scatter": "Dispersion libre (pila)",
    "bands": "Bandas (superior/inferior)",
    "lines_h": "Lineas horizontales",
    "lines_v": "Lineas verticales",
    "diagonal": "Diagonal (arriba-izq. a abajo-der.)",
    "diagonal_rev": "Diagonal (arriba-der. a abajo-izq.)",
    "x": "En X",
    "oval": "Ovalo",
}
LAYOUT_KEYS = {v: k for k, v in LAYOUT_LABELS.items()}


class ScreenTab(QWidget):
    def __init__(self, screen: plasma_bridge.ScreenInfo, profile: ScreenProfile):
        super().__init__()
        self.screen = screen
        self.profile = profile
        self._build_ui()
        self._load_from_profile()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        info = QLabel(f"<b>{self.screen.name}</b> — {self.screen.width}x{self.screen.height}")
        root.addWidget(info)

        self.enabled_check = QCheckBox("Activar rotacion en esta pantalla")
        root.addWidget(self.enabled_check)

        form = QFormLayout()

        self.source_combo = QComboBox()
        self.source_combo.addItems(SOURCE_LABELS.values())
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        form.addRow("Fuente:", self.source_combo)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.browse_btn = QPushButton("Elegir...")
        self.browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(self.browse_btn)
        form.addRow("Carpeta/Imagen:", path_row)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setSuffix(" min")
        form.addRow("Cambiar cada:", self.interval_spin)

        self.fill_combo = QComboBox()
        self.fill_combo.addItems(FILL_LABELS.values())
        form.addRow("Ajuste de imagen:", self.fill_combo)

        root.addLayout(form)

        self.collage_box = QGroupBox("Parametros del collage")
        cform = QFormLayout(self.collage_box)

        self.max_photos_spin = QSpinBox()
        self.max_photos_spin.setRange(2, 20)
        cform.addRow("Cantidad de fotos:", self.max_photos_spin)

        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(0, 40)
        cform.addRow("Rotacion maxima (grados):", self.rotation_slider)

        self.shadow_check = QCheckBox("Sombra")
        cform.addRow("", self.shadow_check)

        self.border_check = QCheckBox("Marco tipo polaroid")
        cform.addRow("", self.border_check)

        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(5, 100)
        cform.addRow("Tamano de cada foto (%):", self.scale_slider)

        self.fit_combo = QComboBox()
        self.fit_combo.addItems(FIT_LABELS.values())
        cform.addRow("Foto dentro del marco:", self.fit_combo)

        self.spacing_slider = QSlider(Qt.Horizontal)
        self.spacing_slider.setRange(0, 150)
        cform.addRow("Separacion minima entre fotos (%):", self.spacing_slider)

        self.background_combo = QComboBox()
        self.background_combo.addItems(["blurred", "solid"])
        cform.addRow("Fondo:", self.background_combo)

        self.layout_combo = QComboBox()
        self.layout_combo.addItems(LAYOUT_LABELS.values())
        self.layout_combo.currentTextChanged.connect(self._on_layout_changed)
        cform.addRow("Distribucion de fotos:", self.layout_combo)

        self.band_top_slider = QSlider(Qt.Horizontal)
        self.band_top_slider.setRange(10, 90)
        cform.addRow("Banda superior (%):", self.band_top_slider)

        self.line_count_spin = QSpinBox()
        self.line_count_spin.setRange(1, 3)
        cform.addRow("Cantidad de lineas:", self.line_count_spin)

        self.path_jitter_slider = QSlider(Qt.Horizontal)
        self.path_jitter_slider.setRange(2, 40)
        cform.addRow("Dispersion alrededor de la linea (%):", self.path_jitter_slider)

        self.oval_fill_check = QCheckBox("Rellenar interior del ovalo (no solo el borde)")
        cform.addRow("", self.oval_fill_check)

        self.collage_form = cform
        root.addWidget(self.collage_box)

        btn_row = QHBoxLayout()
        self.preview_btn = QPushButton("Vista previa")
        self.preview_btn.clicked.connect(self._preview)
        self.apply_btn = QPushButton("Aplicar ahora")
        self.apply_btn.clicked.connect(self._apply_now)
        btn_row.addWidget(self.preview_btn)
        btn_row.addWidget(self.apply_btn)
        root.addLayout(btn_row)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet("background: #111; border: 1px solid #333;")
        root.addWidget(self.preview_label)

        root.addStretch()

    def _on_source_changed(self, text: str) -> None:
        self.collage_box.setVisible(SOURCE_KEYS.get(text) == "collage")

    def _set_row_visible(self, widget: QWidget, visible: bool) -> None:
        label = self.collage_form.labelForField(widget)
        if label is not None:
            label.setVisible(visible)
        widget.setVisible(visible)

    def _on_layout_changed(self, text: str) -> None:
        key = LAYOUT_KEYS.get(text, "scatter")
        self._set_row_visible(self.band_top_slider, key == "bands")
        self._set_row_visible(self.line_count_spin, key in ("lines_h", "lines_v"))
        self._set_row_visible(self.path_jitter_slider, key not in ("scatter", "bands"))
        self._set_row_visible(self.oval_fill_check, key == "oval")

    def _browse(self) -> None:
        source_key = SOURCE_KEYS[self.source_combo.currentText()]
        if source_key == "single_image":
            path, _ = QFileDialog.getOpenFileName(self, "Elegir imagen", str(Path.home()), "Imagenes (*.png *.jpg *.jpeg *.webp)")
        else:
            path = QFileDialog.getExistingDirectory(self, "Elegir carpeta", str(Path.home()))
        if path:
            self.path_edit.setText(path)

    def _load_from_profile(self) -> None:
        p = self.profile
        self.enabled_check.setChecked(p.enabled)
        self.source_combo.setCurrentText(SOURCE_LABELS.get(p.source_type, SOURCE_LABELS["folder_slideshow"]))
        self.path_edit.setText(p.source_path)
        self.interval_spin.setValue(p.interval_minutes)
        self.fill_combo.setCurrentText(FILL_LABELS.get(p.fill_mode, FILL_LABELS["rellenar"]))
        self.max_photos_spin.setValue(p.collage.max_photos)
        self.rotation_slider.setValue(int(p.collage.max_rotation_deg))
        self.shadow_check.setChecked(p.collage.shadow)
        self.border_check.setChecked(p.collage.border)
        self.scale_slider.setValue(int(p.collage.photo_scale * 100))
        self.fit_combo.setCurrentText(FIT_LABELS.get(p.collage.photo_fit, FIT_LABELS["contain"]))
        self.spacing_slider.setValue(int(p.collage.min_spacing * 100))
        self.background_combo.setCurrentText(p.collage.background)
        self.layout_combo.setCurrentText(LAYOUT_LABELS.get(p.collage.layout, LAYOUT_LABELS["scatter"]))
        self.band_top_slider.setValue(int(p.collage.band_top_fraction * 100))
        self.line_count_spin.setValue(p.collage.line_count)
        self.path_jitter_slider.setValue(int(p.collage.path_jitter * 100))
        self.oval_fill_check.setChecked(p.collage.oval_fill)
        self._on_layout_changed(self.layout_combo.currentText())
        self.collage_box.setVisible(p.source_type == "collage")

    def to_profile(self) -> ScreenProfile:
        p = self.profile
        p.enabled = self.enabled_check.isChecked()
        p.source_type = SOURCE_KEYS[self.source_combo.currentText()]
        p.source_path = self.path_edit.text().strip()
        p.interval_minutes = self.interval_spin.value()
        fill_key = {v: k for k, v in FILL_LABELS.items()}[self.fill_combo.currentText()]
        p.fill_mode = fill_key
        p.collage.max_photos = self.max_photos_spin.value()
        p.collage.max_rotation_deg = float(self.rotation_slider.value())
        p.collage.shadow = self.shadow_check.isChecked()
        p.collage.border = self.border_check.isChecked()
        p.collage.photo_scale = self.scale_slider.value() / 100
        p.collage.photo_fit = FIT_KEYS[self.fit_combo.currentText()]
        p.collage.min_spacing = self.spacing_slider.value() / 100
        p.collage.background = self.background_combo.currentText()
        p.collage.layout = LAYOUT_KEYS[self.layout_combo.currentText()]
        p.collage.band_top_fraction = self.band_top_slider.value() / 100
        p.collage.line_count = self.line_count_spin.value()
        p.collage.path_jitter = self.path_jitter_slider.value() / 100
        p.collage.oval_fill = self.oval_fill_check.isChecked()
        return p

    def _preview(self) -> None:
        profile = self.to_profile()
        if not profile.source_path:
            QMessageBox.warning(self, "Falta carpeta/imagen", "Elegi una carpeta o imagen primero.")
            return
        try:
            if profile.source_type == "collage":
                images = [p for p in Path(profile.source_path).rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
                params = CollageParams(
                    canvas_size=(self.screen.width or 1920, self.screen.height or 1080),
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
                preview_path = Path("/tmp") / f"wallrotate_preview_{self.screen.desktop_index}.png"
                img.save(preview_path)
            elif profile.source_type == "single_image":
                preview_path = Path(profile.source_path)
            else:
                images = [p for p in Path(profile.source_path).rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
                if not images:
                    raise ValueError("La carpeta no tiene imagenes")
                preview_path = images[0]
        except Exception as exc:
            QMessageBox.critical(self, "Error generando la vista previa", str(exc))
            return

        pixmap = QPixmap(str(preview_path)).scaledToWidth(500, Qt.SmoothTransformation)
        self.preview_label.setPixmap(pixmap)

    def _apply_now(self) -> None:
        profile = self.to_profile()
        if not profile.source_path:
            QMessageBox.warning(self, "Falta carpeta/imagen", "Elegi una carpeta o imagen primero.")
            return
        state = load_state()
        try:
            apply_profile(profile, state)
        except Exception as exc:
            QMessageBox.critical(self, "Error aplicando el fondo", str(exc))
            return
        save_state(state)
        QMessageBox.information(self, "Listo", f"Fondo aplicado en {self.screen.name}.")


def _wallrotate_version() -> str:
    try:
        return version("wallrotate")
    except PackageNotFoundError:
        return "dev"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Acerca de WallRotate")
        self.resize(460, 480)

        layout = QVBoxLayout(self)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(
            f"<h3>WallRotate {_wallrotate_version()}</h3>"
            "<p>Rotador de fondos de pantalla por monitor para KDE Plasma, con "
            "generador de collage tipo \"pila de fotos\" a partir de tus propias "
            "imagenes.</p>"
            "<p>Inspirado en "
            "<a href=\"https://johnsad.ventures/software/backgroundswitcher/\">John's "
            "Background Switcher</a> (Windows/macOS, sin version Linux).</p>"
            "<p>Licencia MIT — codigo en "
            "<a href=\"https://github.com/Cap-dutch/wallrotate\">github.com/Cap-dutch/wallrotate</a>.</p>"
            "<h3>Ayuda</h3>"
            "<ul>"
            "<li>Cada pestaña es un monitor detectado: elegí fuente (imagen fija, "
            "carpeta en slideshow o collage), intervalo y ajuste, y guardá.</li>"
            "<li>El icono de la bandeja del sistema tiene, por pantalla, "
            "Siguiente fondo / Fondo anterior / Pausar / Ver imagen actual / "
            "Guardar imagen actual.</li>"
            "<li>La rotación automática corre en segundo plano vía systemd timer, "
            "aunque cierres esta ventana (cerrar solo la oculta).</li>"
            "<li>\"Vista previa\" genera la imagen sin aplicarla; \"Aplicar ahora\" "
            "la pone de fondo en esa pantalla.</li>"
            "</ul>"
        )
        layout.addWidget(browser)

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WallRotate")
        self.resize(720, 640)
        self.setWindowIcon(_app_icon())
        self._really_quit = False
        is_first_run = not CONFIG_PATH.exists()

        self.config = load_config()
        self.screens = plasma_bridge.list_screens()

        self.tabs = QTabWidget()
        self.screen_tabs: list[ScreenTab] = []
        for screen in self.screens:
            profile = self.config.profile_for(screen.desktop_index) or ScreenProfile(
                desktop_index=screen.desktop_index, screen_name=screen.name
            )
            tab = ScreenTab(screen, profile)
            self.screen_tabs.append(tab)
            self.tabs.addTab(tab, screen.name)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.tabs)

        self.autostart_check = QCheckBox("Iniciar automaticamente con el sistema")
        self.autostart_check.setChecked(is_autostart_enabled())
        self.autostart_check.toggled.connect(self._on_autostart_toggled)
        layout.addWidget(self.autostart_check)

        save_row = QHBoxLayout()
        save_btn = QPushButton("Guardar configuracion")
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)

        about_btn = QPushButton("?")
        about_btn.setFixedSize(34, 34)
        about_btn.setStyleSheet(
            "QPushButton {"
            "  border-radius: 17px;"
            "  border: 2px solid #3daee9;"
            "  font-weight: bold;"
            "  font-size: 16px;"
            "}"
            "QPushButton:hover { background: rgba(61, 174, 233, 60); }"
        )
        about_btn.setToolTip("Ayuda / Acerca de")
        about_btn.clicked.connect(self._show_about)
        save_row.addWidget(about_btn)

        layout.addLayout(save_row)

        self.setCentralWidget(central)
        self._setup_tray()

        if is_first_run:
            self._ask_autostart_first_run()

    def _on_autostart_toggled(self, checked: bool) -> None:
        set_autostart(checked)

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _ask_autostart_first_run(self) -> None:
        answer = QMessageBox.question(
            self,
            "Autoarranque",
            "¿Queres que WallRotate arranque automaticamente cada vez que inicies sesion?\n\n"
            "Podes cambiar esto despues con el casillero de la ventana principal.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        enabled = answer == QMessageBox.Yes
        set_autostart(enabled)
        self.autostart_check.setChecked(enabled)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(_app_icon(), self)
        self.tray.setToolTip("WallRotate")
        self._pause_actions: dict[int, "QAction"] = {}

        menu = QMenu()
        show_action = menu.addAction("Abrir")
        show_action.triggered.connect(self._show_from_tray)
        rotate_action = menu.addAction("Rotar ahora (todas)")
        rotate_action.triggered.connect(self._rotate_now_all)
        menu.addSeparator()

        for screen in self.screens:
            idx = screen.desktop_index
            submenu = menu.addMenu(screen.name)

            next_action = submenu.addAction("Siguiente fondo")
            next_action.triggered.connect(lambda checked=False, i=idx: self._next_screen(i))

            prev_action = submenu.addAction("Fondo anterior")
            prev_action.triggered.connect(lambda checked=False, i=idx: self._previous_screen(i))

            submenu.addSeparator()

            pause_action = submenu.addAction("Pausar rotacion")
            pause_action.setCheckable(True)
            profile = self.config.profile_for(idx)
            pause_action.setChecked(bool(profile and profile.paused))
            pause_action.triggered.connect(lambda checked=False, i=idx: self._toggle_pause_screen(i))
            self._pause_actions[idx] = pause_action

            submenu.addSeparator()

            view_action = submenu.addAction("Ver imagen actual")
            view_action.triggered.connect(lambda checked=False, i=idx: self._view_current(i))

            save_action = submenu.addAction("Guardar imagen actual como...")
            save_action.triggered.connect(lambda checked=False, i=idx: self._save_current_as(i))

        menu.addSeparator()
        cache_action = menu.addAction("Navegador de imagenes en cache")
        cache_action.triggered.connect(self._open_cache_browser)

        menu.addSeparator()
        quit_action = menu.addAction("Salir")
        quit_action.triggered.connect(self._quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _next_screen(self, desktop_index: int) -> None:
        if go_next(desktop_index):
            self.tray.showMessage("WallRotate", "Siguiente fondo aplicado.", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            self.tray.showMessage("WallRotate", "No se pudo avanzar (revisa la carpeta configurada).", QSystemTrayIcon.MessageIcon.Warning, 3000)

    def _previous_screen(self, desktop_index: int) -> None:
        if not go_previous(desktop_index):
            self.tray.showMessage("WallRotate", "No hay un fondo anterior guardado todavia.", QSystemTrayIcon.MessageIcon.Information, 2500)

    def _toggle_pause_screen(self, desktop_index: int) -> None:
        paused = toggle_pause(desktop_index)
        action = self._pause_actions.get(desktop_index)
        if action is not None:
            action.setChecked(paused)
        estado = "pausada" if paused else "reanudada"
        self.tray.showMessage("WallRotate", f"Rotacion {estado}.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def _view_current(self, desktop_index: int) -> None:
        path = current_image_path(desktop_index)
        if path is None or not path.exists():
            QMessageBox.information(self, "Sin imagen", "Todavia no hay una imagen aplicada en esta pantalla.")
            return
        subprocess.Popen(["xdg-open", str(path)])

    def _save_current_as(self, desktop_index: int) -> None:
        path = current_image_path(desktop_index)
        if path is None or not path.exists():
            QMessageBox.information(self, "Sin imagen", "Todavia no hay una imagen aplicada en esta pantalla.")
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Guardar imagen como...", str(Path.home() / path.name), "Imagen (*.png *.jpg *.jpeg)")
        if dest:
            shutil.copy(path, dest)

    def _open_cache_browser(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["xdg-open", str(CACHE_DIR)])

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _rotate_now_all(self) -> None:
        run_once(force=True)
        self.tray.showMessage("WallRotate", "Fondos rotados en todas las pantallas activas.", QSystemTrayIcon.MessageIcon.Information, 3000)

    def _quit(self) -> None:
        self._really_quit = True
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:
        if self._really_quit:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage("WallRotate", "Sigue corriendo en la bandeja del sistema.", QSystemTrayIcon.MessageIcon.Information, 3000)

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            event.ignore()
            self.hide()
        else:
            super().changeEvent(event)

    def _save(self) -> None:
        profiles = [tab.to_profile() for tab in self.screen_tabs]
        self.config = Config(profiles=profiles)
        save_config(self.config)
        QMessageBox.information(self, "Guardado", "Configuracion guardada. El timer de systemd aplicara los cambios segun el intervalo de cada pantalla.")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WallRotate")
    app.setApplicationDisplayName("WallRotate")
    app.setDesktopFileName("wallrotate")
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
