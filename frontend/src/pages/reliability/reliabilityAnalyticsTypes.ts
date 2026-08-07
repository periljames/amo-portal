import type React from "react";

export type MetricStatus = "GOOD" | "WATCH" | "ALERT" | "NEUTRAL" | "NO_DATA";
export type MetricDirection = "UP" | "DOWN" | "FLAT" | "UNKNOWN";

export type CalculationFormula = {
  code: string;
  name: string;
  version: string;
  origin: "SYSTEM" | "PROGRAMME";
  latex: string;
  mathml: string;
  expression: Record<string, unknown>;
  unit: string;
  precision: number;
  rounding_mode: string;
  numerator_label: string;
  denominator_label?: string | null;
  multiplier?: number | null;
  methodology: string;
  denominator_policy: string;
  source_fields: string[];
  applied_to: string[];
};

export type DashboardMetric = {
  code: string;
  label: string;
  value: number | null;
  unit: string;
  delta_pct?: number | null;
  direction: MetricDirection;
  status: MetricStatus;
  denominator?: number | null;
  detail: string;
  formula_code?: string | null;
  drilldown: DrilldownDescriptor;
};

export type DrilldownDescriptor = {
  dimension?: string;
  key?: string;
  bucket?: string;
};

export type ChartPoint = {
  key: string;
  label: string;
  metrics: Record<string, number | null>;
  drilldown: DrilldownDescriptor;
};

export type FilterOptions = {
  aircraft: string[];
  aircraft_types: string[];
  ata_chapters: string[];
  stations: string[];
  event_types: string[];
  severities: string[];
  source_systems: string[];
  engine_positions: string[];
  engine_metrics: string[];
};

export type DashboardResponse = {
  generated_at: string;
  period_start: string;
  period_end: string;
  comparison_start: string;
  comparison_end: string;
  bucket: "DAY" | "WEEK" | "MONTH";
  filters: FilterOptions;
  formulae: CalculationFormula[];
  summary: DashboardMetric[];
  time_series: ChartPoint[];
  event_mix: ChartPoint[];
  ata_pareto: ChartPoint[];
  aircraft_performance: ChartPoint[];
  station_delay: ChartPoint[];
  route_delay: ChartPoint[];
  component_reliability: ChartPoint[];
  component_removal_age: ChartPoint[];
  shop_visit_trend: ChartPoint[];
  oil_consumption: ChartPoint[];
  deferral_status: ChartPoint[];
  deferral_expiry: ChartPoint[];
  deferral_categories: ChartPoint[];
  deferral_extensions: ChartPoint[];
  deferral_repeats: ChartPoint[];
  deferral_closure: ChartPoint[];
  fracas_stages: ChartPoint[];
  fracas_ageing: ChartPoint[];
  root_causes: ChartPoint[];
  effectiveness: ChartPoint[];
  fracas_actions: ChartPoint[];
  fracas_action_trend: ChartPoint[];
  fracas_reopened: ChartPoint[];
  engine_status: ChartPoint[];
  source_health: ChartPoint[];
  data_quality: ChartPoint[];
  warnings: string[];
};

export type DrilldownRecord = {
  id: string;
  record_type: string;
  occurred_at?: string | null;
  aircraft_serial_number?: string | null;
  reference?: string | null;
  category?: string | null;
  status?: string | null;
  severity?: string | null;
  ata_chapter?: string | null;
  summary: string;
  route?: string | null;
  details: Record<string, unknown>;
};

export type DrilldownResponse = {
  dimension: string;
  key: string;
  total: number;
  limit: number;
  offset: number;
  records: DrilldownRecord[];
};

export type EngineSeriesPoint = {
  timestamp: string;
  value: number;
  aircraft_serial_number: string;
  engine_position: string;
  engine_serial_number?: string | null;
};

export type EngineSeriesResponse = {
  generated_at: string;
  period_start: string;
  period_end: string;
  metric: string;
  unit?: string | null;
  series: Record<string, EngineSeriesPoint[]>;
  thresholds: Array<{ label: string; value: number; comparator: string; severity: string; scope?: string | null }>;
  markers: Array<{ timestamp: string; label: string; status: string; aircraft_serial_number: string; engine_position: string }>;
};

export type DashboardFilters = {
  periodStart: string;
  periodEnd: string;
  bucket: "AUTO" | "DAY" | "WEEK" | "MONTH";
  aircraft: string;
  aircraftType: string;
  ataChapter: string;
  station: string;
  eventType: string;
  severity: string;
  sourceSystem: string;
};

export type SavedView = {
  id: string;
  name: string;
  filters: DashboardFilters;
};

export type ChartTableRow = Record<string, unknown>;

export type ChartCardProps = {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  empty: boolean;
  children: React.ReactNode;
  onExport?: () => void;
  wide?: boolean;
  tableRows?: ChartTableRow[];
  formulaCodes?: string[];
};
