import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  keepPreviousData,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  getRosterContracts,
  getRosterVersion,
  listRosterAssignments,
  listRosterFindings,
  listRosterPeriods,
  listShiftTemplates,
} from "../../../services/rostering";
import { listRosterPeoplePage } from "../../../services/workforce";
import {
  listOfflineMutations,
  type OfflineMutationEntry,
} from "../../../services/offlinePersistence";
import { useDebouncedValue } from "../../../hooks/useDebouncedValue";
import type {
  RosterAssignmentRead,
  RosterContractResponse,
  RosterEmployeeRead,
  RosterPeriodRead,
  RosterValidationFindingRead,
  RosterVersionRead,
  ShiftTemplateRead,
} from "../../../types/rostering";

type VersionWorkspace = {
  version: RosterVersionRead;
  assignments: RosterAssignmentRead[];
  findings: RosterValidationFindingRead[];
};

type PlannerDataV2 = {
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  anchor: Date;
  setAnchor: (next: Date) => void;
  week: { from: string; to: string };
  periods: RosterPeriodRead[];
  selectedPeriodId: string;
  setSelectedPeriodId: (value: string) => void;
  versions: RosterVersionRead[];
  selectedVersionId: string;
  setSelectedVersionId: (value: string) => void;
  selectedVersion: RosterVersionRead | null;
  assignments: RosterAssignmentRead[];
  setAssignments: Dispatch<SetStateAction<RosterAssignmentRead[]>>;
  findings: RosterValidationFindingRead[];
  people: RosterEmployeeRead[];
  peopleTotal: number;
  peopleDepartments: Array<{ id: string; name: string; code?: string | null }>;
  peopleSearch: string;
  setPeopleSearch: (value: string) => void;
  peopleDepartmentId: string;
  setPeopleDepartmentId: (value: string) => void;
  peopleHasMore: boolean;
  peopleLoadingMore: boolean;
  loadMorePeople: () => Promise<void>;
  templates: ShiftTemplateRead[];
  contracts: RosterContractResponse | null;
  refresh: () => Promise<void>;
  moveWeek: (direction: -1 | 1) => void;
};

const PEOPLE_PAGE_SIZE = 120;
const PERIOD_STALE_MS = 30_000;
const WORKSPACE_STALE_MS = 15_000;
const REFERENCE_STALE_MS = 10 * 60_000;
const ROSTER_GC_MS = 30 * 60_000;
const PENDING_OUTBOX_STATUSES = new Set(["PENDING", "SYNCING", "RETRY"]);
const ASSIGNMENT_PATCH_FIELDS = [
  "user_id",
  "roster_date",
  "shift_template_id",
  "start_time",
  "end_time",
  "status",
  "station_id",
  "department_id",
  "notes",
  "source_type",
  "source_reference_id",
] as const;

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Failed to load roster planner data.";
}

function isoDate(value: Date) {
  return value.toISOString().slice(0, 10);
}

function weekBounds(anchor: Date) {
  const normalized = new Date(anchor);
  normalized.setHours(12, 0, 0, 0);
  const weekday = normalized.getDay();
  const mondayOffset = weekday === 0 ? -6 : 1 - weekday;
  const from = new Date(normalized);
  from.setDate(normalized.getDate() + mondayOffset);
  const to = new Date(from);
  to.setDate(from.getDate() + 6);
  return { from: isoDate(from), to: isoDate(to) };
}

function addWeeks(value: Date, amount: number) {
  const next = new Date(value);
  next.setDate(next.getDate() + amount * 7);
  return next;
}

function newest(period: RosterPeriodRead | undefined) {
  return [...(period?.versions || [])]
    .sort((left, right) => right.version_number - left.version_number)[0];
}

const periodsKey = (from: string, to: string) => ["rostering", "planner", "periods", from, to] as const;
const workspaceKey = (versionId: string) => ["rostering", "planner", "workspace", versionId] as const;

async function loadVersionWorkspace(versionId: string): Promise<VersionWorkspace> {
  const [version, assignments, findings] = await Promise.all([
    getRosterVersion(versionId),
    listRosterAssignments(versionId),
    listRosterFindings(versionId, true),
  ]);
  return { version, assignments, findings };
}

function parseOutboxBody(entry: OfflineMutationEntry): Record<string, unknown> {
  if (!entry.body) return {};
  try {
    const parsed = JSON.parse(entry.body) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function pendingCreateRow(
  workspace: VersionWorkspace,
  versionId: string,
  entry: OfflineMutationEntry,
  body: Record<string, unknown>,
): RosterAssignmentRead | null {
  const userId = stringValue(body.user_id);
  const rosterDate = stringValue(body.roster_date);
  if (!userId || !rosterDate) return null;
  const sourceReference = stringValue(body.source_reference_id) || entry.idempotencyKey;
  const optimisticId = `offline-${entry.id}`;
  const existing = workspace.assignments.find((row) => (
    row.id === optimisticId || row.source_reference_id === sourceReference
  ));
  if (existing) return existing;
  const now = new Date(entry.createdAt).toISOString();
  return {
    id: optimisticId,
    version_id: versionId,
    user_id: userId,
    user_name: `Pending assignment (${userId.slice(0, 8)})`,
    department_id: stringValue(body.department_id),
    station_id: stringValue(body.station_id),
    roster_date: rosterDate,
    shift_template_id: stringValue(body.shift_template_id),
    shift_code: null,
    shift_name: null,
    shift_kind: null,
    shift_color: null,
    start_time: stringValue(body.start_time),
    end_time: stringValue(body.end_time),
    break_minutes: 0,
    crosses_midnight: false,
    paid_hours: 0,
    status: (stringValue(body.status) || "DRAFT") as RosterAssignmentRead["status"],
    notes: stringValue(body.notes),
    source_type: stringValue(body.source_type) || "MANUAL",
    source_reference_id: sourceReference,
    compliance_hold: false,
    compliance_summary: null,
    state_revision: 1,
    created_at: now,
    updated_at: now,
  };
}

function assignmentIdFromPath(path: string): string | null {
  const match = path.match(/^\/rostering\/assignments\/([^/?]+)$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function applyPendingPatch(
  row: RosterAssignmentRead,
  previousRow: RosterAssignmentRead | undefined,
  entry: OfflineMutationEntry,
  body: Record<string, unknown>,
): RosterAssignmentRead {
  const restored = previousRow && Number(previousRow.state_revision || 0) > Number(row.state_revision || 0)
    ? { ...previousRow }
    : { ...row };
  const patched: Record<string, unknown> = { ...restored };
  for (const field of ASSIGNMENT_PATCH_FIELDS) {
    if (field in body) patched[field] = body[field];
  }
  if (typeof body.compliance_hold === "boolean") patched.compliance_hold = body.compliance_hold;
  const requestedRevision = Number(body.expected_state_revision || 0);
  patched.state_revision = Math.max(Number(restored.state_revision || 0) + 1, requestedRevision + 1);
  patched.updated_at = new Date(entry.updatedAt || entry.createdAt).toISOString();
  return patched as unknown as RosterAssignmentRead;
}

function mergePendingRosterOutbox(
  workspace: VersionWorkspace,
  previous: VersionWorkspace | undefined,
  entries: OfflineMutationEntry[],
  versionId: string,
): VersionWorkspace {
  const previousAssignments = previous?.assignments || [];
  let assignments = [...workspace.assignments];
  const createPath = `/rostering/versions/${encodeURIComponent(versionId)}/assignments`;

  entries
    .filter((entry) => entry.entityType === "roster-assignment" && PENDING_OUTBOX_STATUSES.has(entry.status))
    .sort((left, right) => left.createdAt - right.createdAt)
    .forEach((entry) => {
      const path = entry.path.split("?", 1)[0];
      const body = parseOutboxBody(entry);

      if (entry.method === "POST" && path === createPath) {
        const sourceReference = stringValue(body.source_reference_id) || entry.idempotencyKey;
        if (assignments.some((row) => row.source_reference_id === sourceReference)) return;
        const restored = previousAssignments.find((row) => (
          row.id === `offline-${entry.id}` || row.source_reference_id === sourceReference
        )) || pendingCreateRow(workspace, versionId, entry, body);
        if (restored) assignments.push(restored);
        return;
      }

      const assignmentId = entry.entityId || assignmentIdFromPath(path);
      if (!assignmentId) return;

      if (entry.method === "DELETE") {
        assignments = assignments.filter((row) => row.id !== assignmentId);
        return;
      }

      if (entry.method === "PATCH") {
        const previousRow = previousAssignments.find((row) => row.id === assignmentId);
        assignments = assignments.map((row) => (
          row.id === assignmentId ? applyPendingPatch(row, previousRow, entry, body) : row
        ));
      }
    });

  return { ...workspace, assignments };
}

export function useRosterPlannerDataV2(): PlannerDataV2 {
  const queryClient = useQueryClient();
  const [anchor, setAnchor] = useState(new Date());
  const week = useMemo(() => weekBounds(anchor), [anchor]);
  const [selectedPeriodId, setSelectedPeriodId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const [peopleSearch, setPeopleSearch] = useState("");
  const [peopleDepartmentId, setPeopleDepartmentId] = useState("");
  const debouncedPeopleSearch = useDebouncedValue(peopleSearch.trim(), 250);

  const periodsQuery = useQuery({
    queryKey: periodsKey(week.from, week.to),
    queryFn: () => listRosterPeriods({ from: week.from, to: week.to }),
    staleTime: PERIOD_STALE_MS,
    gcTime: ROSTER_GC_MS,
    placeholderData: keepPreviousData,
    networkMode: "offlineFirst",
  });

  const peopleQuery = useInfiniteQuery({
    queryKey: [
      "rostering",
      "planner",
      "eligible-people",
      debouncedPeopleSearch,
      peopleDepartmentId,
    ],
    queryFn: ({ pageParam }) => listRosterPeoplePage({
      page: pageParam,
      page_size: PEOPLE_PAGE_SIZE,
      search: debouncedPeopleSearch || null,
      department_id: peopleDepartmentId || null,
      active_only: true,
      roster_eligible_only: true,
    }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.page + 1 : undefined,
    staleTime: REFERENCE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
  });

  const templatesQuery = useQuery({
    queryKey: ["rostering", "planner", "shift-templates", "active"],
    queryFn: () => listShiftTemplates(false),
    staleTime: REFERENCE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
  });

  const contractsQuery = useQuery({
    queryKey: ["rostering", "planner", "contracts"],
    queryFn: getRosterContracts,
    staleTime: REFERENCE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
  });

  const periods = periodsQuery.data || [];
  const selectedPeriod = periods.find((row) => row.id === selectedPeriodId);
  const versions = selectedPeriod?.versions || [];
  const peoplePages = peopleQuery.data?.pages || [];
  const people = useMemo(
    () => peoplePages.flatMap((page) => page.items),
    [peoplePages],
  );
  const peopleTotal = peoplePages[0]?.total || 0;
  const peopleDepartments = peoplePages[0]?.departments || [];

  useEffect(() => {
    if (!periods.length) {
      setSelectedPeriodId("");
      return;
    }
    const current = periods.find((row) => row.id === selectedPeriodId);
    const next = current
      || periods.find((row) => row.starts_on <= week.to && row.ends_on >= week.from)
      || periods[0];
    if (next && next.id !== selectedPeriodId) setSelectedPeriodId(next.id);
  }, [periods, selectedPeriodId, week.from, week.to]);

  useEffect(() => {
    if (!selectedPeriod) {
      setSelectedVersionId("");
      return;
    }
    const current = selectedPeriod.versions.find((row) => row.id === selectedVersionId);
    const next = current || newest(selectedPeriod);
    if ((next?.id || "") !== selectedVersionId) setSelectedVersionId(next?.id || "");
  }, [selectedPeriod, selectedVersionId]);

  const workspaceQuery = useQuery({
    queryKey: workspaceKey(selectedVersionId),
    queryFn: async () => {
      const previous = queryClient.getQueryData<VersionWorkspace>(workspaceKey(selectedVersionId));
      const [workspace, pendingEntries] = await Promise.all([
        loadVersionWorkspace(selectedVersionId),
        listOfflineMutations().catch(() => []),
      ]);
      return mergePendingRosterOutbox(workspace, previous, pendingEntries, selectedVersionId);
    },
    enabled: Boolean(selectedVersionId),
    staleTime: WORKSPACE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
  });

  // The persisted version workspace is the single source of assignment state.
  // Offline optimistic creates/updates/deletes therefore survive reloads. Every
  // subsequent cached or network workspace load projects the durable outbox over
  // the server snapshot before React Query can publish it.
  const assignments = workspaceQuery.data?.assignments || [];
  const setAssignments = useCallback<Dispatch<SetStateAction<RosterAssignmentRead[]>>>((update) => {
    if (!selectedVersionId) return;
    queryClient.setQueryData<VersionWorkspace>(workspaceKey(selectedVersionId), (current) => {
      if (!current) return current;
      const next = typeof update === "function" ? update(current.assignments) : update;
      if (next === current.assignments) return current;
      return { ...current, assignments: next };
    });
  }, [queryClient, selectedVersionId]);

  useEffect(() => {
    for (const direction of [-1, 1] as const) {
      const adjacent = weekBounds(addWeeks(anchor, direction));
      void queryClient.prefetchQuery({
        queryKey: periodsKey(adjacent.from, adjacent.to),
        queryFn: () => listRosterPeriods({ from: adjacent.from, to: adjacent.to }),
        staleTime: PERIOD_STALE_MS,
        gcTime: ROSTER_GC_MS,
        networkMode: "offlineFirst",
      });
    }
  }, [anchor, queryClient]);

  const refresh = useCallback(async () => {
    setManualRefreshing(true);
    try {
      await Promise.allSettled([
        periodsQuery.refetch(),
        peopleQuery.refetch(),
        templatesQuery.refetch(),
        contractsQuery.refetch(),
        selectedVersionId ? workspaceQuery.refetch() : Promise.resolve(),
      ]);
    } finally {
      setManualRefreshing(false);
    }
  }, [contractsQuery, peopleQuery, periodsQuery, selectedVersionId, templatesQuery, workspaceQuery]);

  const loadMorePeople = useCallback(async () => {
    if (!peopleQuery.hasNextPage || peopleQuery.isFetchingNextPage) return;
    await peopleQuery.fetchNextPage();
  }, [peopleQuery]);

  const firstError = [
    periodsQuery.error,
    peopleQuery.error,
    templatesQuery.error,
    contractsQuery.error,
    workspaceQuery.error,
  ].find(Boolean);

  const referenceDataMissing = !periodsQuery.data || !peopleQuery.data || !templatesQuery.data || !contractsQuery.data;
  const versionDataMissing = Boolean(selectedVersionId) && !workspaceQuery.data;
  const loading = (referenceDataMissing || versionDataMissing) && (
    periodsQuery.isPending
    || peopleQuery.isPending
    || templatesQuery.isPending
    || contractsQuery.isPending
    || workspaceQuery.isPending
  );
  const refreshing = manualRefreshing || (
    periodsQuery.isFetching
    || peopleQuery.isFetching
    || templatesQuery.isFetching
    || contractsQuery.isFetching
    || workspaceQuery.isFetching
  );

  return {
    loading,
    refreshing,
    error: firstError ? errorMessage(firstError) : null,
    anchor,
    setAnchor,
    week,
    periods,
    selectedPeriodId,
    setSelectedPeriodId,
    versions,
    selectedVersionId,
    setSelectedVersionId,
    selectedVersion: workspaceQuery.data?.version
      || versions.find((row) => row.id === selectedVersionId)
      || null,
    assignments,
    setAssignments,
    findings: workspaceQuery.data?.findings || [],
    people,
    peopleTotal,
    peopleDepartments,
    peopleSearch,
    setPeopleSearch,
    peopleDepartmentId,
    setPeopleDepartmentId,
    peopleHasMore: Boolean(peopleQuery.hasNextPage),
    peopleLoadingMore: peopleQuery.isFetchingNextPage,
    loadMorePeople,
    templates: templatesQuery.data || [],
    contracts: contractsQuery.data || null,
    refresh,
    moveWeek: (direction) => setAnchor((value) => addWeeks(value, direction)),
  };
}
