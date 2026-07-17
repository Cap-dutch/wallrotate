function isEffectivelyFullscreen(w) {
    if (!w || w.minimized) return false;
    if (w.fullScreen) return true;
    // Algunos reproductores (streaming con DRM, ej. HBO Max) no piden
    // pantalla completa real al compositor -- solo maximizan la ventana y
    // ocultan su propia interfaz. maximizeMode 3 = MaximizeFull; si la
    // ventana maximizada cubre exactamente la pantalla donde esta, lo
    // tratamos igual que pantalla completa real.
    if (w.maximizeMode === 3 && w.output) {
        var g = w.frameGeometry;
        var og = w.output.geometry;
        if (g.width === og.width && g.height === og.height) return true;
    }
    return false;
}

// Se revisan todas las ventanas de todas las pantallas, no solo la activa:
// con varios monitores (ej. un "smart TV" secundario) el foco puede estar
// en otro lado mientras algo corre a pantalla completa en otra pantalla.
var list = workspace.windowList();
var found = false;
for (var i = 0; i < list.length; i++) {
    if (isEffectivelyFullscreen(list[i])) {
        found = true;
        break;
    }
}
callDBus("com.wallrotate.FullscreenCheck", "/FullscreenCheck", "", "Report", found);
