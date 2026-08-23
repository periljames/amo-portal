from __future__ import annotations

"""Keep attendance review warnings stable for UI rendering and audit review."""

_INSTALLED = False


def install(service_module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_attendance_summary = service_module.attendance_summary

    def attendance_summary(*args, **kwargs):
        summary = original_attendance_summary(*args, **kwargs)
        # Totals warnings and event review reasons can legitimately describe the
        # same condition. The UI should receive one warning per distinct reason,
        # while the underlying events/review count remain complete and auditable.
        summary.warnings = list(dict.fromkeys(str(value) for value in summary.warnings if str(value).strip()))
        return summary

    service_module.attendance_summary = attendance_summary
    _INSTALLED = True


__all__ = ["install"]
