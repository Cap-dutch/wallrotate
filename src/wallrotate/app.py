"""GUI de configuracion de WallRotate."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QVBoxLayout,
    QWidget,
)

from . import plasma_bridge
from .collage import CollageParams, generate_collage
from .config import Config, ScreenProfile, load_config, save_config
from .engine import apply_profile, run_once
from .config import load_state, save_state

APP_ICON_PATH = Path(__file__).parent / "resources" / "icon.svg"
APP_ICON_NAMES = ("preferences-desktop-wallpaper", "image-x-generic", "applications-graphics")


def _app_icon() -> QIcon:
    if APP_ICON_PATH.exists():
        icon = QIcon(str(APP_ICON_PATH))
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

FILL_LABELS = {
    "rellenar": "Rellenar (recorta)",
    "ajustar": "Ajustar (con bordes)",
    "estirar": "Estirar",
    "centrado": "Centrado",
    "mosaico": "Mosaico",
}


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
        self.scale_slider.setRange(10, 60)
        cform.addRow("Tamano de cada foto (%):", self.scale_slider)

        self.background_combo = QComboBox()
        self.background_combo.addItems(["blurred", "solid"])
        cform.addRow("Fondo:", self.background_combo)

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
        self.background_combo.setCurrentText(p.collage.background)
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
        p.collage.background = self.background_combo.currentText()
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
                    background=profile.collage.background,
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WallRotate")
        self.resize(720, 640)
        self.setWindowIcon(_app_icon())
        self._really_quit = False

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

        save_btn = QPushButton("Guardar configuracion")
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

        self.setCentralWidget(central)
        self._setup_tray()

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(_app_icon(), self)
        self.tray.setToolTip("WallRotate")

        menu = QMenu()
        show_action = menu.addAction("Abrir")
        show_action.triggered.connect(self._show_from_tray)
        rotate_action = menu.addAction("Rotar ahora")
        rotate_action.triggered.connect(self._rotate_now_all)
        menu.addSeparator()
        quit_action = menu.addAction("Salir")
        quit_action.triggered.connect(self._quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

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
