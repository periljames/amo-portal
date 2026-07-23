import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, format, parseISO, startOfWeek } from "date-fns";
import {
  ArrowLeft,
  ArrowRight,
  CalendarClock,
  Download,
  GraduationCap,
  RefreshCw,
  ShieldCheck,
  Umbrella,
} from "lucide-react";

import {
  listRosterCommitments,
  type RosterCommitmentRead,
} from "../../../services/rosterCommitments";
import { downloadBlob } from "../../../services/typedApi";
import { errorMessage, isoDate } from "../rosterUi";
import { EmptyState, StatusPill } from "./RosterShell";
import "../../../styles/rostering-unified.css";

type RangeMode = 7 | 28;

function commitmentIcon(source: string) {
  if (source === "TRAINING") return GraduationCap;
  if (source === "QUALITY") return ShieldCheck;
  return Umbrella;
}

function localDate(value: string, timezoneName: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezoneName,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(parseISO(value));
  const map = Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  return `${map.year}-${map.month}-${map.day}`;
}

function escapeCsv(value: unknown): string {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function exportCommitments(items: RosterCommitmentRead[], from: string, to: string) {
  const headings = [
    "Staff code",
    "Employee",
    "Source",
    "Type",
    "Title",
    "Starts",
    "Ends",
    "Status",
    "Blocking",
    "Location",
    "Detail",
  ];
  const rows = items.map((item) => [
    item.user_staff_code,
    item.user_full_name,
    item.source_module,
    item.kind,
    item.title,
    item.starts_at,
    item.ends_at,
    item.status,
    item.blocking ? "Yes" : "No",
    item.location_label,
    item.detail,
  ]);
  const csv = [headings, ...rows].map((row) => row.map(escapeCsv).join(",")).join("\n");
  downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8" }), `roster-commitments-${from}-${to}.csv`);
}

export function RosterCommitmentBoard() {
  const [mode, setMode] = useState<RangeMode>(7);
  const [anchor, setAnchor] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const days = useMemo(() => Array.from({ length: mode }, (_, index) => addDays(anchor, index)), [anchor, mode]);
  const from = isoDate(days[0]);
  const to = isoDate(days[days.length - 1]);

  const query = useQuery({
    queryKey: ["rostering", "unified-commitments", from, to],
    queryFn: () => listRosterCommitments({ from, to }),
    staleTime: 30_000,
    gcTime: 24 * 60 * 60_000,
    networkMode: "offlineFirst",
  });

  const timezoneName = query.data?.timezone_name || "UTC";
  const items = query.data?.items || [];
  const people = useMemo(() => {
    const grouped = new Map<string, { userId: string; name: string; staffCode: string; items: RosterCommitmentRead[] }>();
    items.forEach((item) => {
      const current = grouped.get(item.user_id) || {
        userId: item.user_id,
        name: item.user_full_name,
        staffCode: item.user_staff_code,
        items: [],
      };
      current.items.push(item);
      grouped.set(item.user_id, current);
    });
    return [...grouped.values()].sort((left, right) => left.name.localeCompare(right.name));
  }, [items]);

  const move = (direction: -1 | 1) => setAnchor((value) => addDays(value, mode * direction));

  return (
    <section className="wr-panel wr-commitments" aria-label="Fixed cross-module commitments">
      <div className="wr-section-heading wr-commitments__heading">
        <div>
          <span className="wr-eyebrow">Canonical availability · read only</span>
          <h2>Training, leave and Quality commitments</h2>
          <p>Owned by their source modules and projected here automatically. No duplicate roster-only records are created.</p>
        </div>
        <div className="wr-actions">
          <button className="wr-button wr-button--secondary" type="button" disabled={!items.length} onClick={() => exportCommitments(items, from, to)}><Download size={15} /> Export CSV</button>
          <button className="wr-icon-button" type="button" aria-label="Refresh commitments" onClick={() => void query.refetch()}><RefreshCw size={16} className={query.isFetching ? "is-spinning" : ""} /></button>
        </div>
      </div>

      <div className="wr-commitments__toolbar">
        <div className="wr-toolbar-group">
          <button type="button" className="wr-icon-button" aria-label="Previous range" onClick={() => move(-1)}><ArrowLeft size={16} /></button>
          <button type="button" className="wr-button wr-button--secondary" onClick={() => setAnchor(startOfWeek(new Date(), { weekStartsOn: 1 }))}>Current week</button>
          <button type="button" className="wr-icon-button" aria-label="Next range" onClick={() => move(1)}><ArrowRight size={16} /></button>
          <strong>{format(days[0], "dd MMM")} – {format(days[days.length - 1], "dd MMM yyyy")}</strong>
        </div>
        <div className="wr-segmented" role="group" aria-label="Commitment range">
          <button type="button" className={mode === 7 ? "is-active" : ""} onClick={() => setMode(7)}>Week</button>
          <button type="button" className={mode === 28 ? "is-active" : ""} onClick={() => setMode(28)}>4 weeks</button>
        </div>
        <div className="wr-commitments__counts">
          <span><GraduationCap size={14} /> {query.data?.counts.TRAINING || 0} training</span>
          <span><Umbrella size={14} /> {(query.data?.counts.ANNUAL_LEAVE || 0) + (query.data?.counts.SICK_LEAVE || 0) + (query.data?.counts.UNAVAILABLE || 0)} absence</span>
          <span><ShieldCheck size={14} /> {query.data?.counts.QMS_AUDIT || 0} Quality</span>
        </div>
      </div>

      {query.error ? <div className="wr-inline-error" role="alert">Commitments could not be loaded: {errorMessage(query.error)}</div> : null}
      {query.isPending ? <div className="wr-commitments__loading"><span className="wr-spinner" /> Synchronising source modules…</div> : null}
      {!query.isPending && !query.error && people.length === 0 ? <EmptyState title="No fixed commitments in this range" description="Scheduled training, approved leave, unavailability and assigned Quality audits will appear automatically." /> : null}

      {people.length ? (
        <div className={`wr-commitment-grid${mode === 28 ? " is-month" : ""}`} style={{ "--wr-commitment-days": mode } as React.CSSProperties}>
          <div className="wr-commitment-grid__corner"><CalendarClock size={15} /> Person</div>
          {days.map((day) => <div className="wr-commitment-grid__day" key={isoDate(day)}><strong>{format(day, "EEE")}</strong><span>{format(day, "dd MMM")}</span></div>)}
          {people.map((person) => (
            <div className="wr-commitment-grid__row" key={person.userId}>
              <div className="wr-commitment-grid__person"><strong>{person.name}</strong><span>{person.staffCode}</span></div>
              {days.map((day) => {
                const dateKey = isoDate(day);
                const cellItems = person.items.filter((item) => {
                  const start = localDate(item.starts_at, timezoneName);
                  const endExclusive = localDate(item.ends_at, timezoneName);
                  return dateKey >= start && (item.all_day ? dateKey < endExclusive : dateKey <= endExclusive);
                });
                return (
                  <div className="wr-commitment-grid__cell" key={`${person.userId}:${dateKey}`}>
                    {cellItems.map((item) => {
                      const Icon = commitmentIcon(item.source_module);
                      return <article key={item.id} className={`wr-commitment wr-commitment--${item.source_module.toLowerCase()}`} title={[item.title, item.detail, item.location_label].filter(Boolean).join(" · ")}><Icon size={13} /><span><strong>{item.kind.replace(/_/g, " ")}</strong><small>{item.title}</small></span>{item.provisional ? <StatusPill value="PROVISIONAL" /> : null}</article>;
                    })}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
