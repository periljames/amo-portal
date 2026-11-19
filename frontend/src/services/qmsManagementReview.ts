// src/services/qmsManagementReview.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsManagementReview(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/management-review"));
}

export type ReviewInput = { topic: string; summary: string; source_reference: string };
export type ReviewDecision = { id: string; title: string; rationale: string };
export type MeetingBody = {
  title: string; review_date: string; chair_user_id: string; attendee_user_ids: string[];
  agenda: string; inputs: ReviewInput[]; minutes: string; decisions: ReviewDecision[];
};
export type ReviewPayload = Partial<MeetingBody> & {
  review_id?: string; decision_id?: string; completion_evidence?: string;
  history?: { event: string; at: string; by: string; status: string; reason?: string }[];
  approval?: { by: string; at: string; reason: string };
  verification?: { by: string; at: string; reason: string };
};
export type ReviewRecord = {
  id: string; title: string; description?: string; status: string;
  owner_user_id: string; due_date: string; version: number; payload: ReviewPayload;
  actions?: ReviewRecord[];
};
export type ReviewMember = { id: string; first_name: string; last_name: string; email: string };
export type ReviewList = { items: ReviewRecord[]; total: number; offset: number; limit: number;
  summary: { meetings: number; awaiting_approval: number; open_actions: number; overdue_actions: number } };
export type ReviewActionBody = { title: string; description: string; owner_user_id: string; due_date: string; decision_id: string };

export function reviewRequest<T>(amoCode: string, path = "", body?: unknown, method = "POST"): Promise<T> {
  return apiRequest<T>(qmsPath(amoCode, `/management-review/workspace${path}`), body === undefined
    ? { cacheTtlMs: 0 }
    : { method, body: JSON.stringify(body), cacheTtlMs: 0 });
}
