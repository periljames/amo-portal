import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { addWeeks } from "date-fns";

import {
  getRosterContracts,
  getRosterVersion,
  listRosterAssignments,
  listRosterFindings,
  listRosterPeriods,
  listShiftTemplates,
} from "../../../services/rostering";
import { listWorkforcePeople, type WorkforcePersonRead } from "../../../services/workforce";
import type {
  RosterAssignmentRead,
  RosterContractResponse,
  RosterPeriodRead,
  RosterValidationFindingRead,
  RosterVersionRead,
  ShiftTemplateRead,
} from "../../../types/rostering";
import { errorMessage, weekBounds } from "../rosterUi";

export type PlannerDataV2 = {
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  anchor: Date;
  setAnchor: (date: Date) => void;
  week: ReturnType<typeof weekBounds>;
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
  people: WorkforcePersonRead[];
  templates: ShiftTemplateRead[];
  contracts: RosterContractResponse | null;
  refresh: () => Promise<void>;
  moveWeek: (direction: -1 | 1) => void;
};

type VersionWorkspace = {
  version: RosterVersionRead;
  assignments: RosterAssignmentRead[];
  findings: RosterValidationFindingRead[];
};

const PERIOD_STALE_MS = 2 * 60_000;
const REFERENCE_STALE_MS = 15 * 60_000;
const WORKSPACE_STALE_MS = 45_000;
const ROSTER_GC_MS = 7 * 24 * 60 * 60_000;

function newest(period?: RosterPeriodRead): RosterVersionRead | undefined {
  return [...(period?.versions || [])].sort((a, b) => b.version_no - a.version_no)[0];
}

function periodsKey(from: string, to: string) {
  return ["rostering", "planner", "periods", from, to] as const;
}

async function loadVersionWorkspace(versionId: string): Promise<VersionWorkspace> {
  const [version, assignments, findings] = await Promise.all([
    getRosterVersion(versionId),
    listRosterAssignments(versionId),
    listRosterFindings(versionId, true),
  ]);
  return { version, assignments, findings };
}

export function useRosterPlannerDataV2(): PlannerDataV2 {
  const queryClient = useQueryClient();
  const [anchor, setAnchor] = useState(new Date());
  const week = useMemo(() => weekBounds(anchor), [anchor]);
  const [selectedPeriodId, setSelectedPeriodId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [assignments, setAssignments] = useState<RosterAssignmentRead[]>([]);
  const [manualRefreshing, setManualRefreshing] = useState(false);

  const periodsQuery = useQuery({
    queryKey: periodsKey(week.from, week.to),
    queryFn: () => listRosterPeriods({ from: week.from, to: week.to }),
    staleTime: PERIOD_STALE_MS,
    gcTime: ROSTER_GC_MS,
    placeholderData: keepPreviousData,
    networkMode: "offlineFirst",
  });

  const peopleQuery = useQuery({
    queryKey: ["rostering", "planner", "eligible-people"],
    queryFn: () => listWorkforcePeople({ active_only: true, roster_eligible_only: true, limit: 1000 }),
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
    queryKey: ["rostering", "planner", "version-workspace", selectedVersionId],
    queryFn: () => loadVersionWorkspace(selectedVersionId),
    enabled: Boolean(selectedVersionId),
    staleTime: WORKSPACE_STALE_MS,
    gcTime: ROSTER_GC_MS,
    networkMode: "offlineFirst",
  });

  useEffect(() => {
    if (workspaceQuery.data?.assignments) {
      setAssignments(workspaceQuery.data.assignments);
    } else if (!selectedVersionId) {
      setAssignments([]);
    }
  }, [selectedVersionId, workspaceQuery.data]);

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
    people: peopleQuery.data || [],
    templates: templatesQuery.data || [],
    contracts: contractsQuery.data || null,
    refresh,
    moveWeek: (direction) => setAnchor((value) => addWeeks(value, direction)),
  };
}
