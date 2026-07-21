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

function newest(period?: RosterPeriodRead): RosterVersionRead | undefined {
  return [...(period?.versions || [])].sort((a, b) => b.version_no - a.version_no)[0];
}

export function useRosterPlannerDataV2(): PlannerDataV2 {
  const [anchor, setAnchor] = useState(new Date());
  const week = useMemo(() => weekBounds(anchor), [anchor]);
  const [periods, setPeriods] = useState<RosterPeriodRead[]>([]);
  const [selectedPeriodId, setSelectedPeriodId] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [selectedVersion, setSelectedVersion] = useState<RosterVersionRead | null>(null);
  const [assignments, setAssignments] = useState<RosterAssignmentRead[]>([]);
  const [findings, setFindings] = useState<RosterValidationFindingRead[]>([]);
  const [people, setPeople] = useState<WorkforcePersonRead[]>([]);
  const [templates, setTemplates] = useState<ShiftTemplateRead[]>([]);
  const [contracts, setContracts] = useState<RosterContractResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadVersion = useCallback(async (versionId: string) => {
    if (!versionId) {
      setSelectedVersion(null);
      setAssignments([]);
      setFindings([]);
      return;
    }
    const [version, assignmentRows, findingRows] = await Promise.all([
      getRosterVersion(versionId),
      listRosterAssignments(versionId),
      listRosterFindings(versionId, true),
    ]);
    setSelectedVersion(version);
    setAssignments(assignmentRows);
    setFindings(findingRows);
  }, []);

  const loadAll = useCallback(async (forceVersionId?: string) => {
    const [periodRows, personRows, templateRows, capabilityRows] = await Promise.all([
      listRosterPeriods({ from: week.from, to: week.to }),
      listWorkforcePeople({ active_only: true, roster_eligible_only: true, limit: 1000 }),
      listShiftTemplates(false),
      getRosterContracts(),
    ]);
    setPeriods(periodRows);
    setPeople(personRows);
    setTemplates(templateRows);
    setContracts(capabilityRows);

    const period = periodRows.find((row) => row.id === selectedPeriodId)
      || periodRows.find((row) => row.starts_on <= week.to && row.ends_on >= week.from)
      || periodRows[0];
    const periodId = period?.id || "";
    setSelectedPeriodId(periodId);
    const version = period?.versions.find((row) => row.id === (forceVersionId || selectedVersionId)) || newest(period);
    const versionId = version?.id || "";
    setSelectedVersionId(versionId);
    await loadVersion(versionId);
  }, [loadVersion, selectedPeriodId, selectedVersionId, week.from, week.to]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      await loadAll(selectedVersionId);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setRefreshing(false);
    }
  }, [loadAll, selectedVersionId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    loadAll()
      .catch((reason) => { if (active) setError(errorMessage(reason)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loadAll]);

  useEffect(() => {
    const period = periods.find((row) => row.id === selectedPeriodId);
    if (!period) return;
    const version = period.versions.find((row) => row.id === selectedVersionId) || newest(period);
    if (version && version.id !== selectedVersionId) setSelectedVersionId(version.id);
  }, [periods, selectedPeriodId, selectedVersionId]);

  useEffect(() => {
    if (!selectedVersionId) return;
    void loadVersion(selectedVersionId).catch((reason) => setError(errorMessage(reason)));
  }, [loadVersion, selectedVersionId]);

  return {
    loading,
    refreshing,
    error,
    anchor,
    setAnchor,
    week,
    periods,
    selectedPeriodId,
    setSelectedPeriodId,
    versions: periods.find((row) => row.id === selectedPeriodId)?.versions || [],
    selectedVersionId,
    setSelectedVersionId,
    selectedVersion,
    assignments,
    setAssignments,
    findings,
    people,
    templates,
    contracts,
    refresh,
    moveWeek: (direction) => setAnchor((value) => addWeeks(value, direction)),
  };
}
