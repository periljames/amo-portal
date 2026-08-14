import React, { useMemo, useState } from "react";
import { CalendarPlus, ChevronLeft, ChevronRight, Mail, MapPin, Plus, RefreshCw, UsersRound } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import Drawer from "../shared/Drawer";
import { addTrainingEventParticipant, createTrainingEvent, listTrainingCourses, listTrainingEventParticipants, listTrainingEvents } from "../../services/training";
import { listTrainingPeopleReference, listTrainingSessionInvitations, sendTrainingSessionInvitations } from "../../services/trainingOperating";
import type { TrainingEventRead } from "../../types/training";

type Props = { canManage: boolean; onOpenAttendance: (eventId: string) => void };
const PAGE_SIZE = 25;
const emptySession = () => ({ course_id: "", title: "", starts_on: new Date().toISOString().slice(0, 10), ends_on: "", provider: "", location: "", notes: "" });

const TrainingSessionPlanner: React.FC<Props> = ({ canManage, onOpenAttendance }) => {
  const client = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [sessionOpen, setSessionOpen] = useState(false);
  const [rosterEvent, setRosterEvent] = useState<TrainingEventRead | null>(null);
  const [session, setSession] = useState(emptySession);
  const [selectedPeople, setSelectedPeople] = useState<string[]>([]);
  const [channels, setChannels] = useState<Array<"IN_APP" | "EMAIL">>(["IN_APP", "EMAIL"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const events = useQuery({ queryKey: ["training", "sessions", offset], queryFn: async () => { const rows = await listTrainingEvents({ limit: PAGE_SIZE + 1, offset }); return { items: rows.slice(0, PAGE_SIZE), hasMore: rows.length > PAGE_SIZE }; } });
  const courses = useQuery({ queryKey: ["training", "course-catalogue"], queryFn: () => listTrainingCourses({ limit: 500 }) });
  const people = useQuery({ queryKey: ["training", "people-reference"], queryFn: listTrainingPeopleReference, enabled: Boolean(rosterEvent) });
  const participants = useQuery({ queryKey: ["training", "session-participants", rosterEvent?.id], queryFn: () => listTrainingEventParticipants(rosterEvent!.id), enabled: Boolean(rosterEvent) });
  const invitations = useQuery({ queryKey: ["training", "session-invitations", rosterEvent?.id], queryFn: () => listTrainingSessionInvitations(rosterEvent!.id), enabled: Boolean(rosterEvent) });
  const participantIds = useMemo(() => new Set((participants.data || []).map((item) => item.user_id)), [participants.data]);

  const create = async () => {
    setBusy(true); setError(null);
    try {
      await createTrainingEvent({ ...session, ends_on: session.ends_on || null, provider: session.provider || null, location: session.location || null, notes: session.notes || null, status: "PLANNED" });
      setSession(emptySession()); setSessionOpen(false); await client.invalidateQueries({ queryKey: ["training", "sessions"] });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Session could not be created."); } finally { setBusy(false); }
  };
  const invite = async () => {
    if (!rosterEvent || !selectedPeople.length) return;
    setBusy(true); setError(null);
    try {
      for (const userId of selectedPeople.filter((id) => !participantIds.has(id))) await addTrainingEventParticipant({ event_id: rosterEvent.id, user_id: userId, status: "INVITED" });
      await sendTrainingSessionInvitations(rosterEvent.id, selectedPeople, channels, `You are invited to ${rosterEvent.title} on ${rosterEvent.starts_on}.`);
      setSelectedPeople([]); await client.invalidateQueries({ queryKey: ["training", "session-participants", rosterEvent.id] }); await client.invalidateQueries({ queryKey: ["training", "session-invitations", rosterEvent.id] });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Invitations could not be delivered."); } finally { setBusy(false); }
  };

  return <div className="tos-stack training-route-workspace">
    <section className="tos-card tos-route-commandbar"><div><p className="tos-kicker">Delivery lifecycle</p><h2>Session scheduler</h2><p>Create the governed event, build its canonical roster, deliver invitations and move directly to the instructor attendance console.</p></div><button disabled={!canManage} onClick={() => setSessionOpen(true)}><CalendarPlus size={16} /> Session</button><button onClick={() => void events.refetch()} aria-label="Refresh sessions"><RefreshCw size={16} /></button></section>
    {error ? <div className="tos-banner tos-banner--error">{error}<button onClick={() => setError(null)}>×</button></div> : null}
    <section className="tos-card tos-process-rail"><span>Plan cohort</span><i>→</i><span>Create session</span><i>→</i><span>Invite / RSVP</span><i>→</i><span>QR attendance</span><i>→</i><span>Certify QMS/36</span><i>→</i><span>Completion gates</span></section>
    <section className="tos-card tos-register-card">{events.isError ? <div className="tos-empty"><strong>Session source unavailable</strong><span>No empty register is being inferred.</span></div> : <div className="tos-table-wrap"><table className="tos-table tos-table--interactive"><thead><tr><th>Date</th><th>Session</th><th>Provider / location</th><th>Roster</th><th>Status</th><th>Actions</th></tr></thead><tbody>{(events.data?.items || []).map((event) => <tr key={event.id}><td>{event.starts_on}<small>{event.ends_on && event.ends_on !== event.starts_on ? `to ${event.ends_on}` : ""}</small></td><td><strong>{event.title}</strong><small>{event.course_code || event.course_name || event.course_id}</small></td><td>{event.provider || "Internal"}<small><MapPin size={12} /> {event.location || "Venue not set"}</small></td><td>{event.participant_count ?? "Open roster"}</td><td><span className="tos-pill tos-pill--ok">{event.status}</span></td><td><div className="tos-actions"><button onClick={() => setRosterEvent(event)}><UsersRound size={15} /> Roster</button><button onClick={() => onOpenAttendance(event.id)}>Attendance</button></div></td></tr>)}</tbody></table></div>}<footer className="tos-pagination"><span>Page {Math.floor(offset / PAGE_SIZE) + 1}</span><div><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={17} /></button><button disabled={!events.data?.hasMore} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={17} /></button></div></footer></section>

    <Drawer title="Create training session" isOpen={sessionOpen} onClose={() => setSessionOpen(false)} panelClassName="training-form-drawer"><div className="tos-drawer-form"><label>Course<select value={session.course_id} onChange={(e) => { const selected = courses.data?.find((item) => item.id === e.target.value); setSession({ ...session, course_id: e.target.value, title: session.title || selected?.course_name || "" }); }}><option value="">Select course</option>{(courses.data || []).map((item) => <option key={item.id} value={item.id}>{item.course_id} · {item.course_name}</option>)}</select></label><label>Session title<input value={session.title} onChange={(e) => setSession({ ...session, title: e.target.value })} /></label><div className="tos-form-grid"><label>Starts<input type="date" value={session.starts_on} onChange={(e) => setSession({ ...session, starts_on: e.target.value })} /></label><label>Ends<input type="date" value={session.ends_on} onChange={(e) => setSession({ ...session, ends_on: e.target.value })} /></label><label>Provider<input value={session.provider} onChange={(e) => setSession({ ...session, provider: e.target.value })} /></label><label>Location<input value={session.location} onChange={(e) => setSession({ ...session, location: e.target.value })} /></label></div><label>Notes<textarea value={session.notes} onChange={(e) => setSession({ ...session, notes: e.target.value })} /></label><div className="tos-actions"><button onClick={() => setSessionOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !session.course_id || !session.title || !session.starts_on} onClick={() => void create()}>Create session</button></div></div></Drawer>
    <Drawer title={rosterEvent ? `Roster · ${rosterEvent.title}` : "Session roster"} isOpen={Boolean(rosterEvent)} onClose={() => setRosterEvent(null)} panelClassName="training-form-drawer"><div className="tos-drawer-form"><section className="tos-inline-proof"><UsersRound size={17} /><span>{participants.data?.length || 0} roster members</span><strong>{invitations.data?.items.filter((item) => item.delivery_status === "FAILED").length || 0} delivery failures</strong></section><label>Add people<select multiple size={10} value={selectedPeople} onChange={(e) => setSelectedPeople(Array.from(e.target.selectedOptions, (option) => option.value))}>{(people.data || []).map((person) => <option key={person.id} value={person.id}>{person.staff_code} · {person.full_name}{participantIds.has(person.id) ? " (on roster)" : ""}</option>)}</select></label><div className="tos-check-grid"><label><input type="checkbox" checked={channels.includes("IN_APP")} onChange={(e) => setChannels(e.target.checked ? [...new Set([...channels, "IN_APP" as const])] : channels.filter((item) => item !== "IN_APP"))} /> In-app</label><label><input type="checkbox" checked={channels.includes("EMAIL")} onChange={(e) => setChannels(e.target.checked ? [...new Set([...channels, "EMAIL" as const])] : channels.filter((item) => item !== "EMAIL"))} /> Email</label></div><button className="primary-chip-btn" disabled={busy || !selectedPeople.length || !channels.length} onClick={() => void invite()}><Mail size={16} /> Add and send invitations</button><div className="tos-list">{(invitations.data?.items || []).map((item) => <div key={item.id}><div><strong>{people.data?.find((person) => person.id === item.user_id)?.full_name || item.user_id}</strong><small>{item.channel} · Attempt {item.attempt_count}{item.last_error ? ` · ${item.last_error}` : ""}</small></div><span className={`tos-pill ${item.delivery_status === "FAILED" ? "tos-pill--critical" : "tos-pill--ok"}`}>{item.delivery_status} / {item.rsvp_status}</span></div>)}</div></div></Drawer>
  </div>;
};

export default TrainingSessionPlanner;
