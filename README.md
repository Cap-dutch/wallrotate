# WallRotate

Rotador de fondos de pantalla para KDE Plasma, con soporte de **collage
tipo "pila de fotos"** generado automáticamente a partir de tus propias
imágenes — configurable de forma independiente por cada monitor.

Nace como reemplazo de [John's Background Switcher](https://johnsad.ventures/software/backgroundswitcher/)
(Windows/macOS, sin versión Linux) para quienes quieren ese mismo efecto
de fotos "esparcidas" tipo polaroid en su escritorio Linux.

<!-- Capturas de ejemplo — reemplazar con imágenes propias sin contenido sensible
![Vista de la app](docs/screenshot-app.png)
![Ejemplo de collage generado](docs/screenshot-collage.png)
-->

## Features

- **Por monitor**: cada pantalla conectada tiene su propio perfil independiente (detecta automáticamente cuántos monitores tenés).
- **Tres modos de fuente**:
  - Imagen fija.
  - Carpeta en modo slideshow (una foto a la vez, rotando).
  - **Collage**: compone varias fotos de una carpeta en una sola imagen, con marco tipo polaroid, sombra difusa, rotación aleatoria y fondo difuminado.
- **Intervalo configurable** por pantalla (en minutos).
- **Modo de ajuste de imagen**: rellenar, ajustar, estirar, centrado, mosaico.
- **Parámetros de collage ajustables**: cantidad de fotos, ángulo máximo de rotación, sombra on/off, marco on/off, tamaño relativo de cada foto, tipo de fondo (difuminado o color sólido).
- **Vista previa** antes de aplicar.
- **Rotación automática en segundo plano** vía `systemd --user timer`, no depende de que la app esté abierta.

## Instalación

Requiere Python 3.13+, [uv](https://docs.astral.sh/uv/), y KDE Plasma 6 (usa `qdbus6` y `kscreen-doctor`, ambos parte de Plasma).

```bash
git clone <url-del-repo> wallrotate
cd wallrotate
uv sync
```

## Uso

Abrir la GUI de configuración:

```bash
uv run wallrotate
```

Elegí, por cada pestaña (una por monitor detectado): la fuente (imagen /
carpeta / collage), la ruta, el intervalo, el modo de ajuste, y si es
collage, sus parámetros. "Vista previa" genera un preview sin aplicarlo;
"Aplicar ahora" lo aplica al toque; "Guardar configuración" persiste los
cambios para que el motor de rotación automática los use.

### Activar la rotación automática

```bash
systemctl --user daemon-reload
systemctl --user enable --now wallrotate.timer
```

El timer corre cada 1 minuto y decide, por cada pantalla, si ya se cumplió
su intervalo configurado. Ver logs:

```bash
journalctl --user -u wallrotate.service -f
```

## Arquitectura

```
src/wallrotate/
├── collage.py         # Generador de collage (Pillow): marco, sombra, rotación, fondo
├── plasma_bridge.py   # Detección de monitores y aplicación de wallpaper vía D-Bus/Plasma
├── config.py           # Perfiles por pantalla (JSON) + estado de rotación
├── engine.py           # Motor: decide y aplica el siguiente fondo por pantalla
└── app.py              # GUI de configuración (PySide6)
```

El wallpaper se aplica usando la API de scripting de Plasma
(`org.kde.PlasmaShell.evaluateScript` vía `qdbus6`), escribiendo
directamente la configuración del plugin `org.kde.image` para el
`desktop` correspondiente a cada pantalla — es el mismo mecanismo que usa
Plasma internamente, sin dependencias extra ni hacks sobre archivos de
configuración.

## Stack

Python 3.13 · [PySide6](https://doc.qt.io/qtforpython/) (GUI) ·
[Pillow](https://python-pillow.org/) (composición de imágenes) ·
`qdbus6` / `kscreen-doctor` (integración con Plasma) ·
`systemd --user` (rotación automática)

## Estado del proyecto

Funcional, en uso diario propio. Sin tests automatizados todavía.
Desarrollado con asistencia de [Claude Code](https://claude.com/claude-code).

### Pendientes conocidos

- Resolución del timer de 1 minuto — intervalos menores no aplican.
- No maneja hot-plug de monitores mientras la GUI está abierta.
- El modo de ajuste "mosaico" no está probado a fondo.

## Licencia

[MIT](LICENSE) — usalo, copialo, modificalo, lo que quieras.
