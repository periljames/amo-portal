import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  ClockAlert,
  Crosshair,
  LocateFixed,
  MapPin,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { getCachedUser } from "../../../services/auth";
import {
  contributeBaseLocation,
  evaluateBaseLocation,
  listBaseStations,
} from "../../../services/foundations";
import { getMyRoster } from "../../../services/rostering";
import { getAttendanceSummary } from "../../../services/workforce";
import type { AttendanceEventRead } from "../../../types/workforce";
import type { LocationEvaluationRead } from "../../../types/foundations";
import { errorMessage } from "../rosterUi";
import "./duty-location-assistant.css";

type AttendanceMode = "CLOCKED_OUT" | "WORKING" | "ON_BREAK";
type LocationPosition = {
  latitude: number;
  longitude: number;
  accuracy: number;
  capturedAt: string;
};

const DUTY_STATUSES = new Set(["DUTY", "STANDBY", "TRAINING", "TRAVEL"]);

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function attendanceMode(events: AttendanceEventRead[]): AttendanceMode {
  const latest = [...events]
    .filter((event) => event.event_type !== "MANUAL_ADJUSTMENT")
    .sort((left, right) => Date.parse(right.occurred_at) - Date.parse(left.occurred_at))[0];
  if (!latest || latest.event_type === "CLOCK_OUT") return "CLOCKED_OUT";
  if (latest.event_type === "BREAK_START") return "ON_BREAK";
  return "WORKING";
}

function captureCurrentPosition(): Promise<LocationPosition> {
  if (!window.isSecureContext) {
    return Promise.reject(new Error("Location guidance requires HTTPS or a trusted local development origin."));
  }
  if (!navigator.geolocation) {
    return Promise.reject(new Error("This browser does not provide geolocation."));
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
        capturedAt: new Date(position.timestamp || Date.now()).toISOString(),
      }),
      (reason) => {
        const message = reason.code === reason.PERMISSION_DENIED
          ? "Location permission was denied. Attendance remains available without location guidance."
          : reason.code === reason.TIMEOUT
            ? "The device did not return a position within 15 seconds. Try again where satellite or network location is clearer."
            : "The device location could not be determined.";
        reject(new Error(message));
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    );
  });
}

export function DutyLocationAssistant() {
  const user = getCachedUser();
  const userId = String((user as { id?: string } | null)?.id || "");
  const now = new Date();
  const from = new Date(now);
  from.setDate(from.getDate() - 31);
  const to = new Date(now);
  to.setDate(to.getDate() + 2);

  const rosterQuery = useQuery({
    queryKey: ["rostering", "duty-location", "roster", isoDate(now), userId],
    queryFn: () => getMyRoster({ from: isoDate(now), to: isoDate(to) }),
    staleTime: 45_000,
  });
  const attendanceQuery = useQuery({
    queryKey: ["rostering", "duty-location", "attendance", userId, isoDate(from), isoDate(to)],
    queryFn: () => getAttendanceSummary({
      user_id: userId || null,
      from: isoDate(from),
      to: isoDate(to),
    }),
    staleTime: 15_000,
  });
  const basesQuery = useQuery({
    queryKey: ["foundations", "duty-location", "bases"],
    queryFn: () => listBaseStations({ include_inactive: false }),
    staleTime: 10 * 60_000,
  });

  const [capturing, setCapturing] = useState(false);
  const [contributing, setContributing] = useState(false);
  const [position, setPosition] = useState<LocationPosition | null>(null);
  const [evaluation, setEvaluation] = useState<LocationEvaluationRead | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [contributionMessage, setContributionMessage] = useState<string | null>(null);

  const assignments = rosterQuery.data?.assignments || [];
  const mode = useMemo(
    () => attendanceMode(attendanceQuery.data?.events || []),
    [attendanceQuery.data?.events],
  );
  const dutyContext = useMemo(() => {
    const timestamp = Date.now();
    const dutyAssignments = assignments
      .filter((assignment) => DUTY_STATUSES.has(String(assignment.status)))
      .filter((assignment) => Boolean(assignment.base_station_id))
      .sort((left, right) => Date.parse(left.starts_at) - Date.parse(right.starts_at));
    const active = dutyAssignments.find((assignment) => (
      Date.parse(assignment.starts_at) <= timestamp && Date.parse(assignment.ends_at) >= timestamp
    ));
    if (active) return { kind: "ACTIVE" as const, assignment: active };
    const recentlyEnded = [...dutyAssignments]
      .reverse()
      .find((assignment) => {
        const ended = Date.parse(assignment.ends_at);
        return ended < timestamp && timestamp - ended <= 4 * 60 * 60_000;
      });
    if (recentlyEnded) return { kind: "ENDED" as const, assignment: recentlyEnded };
    const next = dutyAssignments.find((assignment) => {
      const starts = Date.parse(assignment.starts_at);
      return starts > timestamp && starts - timestamp <= 4 * 60 * 60_000;
    });
    return next ? { kind: "UPCOMING" as const, assignment: next } : null;
  }, [assignments]);

  const base = useMemo(
    () => basesQuery.data?.find((item) => item.id === dutyContext?.assignment.base_station_id) || null,
    [basesQuery.data, dutyContext?.assignment.base_station_id],
  );

  const prompt = useMemo(() => {
    if (!dutyContext || !base) return null;
    if (dutyContext.kind === "ACTIVE" && mode === "CLOCKED_OUT" && base.checkin_prompt_enabled) {
      return {
        tone: "action" as const,
        title: "Duty is active and attendance has not started",
        detail: `Check your position once to confirm proximity to ${base.code} before using the Clock in control below.`,
      };
    }
    if (dutyContext.kind === "ENDED" && mode !== "CLOCKED_OUT" && base.checkout_reminder_enabled) {
      return {
        tone: "warning" as const,
        title: "Duty has ended and attendance is still open",
        detail: `Check your current distance from ${base.code}, then use the Clock out control below.`,
      };
    }
    if (dutyContext.kind === "UPCOMING" && mode === "CLOCKED_OUT" && base.checkin_prompt_enabled) {
      return {
        tone: "info" as const,
        title: "Upcoming duty location is ready",
        detail: `Your duty at ${base.code} begins soon. Location is checked only when you request guidance.`,
      };
    }
    return null;
  }, [base, dutyContext, mode]);

  if (rosterQuery.isPending || attendanceQuery.isPending || basesQuery.isPending) {
    return null;
  }
  if (!dutyContext || !base) return null;
  const hasApprovedLocation = base.latitude != null && base.longitude != null;
  const locationPolicyEnabled = base.checkin_prompt_enabled
    || base.checkout_reminder_enabled
    || base.suspicious_location_review_enabled;
  if (!prompt && !locationPolicyEnabled) return null;

  const checkLocation = async () => {
    setCapturing(true);
    setMessage(null);
    setContributionMessage(null);
    try {
      const captured = await captureCurrentPosition();
      const result = await evaluateBaseLocation({
        latitude: captured.latitude,
        longitude: captured.longitude,
        accuracy_m: captured.accuracy,
        base_station_id: base.id,
      });
      setPosition(captured);
      setEvaluation(result);
      if (result.location_confidence === "LOW") {
        setMessage("The browser-reported accuracy is too low for a strong location conclusion. Attendance remains an explicit user action.");
      } else if (result.inside_geofence) {
        setMessage(`You are within the approved ${base.code} geofence. Use the attendance control below when ready.`);
      } else {
        setMessage(`Your one-time position is approximately ${Math.round(result.distance_m || 0)} m from ${base.code}. This does not block attendance; review the assignment and use the attendance control deliberately.`);
      }
    } catch (reason) {
      setMessage(errorMessage(reason));
      setPosition(null);
      setEvaluation(null);
    } finally {
      setCapturing(false);
    }
  };

  const contributeVerification = async () => {
    setContributing(true);
    setContributionMessage(null);
    try {
      const ageMs = position ? Date.now() - Date.parse(position.capturedAt) : Number.POSITIVE_INFINITY;
      const captured = position && ageMs <= 5 * 60_000 ? position : await captureCurrentPosition();
      const consensus = await contributeBaseLocation(base.id, {
        latitude: captured.latitude,
        longitude: captured.longitude,
        accuracy_m: captured.accuracy,
        captured_at: captured.capturedAt,
      });
      setPosition(captured);
      setContributionMessage(
        `Private verification contributed. The administrator sees only ${consensus.sample_count} sample(s), ${consensus.distinct_contributor_count} contributor(s) and aggregate quality—not your raw position or identity.`,
      );
    } catch (reason) {
      setContributionMessage(errorMessage(reason));
    } finally {
      setContributing(false);
    }
  };

  const PromptIcon = prompt?.tone === "warning" ? ClockAlert : prompt?.tone === "action" ? LocateFixed : MapPin;

  return (
    <section className={`duty-location-assistant duty-location-assistant--${prompt?.tone || "info"}`} aria-labelledby="dutyLocationTitle">
      <div className="duty-location-assistant__heading">
        <div className="duty-location-assistant__icon"><PromptIcon size={20} /></div>
        <div>
          <span>Private duty-location guidance</span>
          <h2 id="dutyLocationTitle">{prompt?.title || `${base.code} location verification`}</h2>
          <p>{prompt?.detail || "You may contribute a one-time observation to strengthen the approved base coordinate."}</p>
        </div>
        <span className="duty-location-assistant__base">{base.code} · {base.geofence_radius_m} m</span>
      </div>

      {!hasApprovedLocation ? (
        <div className="duty-location-assistant__result is-warning"><TriangleAlert size={17} /><span>This base does not yet have an approved coordinate. Attendance remains available without location guidance.</span></div>
      ) : (
        <div className="duty-location-assistant__actions">
          <button type="button" onClick={() => void checkLocation()} disabled={capturing || contributing}>
            <Crosshair size={16} /> {capturing ? "Checking once…" : "Check my location once"}
          </button>
          <button type="button" className="is-secondary" onClick={() => void contributeVerification()} disabled={capturing || contributing}>
            <ShieldCheck size={16} /> {contributing ? "Contributing…" : "Help verify this base"}
          </button>
        </div>
      )}

      <div className="duty-location-assistant__privacy">
        <ShieldCheck size={16} />
        <span>No background tracking is used. Proximity checks are transient. Verification samples are short-lived, tenant-scoped and replaced when you contribute again.</span>
      </div>

      {message ? (
        <div className={`duty-location-assistant__result ${evaluation?.inside_geofence ? "is-success" : evaluation?.review_signal ? "is-warning" : ""}`}>
          {evaluation?.inside_geofence ? <CheckCircle2 size={17} /> : evaluation?.review_signal ? <TriangleAlert size={17} /> : <MapPin size={17} />}
          <span>{message}{evaluation?.review_signal ? " The derived result requires human review; location alone is never treated as misconduct." : ""}</span>
        </div>
      ) : null}
      {contributionMessage ? <div className="duty-location-assistant__result"><ShieldCheck size={17} /><span>{contributionMessage}</span></div> : null}
    </section>
  );
}
