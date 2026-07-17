# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [Sin publicar] - 2026-07-13

### Agregado

- Autoarranque como opción real de la app: casillero "Iniciar
  automáticamente con el sistema" en la ventana principal (crea/borra
  `~/.config/autostart/wallrotate.desktop`). Antes había que armar ese
  archivo a mano. En el primer arranque (sin `config.json` previo) la
  app pregunta directamente si se quiere activar.
- Distribución de fotos configurable en el collage (antes solo existía
  la dispersión libre tipo pila): bandas (superior/inferior con % de
  alto independiente), líneas horizontales o verticales (1 a 3),
  diagonal en ambos sentidos, en X, y óvalo (sobre el borde o
  rellenando el interior). Nuevo selector "Distribución de fotos" y
  controles asociados en los parámetros del collage de la GUI.
- Botón "?" junto a "Guardar configuración" con un diálogo "Acerca de
  WallRotate" (versión, crédito a John's Background Switcher, licencia
  MIT, link al repo) y una sección de Ayuda con el uso básico de la
  app (pestañas por monitor, menú de bandeja, timer en segundo plano).
- "Pausar todo" en el menú de bandeja, junto a "Rotar ahora (todas)":
  pausa o reanuda la rotación de todas las pantallas de una vez, en
  vez de tener que entrar pantalla por pantalla. Si el estado está
  mezclado (alguna pausada y otra no), pausa todas; si ya están todas
  pausadas, las reanuda. Se mantiene sincronizado con los checkboxes
  "Pausar rotación" de cada pantalla.
- Casillero "Pausar rotación automática si hay una app en pantalla
  completa (juegos, películas)" en la ventana principal. Detecta la
  ventana activa a pantalla completa consultando a KWin (vía un script
  cargado dinámicamente por D-Bus, `src/wallrotate/fullscreen.py`),
  funciona tanto en X11 como en Wayland. Solo afecta al chequeo
  periódico automático del timer — "Rotar ahora" y el resto del menú
  de bandeja siguen funcionando igual mientras hay algo en pantalla
  completa.
- Notificación de escritorio con miniatura del collage/imagen recién
  aplicada, en cada rotación (automática o manual — "Rotar ahora",
  "Siguiente/Anterior fondo"). Un solo punto de disparo (`_apply_path`
  en `engine.py`, vía `notify-send`) cubre ambos casos, incluida la
  rotación automática del timer que corre sin GUI. El daemon de
  notificaciones de Plasma ignora tanto el hint `image-path` como los
  atributos `width`/`height` del tag `<img>` en el cuerpo del mensaje
  (siempre renderiza a tamaño original) — la solución fue generar una
  miniatura real de 200×200 con Pillow y embeberla en el cuerpo vía
  `<img src="file://...">`, ya que el único control real del tamaño es
  pre-escalar el archivo antes de mandarlo.

### Corregido

- El diálogo "Acerca de" recortaba y superponía su propio texto (el
  `QLabel` con rich text calculaba mal el alto disponible). Se
  reemplazó por un `QTextBrowser` con scroll interno. De paso, el
  botón "?" pasó a tener borde de color y negrita para leerse mejor
  como botón.
- El autoarranque no levantaba la GUI (ícono de bandeja ausente tras
  reiniciar la sesión, sin ningún error visible salvo en el log del
  sistema): `~/.config/autostart/wallrotate.desktop` usaba
  `Exec=wallrotate`, y `systemd-xdg-autostart-generator` evalúa ese
  archivo antes de que el manager de systemd de usuario importe el
  `PATH` de la sesión gráfica (que es donde vive `~/.local/bin`). El
  archivo ahora se genera con la ruta absoluta al binario del venv
  (`Exec=/ruta/al/proyecto/.venv/bin/wallrotate`), sin depender del
  `PATH` en ese momento del arranque.
- El autoarranque abría la ventana principal y quedaba como una app
  más en la barra de tareas en cada inicio de sesión, en vez de
  arrancar solo con el ícono de bandeja (comportamiento esperado). Se
  agregó el flag `--minimized` (usado en el `Exec=` del autoarranque)
  que evita el `window.show()` inicial.

## [0.1.0] - 2026-07-12

Primera versión funcional.

### Agregado

- Rotador de fondos de pantalla por monitor para KDE Plasma, con tres
  modos de fuente: imagen fija, carpeta en slideshow, y collage.
- Generador de collage estilo "pila de polaroids" (Pillow): marco,
  sombra difusa, rotación aleatoria, fondo difuminado.
- Bridge a Plasma vía D-Bus (`qdbus6` / `org.kde.PlasmaShell.evaluateScript`)
  para aplicar el fondo en una pantalla específica.
- Motor de rotación con `systemd --user timer`, corre en segundo plano
  sin depender de que la GUI esté abierta.
- GUI de configuración (PySide6): una pestaña por monitor detectado,
  con vista previa y aplicación inmediata.
- Icono propio en la ventana y en la bandeja del sistema (SVG,
  pantalla con flecha de rotación). Cerrar o minimizar oculta la
  ventana en vez de salir.
- Entrada `.desktop` para lanzar como aplicación normal desde el menú.
- Menú de bandeja completo por pantalla, inspirado en John's Background
  Switcher: Siguiente fondo / Fondo anterior (con historial persistente),
  Pausar rotación, Ver imagen actual, Guardar imagen actual como...,
  Navegador de imágenes en caché.
- Modo de ajuste de foto dentro del marco: "completa" (fondo blanco,
  sin recortar) o "recortar y llenar".
- Separación mínima configurable entre fotos, para evitar que se tapen
  por completo en el modo collage.
- Licencia MIT.

### Corregido

- El collage sobrescribía siempre el mismo nombre de archivo; Plasma
  cacheaba la imagen por ruta y no detectaba el cambio de contenido.
  Ahora cada generación usa un nombre único.
- Las fotos de filas inferiores se salían del borde del canvas cuando
  había varias filas.
- El tamaño de marco variaba según el aspect ratio de cada foto,
  dejando fotos verticales (ej. contenido tipo Instagram) muy chicas
  con mucho espacio vacío alrededor — se unificó a un marco de tamaño
  fijo, como un Polaroid real.
- El selector de tamaño de foto no tenía efecto real porque el ajuste
  automático por fila lo pisaba.
- El ícono de la bandeja se registraba pero con los píxeles vacíos
  (bug de Qt al exportar un `QIcon` basado en SVG por D-Bus en tamaños
  chicos) — se renderizan los tamaños típicos por adelantado.

### Documentación

- README con instalación, uso, arquitectura, capturas de ejemplo.
- Historia del proyecto y créditos a John's Background Switcher.

[0.1.0]: https://github.com/Cap-dutch/wallrotate/releases/tag/v0.1.0
