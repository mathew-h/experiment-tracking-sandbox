"""
Hook: notify_stop.py
Event: Stop

Sends a Windows toast notification whenever Claude Code finishes a response turn.
Uses PowerShell with Windows Runtime (WinRT) APIs — no third-party packages required.
Fails gracefully if the notification APIs are unavailable (e.g. Windows Server without
Desktop Experience, or non-Windows platforms).

Claude Code passes a JSON payload via stdin. We drain it and discard it.
"""

import json
import subprocess
import sys


def main() -> None:
    # Drain stdin — Claude Code sends a JSON payload we don't need
    try:
        payload = json.loads(sys.stdin.read())
        # stop_hook_active=True means a Stop hook is already running; skip to avoid
        # infinite notification loops (shouldn't happen but belt-and-suspenders).
        if payload.get("stop_hook_active"):
            sys.exit(0)
    except Exception:
        pass

    # Inline PowerShell command: WinRT toast notification, no .ps1 file path needed.
    # Works on Windows 10 / 11 out of the box.
    ps_command = r"""
try {
    $null = [Windows.UI.Notifications.ToastNotificationManager,
             Windows.UI.Notifications,
             ContentType = WindowsRuntime]

    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
        [Windows.UI.Notifications.ToastTemplateType]::ToastText02
    )
    $xml = [xml] $template.GetXml()
    $nodes = $xml.GetElementsByTagName('text')
    $nodes[0].InnerText = 'Claude Code'
    $nodes[1].InnerText = 'Claude has stopped and is waiting for you.'

    $xmlDoc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xmlDoc.LoadXml($xml.OuterXml)

    $toast = [Windows.UI.Notifications.ToastNotification]::new($xmlDoc)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Claude Code').Show($toast)
} catch {
    # Notification unavailable — exit silently without blocking Claude Code
    exit 0
}
"""

    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NonInteractive",
                "-NoProfile",
                "-WindowStyle", "Hidden",
                "-Command", ps_command,
            ],
            timeout=10,
            capture_output=True,
        )
    except Exception:
        # powershell.exe not found or timed out — fail silently
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
