import {
  keepPreviousData,
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { addMonths } from "date-fns";

import {
  listOfflineMutations,
  type OfflineOutboxEntry,
} from "../../../services/offlinePersistence";
import {
  getRosterContracts,
  getRosterVersion,
  listRosterAssignments,
  listRosterFindings,
  listRosterPeriods,
  listShiftTemplates,
} from "../../../services/rostering";
import {
  listRosterPeoplePage,
  type RosterDepartmentOption,
  type RosterPersonRead,
} from "../../../services/rosterPeople";
import type {
  RosterAssignmentRead,
  RosterContractResponse,
  RosterPeriodRead,
  RosterValidationFindingRead,
  RosterVersionRead,
  ShiftTemplateRead,
} from "../../../types/rostering";
import { errorMessage, monthBounds } from "../rosterUi";

export type PlannerSourceErrors = {
  periods: string | null;
  people: string | null;
  templates: string | null;
  contracts: string | null;
  workspace: string | null;
  findings: string | null;
};

export type PlannerDataV2 = {
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  sourceErrors: PlannerSourceErrors;
  anchor: Date;
  setAnchor: (date: Date) => void;
  month: ReturnType<typeof monthBounds>;
  periods: RosterPeriodRead[];
  selectedPeriodId: string;
  setSelectedPeriodId: (id: string) => void;
  versions: RosterVersionRead[];
  selectedVersionId: string;
  setSelectedVersionId: (id: string) => void;
  selectedVersion: RosterVersionRead | null;
  assignments: RosterAssignmentRead[];
  setAssignments: Dispatch<SetStateAction<RosterAssignmentRead[]>>;
  findings: RosterValidationFindingRead[];
  people: RosterPersonRead[];
  peopleTotal: number;
  peopleDepartments: RosterDepartmentOption[];
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
  retrySource: (source: keyof PlannerSourceErrors) => Promise<void>;
  moveMonth: (direction: -1 | 1) => void;
};

type VersionWorkspace = {
  version: RosterVersionRead;
  assignments: RosterAssignmentRead[];
  findings: RosterValidationFindingRead[];
  findingsError: string | null;
};

const PERIOD_STALE_MS = 2 * 60_000;
const REFERENCE_STALE_MS = 15 * 60_000;
const WORKSPACE_STALE_MS = 45_000;
const ROSTER_GC_MS = 7 * 24 * 60 * 60_000;
const PEOPLE_PAGE_SIZE = 100;
const REQUEST_TIMEOUT_MS = 20_000;
const PENDING_OUTBOX_STATUSES = new Set(["queued", "syncing", "conflict"]);
const ASSIGNMENT_PATCH_FIELDS = [
  "department_id",
  "base_station_id",
  "shift_template_id",
  "status",
  "starts_at",
  "ends_at",
  "planned_minutes",
  "role_label",
  "team_code",
  "location_label",
  "task_note",
  "change_reason",
] as const;

function newest(period?: RosterPeriodRead): RosterVersionRead | undefined {
  return [...(period?.versions || [])].sort((a, b) => b.version_no - a.version_no)[0];
}

function periodsKey(from: string, to: string) {
  return ["rostering", "planner", "periods", from, to] as const;
}

function workspaceKey(versionId: string) {
  return ["rostering", "planner", "version-workspace", versionId] as const;
}

function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = globalThis.setTimeout(() => setDebounced(value), delayMs);
    return () => globalThis.clearTimeout(timer);
  }, [delayMs, value]);
  return debounced;
}

async function withTimeout<T>(label: string, request: Promise<T>, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  let timer: ReturnType<typeof globalThis.setTimeout> | undefined;
  try {
    return await Promise.race([
      request,
      new Promise<T>((_resolve, reject) => {
        timer = globalThis.setTimeout(() => reject(new Error(`${label} did not respond within ${Math.round(timeoutMs / 1000)} seconds.`)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) globalThis.clearTimeout(timer);
  }
}

async function loadVersionWorkspace(versionId: string): Promise<VersionWorkspace> {
  const [versionResult, assignmentsResult, findingsResult] = await Promise.allSettled([
    withTimeout("Roster version", getRosterVersion(versionId)),
    withTimeout("Roster assignments", listRosterAssignments(versionId)),
    withTimeout("Roster findings", listRosterFindings(versionId, true)),
  ]);

  if (versionResult.status === "rejected") throw versionResult.reason;
  if (assignmentsResult.status === "rejected") throw assignmentsResult.reason;

  return {
    version: versionResult.value,
    assignments: assignmentsResult.value,
    findings: findingsResult.status === "fulfilled" ? findingsResult.value : [],
    findingsError: findingsResult.status === "rejected" ? errorMessage(findingsResult.reason) : null,
  };
}

function parseOutboxBody(entry: OfflineOutboxEntry): Record<string, unknown> {
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

function nullableString(value: unknown): string | null | undefined {
  if (value === null) return null;
  return typeof value === "string" ? value : undefined;
}

function assignmentIdFromPath(path: string): string | null {
  const match = path.split("?", 1)[0].match(/^\/rostering\/assignments\/([^/]+)$/);
  if (!match?.[1]) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function pendingCreateRow(
  workspace: VersionWorkspace,
  versionId: string,
  entry: OfflineOutboxEntry,
  body: Record<string, unknown>,
): RosterAssignmentRead | null {
  const userId = stringValue(body.user_id);
  const startsAt = stringValue(body.starts_at);
  const endsAt = stringValue(body.ends_at);
  if (!userId || !startsAt || !endsAt) return null;

  const timestamp = new Date(entry.createdAt).toISOString();
  const sourceReference = stringValue(body.source_reference_id) || entry.idempotencyKey;
  return {
    id: `offline-${entry.id}`,
    amo_id: workspace.version.amo_id,
    version_id: versionId,
    user_id: userId,
    department_id: nullableString(body.department_id) ?? null,
    base_station_id: nullableString(body.base_station_id) ?? null,
    shift_template_id: nullableString(body.shift_template_id) ?? null,
    status: (stringValue(body.status) || "DUTY") as RosterAssignmentRead["status"],
    source: (stringValue(body.source) || "MANUAL") as RosterAssignmentRead["source"],
    source_reference_id: sourceReference,
    starts_at: startsAt,
    ends_at: endsAt,
    planned_minutes: typeof body.planned_minutes === "number" ? body.planned_minutes : null,
    role_label: nullableString(body.role_label) ?? null,
    team_code: nullableString(body.team_code) ?? null,
    location_label: nullableString(body.location_label) ?? null,
    task_note: nullableString(body.task_note) ?? null,
    change_reason: nullableString(body.change_reason) ?? "Planner assignment",
    locked_after_publish: false,
    state_revision: 1,
    deleted_at: null,
    created_by_user_id: null,
    updated_by_user_id: null,
    created_at: timestamp,
    updated_at: timestamp,
    user_full_name: null,
    user_staff_code: null,
    user_role: null,
    department_code: null,
    department_name: null,
    base_code: null,
    base_name: null,
    shift_code: null,
    shift_label: null,
    shift_kind: null,
    linked_task_count: 0,
    linked_task_hours: 0,
  };
}

function applyPendingPatch(
  current: RosterAssignmentRead,
  previous: RosterAssignmentRead | undefined,
  entry: OfflineOutboxEntry,
  body: Record<string, unknown>,
): RosterAssignmentRead {
  const base = previous && previous.state_revision > current.state_revision ? previous : current;
  const patched: Record<string, unknown> = { ...base };
  for (const field of ASSIGNMENT_PATCH_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(body, field)) patched[field] = body[field];
  }
  const expectedRevision = typeof body.expected_state_revision === "number" ? body.expected_state_revision : current.state_revision;
  patched.state_revision = Math.max(current.state_revision + 1, expectedRevision + 1);
  patched.updated_at = new Date(entry.updatedAt).toISOString();
  return patched as unknown as RosterAssignmentRead;
}

function mergePendingRosterOutbox(
  workspace: VersionWorkspace,
  previous: VersionWorkspace | undefined,
  entries: OfflineOutboxEntry[],
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
        const restored = previousAssignments.find((row) => row.id === `offline-${entry.id}` || row.source_reference_id === sourceReference)
          || pendingCreateRow(workspace, versionId, entry, body);
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
        assignments = assignments.map((row) => row.id === assignmentId ? applyPendingPatch(row, previousRow, entry, body) : row);
      }
    });

  return { ...workspace, assignments };
}

export function useRosterPlannerDataV2(): PlannerDataV2 {
  const queryClient = useQueryClient();
  const [anchor, setAnchor] = useState(new Date());
  const month = useMemo(() => monthBounds(anchor), [anchor]);
  const [selectedPeriodId, setSelectedPeriodId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [manualRefreshing, setManualRefreshing] = useState(false);
  const [peopleSearch, setPeopleSearch] = useState("");
  const [peopleDepartmentId, setPeopleDepartmentId] = useState("");
  const debouncedPeopleSearch = useDebouncedValue(peopleSearch.trim(), 250);

  const periodsQuery = useQuery({
    queryKey: periodsKey(month.from, month.to),
    queryFn: () => withTimeout("Roster periods", listRosterPeriods({ from: month.from, to: month.to })),
    staleTime: PERIOD_STALE_MS,
    gcTime: ROSTER_GC_MS,
    placeholderData: keepPreviousData,
    networkMode: "offlineFirst",
    retry: 1,
  });

  const peopleQuery = useInfiniteQuery({
    queryKey: ["rostering", "planner", "eligible-people", month.from, month.to, debouncedPeopleSearch, peopleDepartmentId],
    queryFn: ({ pageParam }) => withTimeout("Eligible personnel", listRosterPeoplePage({
      page: pageParam,
      page_size: PEOPLE_PAGE_SIZE,
      search: debouncedPeopleSearch || null,
      department_id: peopleDepartmentId || null,
      active_only: true,
      roster_eligible_only: true,
      from: month.from,
      to: month.to,
    })),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.page + 1 : undefined,
    staleTime: REFERENCE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
    retry: 1,
  });

  const templatesQuery = useQuery({
    queryKey: ["rostering", "planner", "shift-templates", "active"],
    queryFn: () => withTimeout("Shift templates", listShiftTemplates(false)),
    staleTime: REFERENCE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
    retry: 1,
  });

  const contractsQuery = useQuery({
    queryKey: ["rostering", "planner", "contracts"],
    queryFn: () => withTimeout("Roster capability contract", getRosterContracts()),
    staleTime: REFERENCE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
    retry: 1,
  });

  const periods = useMemo(() => periodsQuery.data || [], [periodsQuery.data]);
  const selectedPeriod = periods.find((row) => row.id === selectedPeriodId);
  const versions = selectedPeriod?.versions || [];
  const peoplePages = useMemo(() => peopleQuery.data?.pages || [], [peopleQuery.data?.pages]);
  const people = useMemo(() => peoplePages.flatMap((page) => page.items), [peoplePages]);
  const peopleTotal = peoplePages[0]?.total || 0;
  const peopleDepartments = peoplePages[0]?.departments || [];

  useEffect(() => {
    if (!periods.length) {
      if (selectedPeriodId) setSelectedPeriodId("");
      return;
    }
    const current = periods.find((row) => row.id === selectedPeriodId);
    const next = current || periods.find((row) => row.starts_on <= month.to && row.ends_on >= month.from) || periods[0];
    if (next && next.id !== selectedPeriodId) setSelectedPeriodId(next.id);
  }, [month.from, month.to, periods, selectedPeriodId]);

  useEffect(() => {
    if (!selectedPeriod) {
      if (selectedVersionId) setSelectedVersionId("");
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
    retry: 1,
  });

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
      const adjacent = monthBounds(addMonths(anchor, direction));
      void queryClient.prefetchQuery({
        queryKey: periodsKey(adjacent.from, adjacent.to),
        queryFn: () => withTimeout("Adjacent roster periods", listRosterPeriods({ from: adjacent.from, to: adjacent.to })),
        staleTime: PERIOD_STALE_MS,
        gcTime: ROSTER_GC_MS,
        networkMode: "offlineFirst",
        retry: 0,
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

  const retrySource = useCallback(async (source: keyof PlannerSourceErrors) => {
    if (source === "periods") await periodsQuery.refetch();
    if (source === "people") await peopleQuery.refetch();
    if (source === "templates") await templatesQuery.refetch();
    if (source === "contracts") await contractsQuery.refetch();
    if ((source === "workspace" || source === "findings") && selectedVersionId) await workspaceQuery.refetch();
  }, [contractsQuery, peopleQuery, periodsQuery, selectedVersionId, templatesQuery, workspaceQuery]);

  const loadMorePeople = useCallback(async () => {
    if (!peopleQuery.hasNextPage || peopleQuery.isFetchingNextPage) return;
    await peopleQuery.fetchNextPage();
  }, [peopleQuery]);

  const sourceErrors: PlannerSourceErrors = {
    periods: periodsQuery.error ? errorMessage(periodsQuery.error) : null,
    people: peopleQuery.error ? errorMessage(peopleQuery.error) : null,
    templates: templatesQuery.error ? errorMessage(templatesQuery.error) : null,
    contracts: contractsQuery.error ? errorMessage(contractsQuery.error) : null,
    workspace: workspaceQuery.error ? errorMessage(workspaceQuery.error) : null,
    findings: workspaceQuery.data?.findingsError || null,
  };

  const loading = (!periodsQuery.data && periodsQuery.isPending)
    || (Boolean(selectedVersionId) && !workspaceQuery.data && workspaceQuery.isPending);
  const refreshing = manualRefreshing || periodsQuery.isFetching || workspaceQuery.isFetching;
  const blockingError = sourceErrors.periods || sourceErrors.workspace;

  return {
    loading,
    refreshing,
    error: blockingError,
    sourceErrors,
    anchor,
    setAnchor,
    month,
    periods,
    selectedPeriodId,
    setSelectedPeriodId,
    versions,
    selectedVersionId,
    setSelectedVersionId,
    selectedVersion: workspaceQuery.data?.version || versions.find((row) => row.id === selectedVersionId) || null,
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
    retrySource,
    moveMonth: (direction) => setAnchor((value) => addMonths(value, direction)),
  };
}
