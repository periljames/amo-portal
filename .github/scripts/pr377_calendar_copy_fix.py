from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}: {old[:100]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


root = Path(__file__).resolve().parents[2]

calendar_feed = root / "backend/amodb/apps/rostering/calendar_feed.py"
replace_once(
    calendar_feed,
    "from ..accounts import models as account_models\nfrom . import commitments, models\n",
    "from ..accounts import models as account_models\nfrom ..work import models as work_models\nfrom . import commitments, models\n",
)
replace_once(
    calendar_feed,
    """def _published_assignments(
    db: Session,
""",
    """def _published_assignment_loader_options():
    \"\"\"Build SQLAlchemy 2-compatible eager-loader paths for calendar events.\"\"\"
    return (
        selectinload(models.RosterAssignment.shift_template),
        selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterAssignment.task_links)
        .selectinload(models.RosterTaskAssignmentLink.task_assignment)
        .selectinload(work_models.TaskAssignment.task)
        .selectinload(work_models.TaskCard.work_order)
        .selectinload(work_models.WorkOrder.aircraft),
    )


def _published_assignments(
    db: Session,
""",
)
replace_once(
    calendar_feed,
    """    ).options(
        selectinload(models.RosterAssignment.shift_template),
        selectinload(models.RosterAssignment.base_station),
        selectinload(models.RosterAssignment.task_links)
        .selectinload(models.RosterTaskAssignmentLink.task_assignment)
        .selectinload("task")
        .selectinload("work_order")
        .selectinload("aircraft"),
    ).filter(
""",
    """    ).options(*_published_assignment_loader_options()).filter(
""",
)

backend_test = root / "backend/amodb/apps/rostering/tests/test_calendar_feed.py"
backend_test.write_text(
    '''from __future__ import annotations

import inspect

import pytest

from amodb.apps.rostering import calendar_feed


def test_calendar_loader_paths_are_sqlalchemy_2_compatible() -> None:
    options = calendar_feed._published_assignment_loader_options()
    assert len(options) == 3

    source = inspect.getsource(calendar_feed._published_assignment_loader_options)
    assert '.selectinload("task")' not in source
    assert '.selectinload("work_order")' not in source
    assert '.selectinload("aircraft")' not in source
    assert "work_models.TaskAssignment.task" in source
    assert "work_models.TaskCard.work_order" in source
    assert "work_models.WorkOrder.aircraft" in source


def test_calendar_subscription_token_round_trip_and_tamper_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "calendar-feed-regression-secret")
    token = calendar_feed.calendar_token(amo_id="AMO-TEST", user_id="USER-TEST")

    assert calendar_feed.decode_calendar_token(token) == ("AMO-TEST", "USER-TEST")

    with pytest.raises(ValueError, match="Invalid calendar subscription token"):
        calendar_feed.decode_calendar_token(f"{token[:-1]}x")
''',
    encoding="utf-8",
)

my_roster = root / "frontend/src/pages/rostering/components/MyRosterWorkspace.tsx"
replace_once(
    my_roster,
    'import { useMemo, useState } from "react";\n',
    'import { useEffect, useMemo, useRef, useState } from "react";\n',
)
replace_once(
    my_roster,
    'type AttendanceAction = "CLOCK_IN" | "CLOCK_OUT" | "BREAK_START" | "BREAK_END";\n',
    'type AttendanceAction = "CLOCK_IN" | "CLOCK_OUT" | "BREAK_START" | "BREAK_END";\ntype CalendarCopyState = "idle" | "copied" | "error";\n',
)
replace_once(
    my_roster,
    """  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarSetupStarted, setCalendarSetupStarted] = useState(false);
  const calendarStorageKey = calendarLinkStorageKey(userId);
""",
    """  const [calendarOpen, setCalendarOpen] = useState(false);
  const [calendarSetupStarted, setCalendarSetupStarted] = useState(false);
  const [calendarCopyState, setCalendarCopyState] = useState<CalendarCopyState>("idle");
  const calendarCopyResetRef = useRef<number | null>(null);
  const calendarStorageKey = calendarLinkStorageKey(userId);
""",
)
replace_once(
    my_roster,
    """  const [linkedFeedPath, setLinkedFeedPath] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(calendarStorageKey) || "";
  });
  const leaveYear = new Date().getFullYear();
""",
    """  const [linkedFeedPath, setLinkedFeedPath] = useState(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(calendarStorageKey) || "";
  });
  useEffect(() => () => {
    if (calendarCopyResetRef.current !== null) {
      window.clearTimeout(calendarCopyResetRef.current);
    }
  }, []);
  const leaveYear = new Date().getFullYear();
""",
)
replace_once(
    my_roster,
    """  const copyCalendarFeed = async () => {
    if (!calendarUrls) return;
    try {
      await navigator.clipboard.writeText(calendarUrls.httpsUrl);
    } catch {
      setActionError("The browser could not copy the calendar address. Open the subscription link and copy it manually.");
    }
  };
""",
    """  const scheduleCalendarCopyReset = (delayMs: number) => {
    if (typeof window === "undefined") return;
    if (calendarCopyResetRef.current !== null) {
      window.clearTimeout(calendarCopyResetRef.current);
    }
    calendarCopyResetRef.current = window.setTimeout(() => {
      setCalendarCopyState("idle");
      calendarCopyResetRef.current = null;
    }, delayMs);
  };

  const copyCalendarFeed = async () => {
    if (!calendarUrls) return;
    setActionError(null);
    setCalendarCopyState("idle");
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(calendarUrls.httpsUrl);
      setCalendarCopyState("copied");
      scheduleCalendarCopyReset(2400);
    } catch {
      setCalendarCopyState("error");
      scheduleCalendarCopyReset(3200);
      setActionError("The browser could not copy the calendar address. Open the subscription link and copy it manually.");
    }
  };
""",
)
replace_once(
    my_roster,
    """                  <button
                    type="button"
                    className="wr-button wr-button--secondary"
                    onClick={() => void copyCalendarFeed()}
                  >
                    <Copy size={14} /> Copy URL
                  </button>
""",
    """                  <button
                    type="button"
                    className={`wr-button wr-button--secondary wr-calendar-copy ${calendarCopyState === "copied" ? "is-copied" : calendarCopyState === "error" ? "is-error" : ""}`}
                    onClick={() => void copyCalendarFeed()}
                    aria-label={calendarCopyState === "copied" ? "Calendar URL copied" : "Copy calendar URL"}
                  >
                    {calendarCopyState === "copied"
                      ? <CheckCircle2 size={15} className="wr-calendar-copy__check" />
                      : <Copy size={14} />}
                    <span>{calendarCopyState === "copied" ? "Copied" : calendarCopyState === "error" ? "Try again" : "Copy URL"}</span>
                  </button>
""",
)
replace_once(
    my_roster,
    """                  ) : null}
                </div>
              ) : (
""",
    """                  ) : null}
                </div>
                {calendarCopyState !== "idle" ? (
                  <div
                    className={`wr-calendar-copy-feedback is-${calendarCopyState}`}
                    role="status"
                    aria-live="polite"
                    aria-atomic="true"
                  >
                    {calendarCopyState === "copied"
                      ? <><CheckCircle2 size={15} /> Calendar address copied successfully</>
                      : <>Copy failed. Use the subscription link or try again.</>}
                  </div>
                ) : null}
              ) : (
""",
)

my_roster_css = root / "frontend/src/pages/rostering/components/my-roster-workspace.css"
replace_once(
    my_roster_css,
    """.wr-calendar-popover__actions .wr-button {
  width: auto;
}

.wr-calendar-popover__notice {
""",
    """.wr-calendar-popover__actions .wr-button {
  width: auto;
}

.wr-calendar-copy {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  transition:
    color 160ms ease,
    border-color 160ms ease,
    background 160ms ease,
    box-shadow 160ms ease,
    transform 160ms ease;
}

.wr-calendar-copy::after {
  content: "";
  position: absolute;
  z-index: -1;
  inset: 50% auto auto 50%;
  width: 12px;
  aspect-ratio: 1;
  border-radius: 999px;
  background: color-mix(in srgb, #22c55e 26%, transparent);
  opacity: 0;
  transform: translate(-50%, -50%) scale(0);
}

.wr-calendar-copy.is-copied {
  border-color: color-mix(in srgb, #16a34a 70%, var(--border));
  background: color-mix(in srgb, var(--surface) 84%, #22c55e 16%);
  color: color-mix(in srgb, var(--text) 78%, #14532d 22%);
  box-shadow: 0 0 0 3px color-mix(in srgb, #22c55e 16%, transparent);
  animation: wr-calendar-copy-confirm 420ms cubic-bezier(.2, .85, .25, 1.25);
}

.wr-calendar-copy.is-copied::after {
  animation: wr-calendar-copy-ripple 560ms ease-out;
}

.wr-calendar-copy.is-error {
  border-color: color-mix(in srgb, #dc2626 60%, var(--border));
  background: color-mix(in srgb, var(--surface) 90%, #dc2626 10%);
}

.wr-calendar-copy__check {
  animation: wr-calendar-copy-check 360ms cubic-bezier(.18, .9, .3, 1.35);
}

.wr-calendar-copy-feedback {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  min-height: 28px;
  padding: 5px 9px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: .78rem;
  font-weight: 700;
  line-height: 1.2;
  animation: wr-calendar-copy-feedback-in 260ms ease-out;
}

.wr-calendar-copy-feedback.is-copied {
  border-color: color-mix(in srgb, #16a34a 56%, var(--border));
  background: color-mix(in srgb, var(--surface) 88%, #22c55e 12%);
  color: color-mix(in srgb, var(--text) 76%, #14532d 24%);
}

.wr-calendar-copy-feedback.is-error {
  border-color: color-mix(in srgb, #dc2626 52%, var(--border));
  background: color-mix(in srgb, var(--surface) 92%, #dc2626 8%);
  color: color-mix(in srgb, var(--text) 78%, #7f1d1d 22%);
}

@keyframes wr-calendar-copy-confirm {
  0% { transform: scale(.96); }
  55% { transform: scale(1.045); }
  100% { transform: scale(1); }
}

@keyframes wr-calendar-copy-check {
  0% { opacity: 0; transform: rotate(-18deg) scale(.35); }
  100% { opacity: 1; transform: rotate(0) scale(1); }
}

@keyframes wr-calendar-copy-ripple {
  0% { opacity: .85; transform: translate(-50%, -50%) scale(0); }
  100% { opacity: 0; transform: translate(-50%, -50%) scale(14); }
}

@keyframes wr-calendar-copy-feedback-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.wr-calendar-popover__notice {
""",
)
replace_once(
    my_roster_css,
    """@media (prefers-reduced-motion: reduce) {
  .wr-calendar-link.is-unlinked > i {
    animation: none;
  }
}
""",
    """@media (prefers-reduced-motion: reduce) {
  .wr-calendar-link.is-unlinked > i,
  .wr-calendar-copy,
  .wr-calendar-copy::after,
  .wr-calendar-copy__check,
  .wr-calendar-copy-feedback {
    animation: none;
    transition: none;
  }
}
""",
)

frontend_test = root / "frontend/src/pages/rostering/rosteringSetupOverhaul.test.ts"
replace_once(
    frontend_test,
    'const hrSource = readSource("./components/WorkforceHrWorkspace.tsx");\n',
    'const hrSource = readSource("./components/WorkforceHrWorkspace.tsx");\nconst myRosterSource = readSource("./components/MyRosterWorkspace.tsx");\nconst myRosterCss = readSource("./components/my-roster-workspace.css");\n',
)
replace_once(
    frontend_test,
    """  it("keeps active tenant users visible when Workforce records are incomplete", () => {
    expect(hrSource).toContain("Every active tenant user appears here");
    expect(hrSource).toContain("Create contract");
    expect(hrSource).toContain("createEmploymentContract");
    expect(hrSource).toContain("Apply default day pattern");
    const workforceHrService = readSource("../../services/workforceHr.ts");
    expect(workforceHrService).toContain("/workforce/hr/default-day-pattern");
    const workforceTypes = readSource("../../types/workforce.ts");
    expect(workforceTypes).toContain('"TEMPORARY"');
    expect(workforceTypes).not.toContain('"CASUAL"');
    expect(workforceTypes).not.toContain('"SECONDMENT"');
    expect(workforceTypes).not.toContain('"ENDED"');
  });
});
""",
    """  it("keeps active tenant users visible when Workforce records are incomplete", () => {
    expect(hrSource).toContain("Every active tenant user appears here");
    expect(hrSource).toContain("Create contract");
    expect(hrSource).toContain("createEmploymentContract");
    expect(hrSource).toContain("Apply default day pattern");
    const workforceHrService = readSource("../../services/workforceHr.ts");
    expect(workforceHrService).toContain("/workforce/hr/default-day-pattern");
    const workforceTypes = readSource("../../types/workforce.ts");
    expect(workforceTypes).toContain('"TEMPORARY"');
    expect(workforceTypes).not.toContain('"CASUAL"');
    expect(workforceTypes).not.toContain('"SECONDMENT"');
    expect(workforceTypes).not.toContain('"ENDED"');
  });

  it("confirms copied calendar links visually and accessibly", () => {
    expect(myRosterSource).toContain('type CalendarCopyState = "idle" | "copied" | "error"');
    expect(myRosterSource).toContain('setCalendarCopyState("copied")');
    expect(myRosterSource).toContain('aria-live="polite"');
    expect(myRosterSource).toContain("Calendar address copied successfully");
    expect(myRosterSource).toContain("wr-calendar-copy__check");
    expect(myRosterCss).toContain("wr-calendar-copy-confirm");
    expect(myRosterCss).toContain("wr-calendar-copy-ripple");
    expect(myRosterCss).toContain("prefers-reduced-motion");
  });
});
""",
)

for path in (calendar_feed, backend_test, my_roster, my_roster_css, frontend_test):
    text = path.read_text(encoding="utf-8")
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
