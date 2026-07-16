var w = workspace.activeWindow;
var fs = w ? w.fullScreen : false;
callDBus("com.wallrotate.FullscreenCheck", "/FullscreenCheck", "", "Report", fs);
