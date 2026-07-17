# WallRotate — rotador de fondos de pantalla con collage

App de escritorio para KDE Plasma (CachyOS): rota el fondo de pantalla por
monitor, con soporte de imagen fija, carpeta en slideshow, o collage
generado a partir de fotos (estilo "pila de polaroids", inspirado en
John's Background Switcher, que no tiene versión Linux).

## Arquitectura

| Pieza | Archivo | Rol |
|---|---|---|
| Generador de collage | `src/wallrotate/collage.py` | Compone N fotos con Pillow: marco polaroid, sombra, rotación aleatoria, fondo difuminado |
| Bridge a Plasma | `src/wallrotate/plasma_bridge.py` | Detecta monitores y aplica wallpaper por pantalla vía `qdbus6`/`org.kde.PlasmaShell.evaluateScript` (método `setWallpaper` nativo no soporta bien parámetros complejos desde CLI, se usa scripting JS de Plasma) |
| Config | `src/wallrotate/config.py` | Perfiles por pantalla en `~/.config/wallrotate/config.json`, estado de rotación en `state.json` |
| Motor | `src/wallrotate/engine.py` | Revisa perfiles, aplica el siguiente fondo si venció el intervalo. Se ejecuta vía systemd timer. Si `config.pause_on_fullscreen`, salta el chequeo (no afecta `force=True`) consultando `fullscreen.py`. `_apply_path` es el unico punto de aplicacion (automatica y manual via `go_next`/`go_previous`) y ahi mismo dispara la notificacion con miniatura via `notify-send`. El daemon de notificaciones de Plasma ignora el hint `image-path` y los atributos `width`/`height` del `<img>` en el cuerpo -- `_make_notification_thumbnail` pre-escala una miniatura real de 200x200 con Pillow y esa es la que se embebe |
| Deteccion pantalla completa | `src/wallrotate/fullscreen.py` | Carga un script de KWin (`resources/check_fullscreen.js`) por D-Bus que llama de vuelta via `callDBus` a un servicio D-Bus temporal (`QDBusConnection` + `ExportAllSlots`, interfaz vacia en el `callDBus` del lado JS). Funciona en X11 y Wayland porque no inspecciona ventanas desde afuera, le pregunta al compositor. Falla "cerrado" (False) ante cualquier error. El script revisa `workspace.windowList()` completo (no solo la ventana activa, para multi-monitor) y trata `maximizeMode === 3` con geometria igual a la de su pantalla como pantalla completa tambien (streaming con DRM, ej. HBO Max, no pide fullscreen real al compositor) |
| GUI | `src/wallrotate/app.py` | PySide6, una pestaña por monitor detectado. Tiene icono en bandeja (QSystemTrayIcon): cerrar/minimizar oculta la ventana en vez de salir (`app.setQuitOnLastWindowClosed(False)` + `closeEvent`/`changeEvent` overrides), solo "Salir" del menu del tray cierra de verdad. Boton "?" junto a "Guardar configuracion" abre `AboutDialog` (usa `QTextBrowser`, no `QLabel`, para que el rich text largo no se recorte/superponga) |
| Desktop entry | `packaging/wallrotate.desktop` | Necesario para que `QApplication.setDesktopFileName` no tire warning del portal y para que el icono/titulo del tray se vea bien (si no, Qt usa el nombre del script como Id/Title) |

## Cómo correr

```bash
cd ~/Proyectos/wallrotate
uv run wallrotate          # abre la GUI de configuración
uv run wallrotate-engine   # corre el motor una vez (lo hace el timer automáticamente)
```

## Automatización

`~/.config/systemd/user/wallrotate.{service,timer}` — el timer corre el
motor cada 1 minuto; el motor decide internamente si a cada pantalla le
toca rotar según su `interval_minutes`. Ver estado:

```bash
systemctl --user status wallrotate.timer
journalctl --user -u wallrotate.service -f
```

## Cuidado con el contenido de las fuentes

Las carpetas de fotos personales del usuario pueden tener contenido no
apto para todo público. **Al generar o previsualizar collages en sesiones
de Claude, confirmar primero con el usuario qué carpeta es segura usar**
— el modelo no puede procesar ese tipo de contenido. Para pruebas usar
`/usr/share/wallpapers/cachyos-wallpapers/` (siempre seguro) u otra
carpeta que el usuario confirme explícitamente.

## Pendientes / mejoras futuras

- La resolución del timer es de 1 min — intervalos menores a eso no aplican.
- No maneja hot-plug de monitores mientras la GUI está abierta (hay que
  reabrirla si se conecta/desconecta un monitor).
- Sin tests automatizados todavía.
- El fill mode "mosaico" usa el valor Qt `Tile` pero no se probó a fondo.
