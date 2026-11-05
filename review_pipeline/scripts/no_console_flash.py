"""No black console boxes from background Python. `import no_console_flash` at the top of a pythonw entry point.

Studio, the {{PROJECTS_ROOT}} watcher, the sync tasks and the rule gate run under pythonw, which has no console. When a
no-console process starts a console program (ffmpeg, ffprobe, git, powershell, cmd, bash, ssh) without
CREATE_NO_WINDOW, Windows gives the child its own VISIBLE console for a split second: the black boxes the owner kept
seeing (2026-10-27, 2026-10-30). ~220 subprocess calls lacked the flag, so instead of patching each one this patches
subprocess.Popen once, and only while this process has no visible console of its own:
- every child gets CREATE_NO_WINDOW (GUI children such as explorer or Premiere ignore it);
- a pythonw child is started as python.exe in that hidden console, so the scripts IT starts (ffmpeg, powershell...)
  inherit the hidden console too, even though they never import this module (same fix as rule_gate.run, e139ee3);
- an explicit CREATE_NEW_CONSOLE (a deliberate "open a terminal") is left alone; python.exe in a terminal is untouched.
os.system goes through subprocess so it is covered too. NO_CONSOLE_FLASH=0 turns it off.

Canonical copy: {{KIT}}/tools\\no_console_flash\\no_console_flash.py. Copies live next to the entry points in
{{STUDIO_NAME}}\\app, hermes product-review-edit\\scripts and Documents\\TickTick Bot; install.py can also put it into
Python312 as sitecustomize.py so EVERY script is covered.
"""
import os

if os.name == "nt" and os.environ.get("NO_CONSOLE_FLASH", "1") != "0" and not getattr(os, "_no_console_flash", 0):
    try:
        import ctypes
        import subprocess

        _GetConsoleWindow = ctypes.windll.kernel32.GetConsoleWindow
        _NO_WINDOW = 0x08000000
        _NEW_CONSOLE = 0x00000010
        _DETACHED = 0x00000008
        _popen_init = subprocess.Popen.__init__

        def _console_python(exe):
            """pythonw.exe path -> python.exe next to it (None if not pythonw)."""
            if not isinstance(exe, (str, os.PathLike)):
                return None
            exe = os.fspath(exe)
            base = os.path.basename(exe.strip('"')).lower()
            if base not in ("pythonw.exe", "pythonw"):
                return None
            con = os.path.join(os.path.dirname(exe.strip('"')), "python.exe")
            return con if os.path.dirname(exe.strip('"')) == "" or os.path.exists(con) else None

        def _hidden_init(self, args, *pos, **kw):
            # creationflags is the 13th parameter after args; a caller passing it positionally keeps its own value
            if len(pos) < 13 and not _GetConsoleWindow():
                flags = kw.get("creationflags") or 0
                if not flags & _NEW_CONSOLE:
                    py = None
                    if kw.get("executable") is not None:
                        py = _console_python(kw["executable"])
                        if py:
                            kw["executable"] = py
                    elif isinstance(args, (list, tuple)) and args:
                        py = _console_python(args[0])
                        if py:
                            args = [py, *args[1:]]
                    if py:  # a python child needs a (hidden) console to hand down, not none at all
                        flags &= ~_DETACHED
                    if not flags & _DETACHED:
                        kw["creationflags"] = flags | _NO_WINDOW
            _popen_init(self, args, *pos, **kw)

        subprocess.Popen.__init__ = _hidden_init

        _os_system = os.system

        def _hidden_system(command):
            if _GetConsoleWindow():
                return _os_system(command)
            return subprocess.call(command, shell=True)

        os.system = _hidden_system
        os._no_console_flash = 1  # imported twice (module + sitecustomize): patch once
    except Exception:  # never stop a tool from starting over a cosmetic fix
        pass
