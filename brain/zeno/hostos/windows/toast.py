"""Windows toast notifications through WinRT (the winrt-* packages, Windows only).

A toast needs an AppUserModelID that Windows knows. ``daemons/windows_setup.ps1``
registers ``Zeno.Brain`` under HKCU (``REGISTRATION``); until it does,
the toast is shown under PowerShell's own ID, so it still appears (labelled Windows
PowerShell).
"""

import asyncio
import logging
import sys
from collections.abc import Callable
from typing import Any
from xml.sax.saxutils import escape

from zeno.hostos.desktop import DesktopUnavailable

log = logging.getLogger(__name__)

APP_ID = "Zeno.Brain"
POWERSHELL_APP_ID = (
    "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe"
)
_ENABLED = 0  # NotificationSetting.ENABLED


REGISTRATION = "Software\\Classes\\AppUserModelId\\" + APP_ID


def app_id_registered() -> bool:
    """Whether windows_setup.ps1 registered Zeno's toast identity for this user."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRATION))
    except OSError:
        return False
    return True


def toast_xml(title: str, body: str, urgency: str) -> str:
    scenario = ' scenario="urgent"' if urgency == "critical" else ""
    audio = '<audio silent="true"/>' if urgency == "low" else ""
    texts = f"<text>{escape(title)}</text>" + (f"<text>{escape(body)}</text>" if body else "")
    return (
        f'<toast{scenario}><visual><binding template="ToastGeneric">{texts}'
        f"</binding></visual>{audio}</toast>"
    )


def _load_winrt() -> tuple[Any, Any]:
    from winrt.windows.data.xml import dom  # installed on Windows only
    from winrt.windows.ui import notifications

    return dom, notifications


class WindowsToaster:
    def __init__(
        self,
        app_id: str = APP_ID,
        *,
        registered: Callable[[], bool] = app_id_registered,
        winrt: Callable[[], tuple[Any, Any]] = _load_winrt,
    ) -> None:
        self._app_id = app_id
        self._registered = registered
        self._winrt = winrt
        self._warned = False

    async def notify(self, title: str, body: str, urgency: str) -> int:
        await asyncio.to_thread(self._show, toast_xml(title, body, urgency))
        return 0

    def _show(self, xml: str) -> None:
        try:
            dom, notifications = self._winrt()
        except ImportError as error:
            raise DesktopUnavailable("Windows notifications need the winrt packages") from error
        app_id = self._app_id
        if not self._registered():
            if not self._warned:
                log.info("Zeno's toast identity is not registered; run daemons/windows_setup.ps1")
                self._warned = True
            app_id = POWERSHELL_APP_ID
        try:
            document = dom.XmlDocument()
            document.load_xml(xml)
            notifier = notifications.ToastNotificationManager.create_toast_notifier_with_id(app_id)
            if int(notifier.setting) != _ENABLED:
                raise DesktopUnavailable(
                    "notifications for Zeno are turned off in Windows settings"
                )
            notifier.show(notifications.ToastNotification(document))
        except OSError as error:  # WinRT errors arrive as OSError with an HRESULT
            raise DesktopUnavailable(f"Windows refused the notification ({error})") from error
