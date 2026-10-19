"""Lightweight UI-only receiver; never imports an old exchange on startup."""
import builtins,time
def defer_start():
    import hou
    if not hou.isUIAvailable():return
    hou.unsetenv('KARMA_XPU_DISABLE_OPTIX_DEVICE')
    old=getattr(builtins,'_b2h_deferred_start',None)
    if old:
        try:hou.ui.removeEventLoopCallback(old)
        except Exception:pass
    ready=time.monotonic()+2
    def callback():
        if hou.hipFile.isLoadingHipFile() or time.monotonic()<ready:return
        hou.ui.removeEventLoopCallback(callback)
        builtins._b2h_deferred_start=None
        import auto_import_bridge
        auto_import_bridge.start()
    builtins._b2h_deferred_start=callback
    hou.ui.addEventLoopCallback(callback)
