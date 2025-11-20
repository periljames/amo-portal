// src/types/crs.ts

// Enums – mirror backend pydantic enums
export type ReleasingAuthority = "KCAA" | "ECAA" | "GCAA";

export type AirframeLimitUnit = "HOURS" | "CYCLES";

// --- Sign-offs ---

export interface CRSSignoffCreate {
  category: string; // e.g. "AEROPLANES", "ENGINES", etc.
  sign_date?: string; // ISO date "YYYY-MM-DD"
  full_name_and_signature?: string;
  internal_auth_ref?: string;
  stamp?: string;
}

export interface CRSSignoffRead extends CRSSignoffCreate {
  id: number;
}

// --- CRS payloads ---

// Shape for POST /crs/ – mirrors backend but most fields optional.
export interface CRSCreate {
  // Header
  releasing_authority: ReleasingAuthority;
  operator_contractor: string;
  job_no?: string;
  wo_no?: string;
  location: string;

  // Aircraft & engines
  aircraft_type: string;
  aircraft_reg: string;
  msn?: string;

  lh_engine_type?: string;
  rh_engine_type?: string;
  lh_engine_sno?: string;
  rh_engine_sno?: string;

  aircraft_tat?: number;
  aircraft_tac?: number;
  lh_hrs?: number;
  lh_cyc?: number;
  rh_hrs?: number;
  rh_cyc?: number;

  // Work / deferred maintenance
  maintenance_carried_out: string;
  deferred_maintenance?: string;
  date_of_completion: string; // ISO date

  // Maintenance data – check boxes & refs
  amp_used: boolean;
  amm_used: boolean;
  mtx_data_used: boolean;

  amp_reference?: string;
  amp_revision?: string;
  amp_issue_date?: string; // ISO date

  amm_reference?: string;
  amm_revision?: string;
  amm_issue_date?: string; // ISO date

  add_mtx_data?: string;
  work_order_no?: string;

  // Expiry / next maintenance
  airframe_limit_unit: AirframeLimitUnit;
  expiry_date?: string; // ISO date
  hrs_to_expiry?: number;
  sum_airframe_tat_expiry?: number;
  next_maintenance_due?: string;

  // Certificate issued by
  issuer_full_name: string;
  issuer_auth_ref: string;
  issuer_license: string;
  crs_issue_date: string; // ISO date
  crs_issuing_stamp?: string;

  // Nested sign-offs
  signoffs: CRSSignoffCreate[];
}

// Shape returned by GET /crs/ and POST /crs/
export interface CRSRead extends CRSCreate {
  id: number;
  crs_serial: string;
  barcode_value: string;

  created_by_id?: number | null;
  created_at: string;
  updated_at: string;

  is_archived: boolean;
  archived_at?: string | null;
  expires_at?: string | null;

  // In read responses signoffs include ids
  signoffs: CRSSignoffRead[];
}
