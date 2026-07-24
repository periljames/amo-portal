import { apiJson } from "./typedApi";

export type RosterCommitmentRead = {
  id: string;
  user_id: string;
  user_full_name: string;
  user_staff_code: string;
  department_id?: string | null;
  kind: string;
  source_module: "WORKFORCE" | "TRAINING" | "QUALITY" | string;
  source_type: string;
  source_id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  all_day: boolean;
  blocking: boolean;
  provisional: boolean;
  status?: string | null;
  location_label?: string | null;
  detail?: string | null;
  editable: false;
};

export type RosterCommitmentResponse = {
  from_date: string;
  to_date: string;
  timezone_name: string;
  items: RosterCommitmentRead[];
  counts: Record<string, number>;
};

export function listRosterCommitments(params: {
  from: string;
  to: string;
  user_id?: string[];
}): Promise<RosterCommitmentResponse> {
  const search = new URLSearchParams({ from: params.from, to: params.to });
  params.user_id?.forEach((userId) => search.append("user_id", userId));
  return apiJson(`/rostering/commitments?${search.toString()}`);
}
