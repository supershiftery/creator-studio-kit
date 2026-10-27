"""Notifications: a Windows toast."""
import subprocess
import sys
import threading

import store

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
TOAST_PS = r'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($args[0])
$t = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('CreatorKit.Studio').Show($t)
'''


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def toast(title, body):
    xml = f'<toast><visual><binding template="ToastGeneric"><text>{_esc(title)}</text><text>{_esc(body)}</text></binding></visual></toast>'
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", TOAST_PS, xml], creationflags=CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def notify(title, body, tg=True):
    """Windows toast (tg is ignored; kept so old callers still work)."""
    s = store.settings()
    if s.get("notify_toast", True):
        toast(title, body)
