import { apiGet } from "./crs";

export type Person360ReadinessItem = {
  key: string;
  label: string;
  status: string;
  reason?: string | null;
  source?: string | null;
  blocking?: boolean;
};

export type TrainingPerson360 = {
  person: {
    id: string;
    staff_code: string;
    full_name: string;
    position_title?: string | null;
    department_id?: string | null;
    department?: string | null;
    active: boolean;
    licence_number?: string | null;
    licence_expires_on?: string | null;
  };
  compliance: {
    counts: { current: number; due_soon: number; overdue: number; not_done: number };
    requirements: Array<{
      course_id: string;
      course_name: string;
      status: string;
      valid_until?: string | null;
      extended_due_date?: string | null;
      days_until_due?: number | null;
      last_completion_date?: string | null;
    }>;
  };
  records: Array<Record<string, unknown>>;
  assessments: Array<Record<string, unknown>>;
  certificates: Array<Record<string, unknown>>;
  external_and_workflow_evidence: Array<Record<string, unknown>>;
  authorization_cases: Array<{
    id: string;
    status: string;
    application_date?: string | null;
    requested_scope?: string | null;
    requested_privileges: string[];
    decision?: string | null;
    restrictions?: string | null;
    readiness: {
      overall_status: string;
      next_required_action?: string | null;
      items: Person360ReadinessItem[];
    };
  }>;
  technical_training_authorizations: Array<Record<string, unknown>>;
  competence_reviews: Array<Record<string, unknown>>;
  experience_reviews: Array<Record<string, unknown>>;
};

export const getTrainingPerson360 = (userId: string) =>
  apiGet<TrainingPerson360>(`/training/operating/people/${encodeURIComponent(userId)}/360`);
