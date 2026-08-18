"""Start-at-Login via SMAppService (macOS 13+).

This registers the app itself under System Settings → Login Items — the
sanctioned mechanism for the .app bundle. It is NOT a launchd daemon (see
AGENTS.md: daemons are banned; login items are fine). Only meaningful when
running from inside the bundle; callers gate on `bundle.is_bundled()`.
"""

from __future__ import annotations

from ServiceManagement import SMAppService, SMAppServiceStatusEnabled


def is_enabled() -> bool:
    try:
        return SMAppService.mainAppService().status() == SMAppServiceStatusEnabled
    except Exception as e:  # noqa: BLE001
        print(f"[login-item] status check failed: {e}", flush=True)
        return False


def set_enabled(enabled: bool) -> str | None:
    """Toggle Open at Login. Returns an error message, or None on success."""
    svc = SMAppService.mainAppService()
    try:
        # pyobjc maps the NSError** out-param to a (BOOL, NSError) tuple.
        if enabled:
            ok, err = svc.registerAndReturnError_(None)
        else:
            ok, err = svc.unregisterAndReturnError_(None)
    except Exception as e:  # noqa: BLE001
        return str(e)
    return None if ok else str(err)
