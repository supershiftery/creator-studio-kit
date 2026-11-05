"""{{STUDIO_NAME}} launcher.
python main.py            native window (Edge WebView2 through pywebview)
python main.py --browser  no window: opens the default browser instead
python main.py --serve    API only (for curl / tests)
Closing the window while builds run asks first; "keep building" hides the window (the process stays alive and quits itself
once the builds are done). Starting the app again while it runs brings that window back instead of opening a second one."""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import no_console_flash  # noqa: E402,F401  # hides every console window the jobs below start (pythonw: no console of its own)
import server  # noqa: E402
import store  # noqa: E402


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


SHOW_FLAG = store.DATA / "show-window-8765.flag"   # a second launch drops this; the running window sees it and comes back (per port)


def ask_running_window():
    """another studio already owns the port: ask its window to come forward. True when it did (then we just exit)."""
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)   # ASFW_ANY: we were just launched, so we may hand the focus on
    except Exception:
        pass
    try:
        SHOW_FLAG.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        return False
    for _ in range(30):
        time.sleep(0.1)
        if not SHOW_FLAG.exists():
            return True
    try:   # nobody picked it up (a --browser / --serve instance, or an older build): open a window of our own
        SHOW_FLAG.unlink()
    except OSError:
        pass
    return False


def active_jobs():
    import jobs
    return [j for j in list(jobs.JOBS.values()) if j.status in ("queued", "running")]


def main():
    args = sys.argv[1:]
    port = store.settings()["port"]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    url = f"http://127.0.0.1:{port}/"
    global SHOW_FLAG
    SHOW_FLAG = store.DATA / f"show-window-{port}.flag"
    if port_free(port):
        os.environ["STUDIO_MODE"] = "browser" if "--browser" in args or "--serve" in args else "window"
        server.serve(port, block=False)
        time.sleep(0.3)
    else:
        print("studio already running on", url)
        if "--serve" in args:   # nothing to add: exit instead of sleeping forever next to the running one
            return
        if not ("--browser" in args or "--serve" in args) and ask_running_window():
            return
    if "--serve" in args:
        print("serving", url, flush=True)
        while True:
            time.sleep(3600)
    if "--browser" in args:
        webbrowser.open(url)
        while True:
            time.sleep(3600)
    try:
        import webview
    except ImportError:
        webbrowser.open(url)
        while True:
            time.sleep(3600)

    class Api:
        """Called from the page as window.pywebview.api.<name>(...)"""

        def pick_files(self, kind="video", multiple=True):
            ft = {"video": ("Video (*.mp4;*.mov;*.mkv;*.m4v;*.avi)",), "audio": ("Audio (*.wav;*.mp3;*.m4a;*.flac)",),
                  "image": ("Image (*.png;*.jpg;*.jpeg;*.webp)",), "text": ("Text (*.txt;*.md;*.html)",),
                  "any": ("All files (*.*)",)}.get(kind, ("All files (*.*)",))
            res = window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=multiple, file_types=ft)
            return list(res or [])

        def pick_folder(self):
            res = window.create_file_dialog(webview.FileDialog.FOLDER)
            return list(res or [])

        def open_path(self, path):
            os.startfile(path)  # noqa
            return True

    ICON = str(store.HOME / "ui" / "studio.ico")
    try:   # our own taskbar identity, so Windows shows the studio icon instead of python's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CreatorKit.Studio")
    except Exception:
        pass

    def set_icon():
        """Put studio.ico on the window (title bar + taskbar) once the WebView2 window exists."""
        try:
            import ctypes
            u32 = ctypes.windll.user32
            hwnd = None
            try:   # our own form; a title search could find another studio window
                hwnd = int(window.native.Handle.ToInt64())
            except Exception:
                pass
            for _ in range(0 if hwnd else 40):
                hwnd = u32.FindWindowW(None, "{{STUDIO_NAME}}")
                if hwnd:
                    break
                time.sleep(0.25)
            state["hwnd"] = hwnd
            if not hwnd or not os.path.exists(ICON):
                return
            for size, which in ((16, 0), (32, 1), (256, 1)):   # ICON_SMALL, ICON_BIG
                h = u32.LoadImageW(None, ICON, 1, size, size, 0x00000010)   # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    u32.SendMessageW(hwnd, 0x0080, which, h)   # WM_SETICON
        except Exception:
            pass

    state = {"hwnd": None, "hidden": False, "quitting": False, "idle_since": None}

    def on_closing():
        """False keeps the window: a running build would die with this process, so ask first."""
        if state["quitting"]:
            return True
        busy = active_jobs()
        if not busy:
            return True
        import ctypes
        names = "\n".join(f"  • {j.title}" for j in busy[:6])
        n = len(busy)
        msg = (f"{n} build{'s' if n != 1 else ''} running:\n{names}\n\n"
               "Yes: keep building in the background. The window hides; open {{STUDIO_NAME}} again to bring it back. "
               "Studio closes itself once the builds finish, and you still get the toast.\n\n"
               "No: quit now and stop the builds.\n\nCancel: stay open.")
        r = ctypes.windll.user32.MessageBoxW(state["hwnd"] or 0, msg, "Keep building in the background?", 0x3 | 0x20)   # YESNOCANCEL, QUESTION
        if r == 6:   # Yes
            state["hidden"], state["idle_since"] = True, None
            threading.Thread(target=window.hide, daemon=True).start()
            import notify
            notify.toast("Still building in the background", "{{STUDIO_NAME}} is hidden, not closed. Open it again to see the progress.")
            return False
        if r == 7:   # No: stop the builds properly (kills each step's process tree, so no orphan ffmpeg is left behind)
            for j in busy:
                j.cancel()
            state["quitting"] = True
            return True
        return False

    def background_loop():
        """shows the window when a second launch asks for it; quits a hidden studio once its builds are done"""
        while True:
            time.sleep(0.5)
            if SHOW_FLAG.exists():
                try:
                    SHOW_FLAG.unlink()
                except OSError:
                    pass
                state["hidden"] = False
                try:
                    window.show()
                    window.restore()
                    import ctypes
                    if state["hwnd"]:
                        ctypes.windll.user32.SetForegroundWindow(state["hwnd"])
                except Exception:
                    pass
            if state["hidden"]:
                if active_jobs():
                    state["idle_since"] = None
                elif state["idle_since"] is None:
                    state["idle_since"] = time.time()
                elif time.time() - state["idle_since"] > 30:   # grace: a finished job may chain the next one
                    state["quitting"] = True
                    window.destroy()
                    return

    window = webview.create_window("{{STUDIO_NAME}}", url, width=1500, height=940, min_size=(1100, 700), js_api=Api(),
                                   background_color="#0e1014", text_select=True)
    window.events.shown += lambda: threading.Thread(target=set_icon, daemon=True).start()
    window.events.closing += on_closing
    try:   # a flag left by a launch that found nothing running
        SHOW_FLAG.unlink()
    except OSError:
        pass
    threading.Thread(target=background_loop, daemon=True).start()
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.start(gui="edgechromium", private_mode=False, storage_path=str(store.DATA / "webview"))


if __name__ == "__main__":
    main()
