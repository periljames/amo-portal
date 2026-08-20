import { apiGet, apiPost } from "./crs";

export type SessionCloseoutLearner = {
  id: string;
  user_id: string;
  status: string;
  completed: boolean;
  certificate_eligible: boolean;
  blockers: string[];
  decision: Record<string, unknown>;
};

export type TrainingSessionCloseout = {
  id: string;
  event_id: string;
  status: string;
  summary: Record<string, unknown>;
  closed_by_user_id?: string | null;
  closed_at?: string | null;
  learners: SessionCloseoutLearner[];
  verified_records?: number;
  issued_certificates?: Array<{
    record_id: string;
    certificate_issue_id: string;
    certificate_number: string;
  }>;
};

const root = (eventId: string) => `/training/operating/governance/events/${encodeURIComponent(eventId)}/closeout`;

export const getTrainingSessionCloseout = (eventId: string) =>
  apiGet<TrainingSessionCloseout>(root(eventId));

export const refreshTrainingSessionCloseout = (eventId: string) =>
  apiPost<TrainingSessionCloseout>(`${root(eventId)}/refresh`, {});

export const finalizeTrainingSessionCloseout = (eventId: string, note?: string) =>
  apiPost<TrainingSessionCloseout>(`${root(eventId)}/finalize`, { note: note || null });

export const verifyTrainingSessionCloseout = (eventId: string, note?: string, issueCertificates = true) =>
  apiPost<TrainingSessionCloseout>(`${root(eventId)}/verify`, { note: note || null, issue_certificates: issueCertificates });
