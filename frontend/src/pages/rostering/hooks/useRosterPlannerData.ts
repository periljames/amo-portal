import { useCallback, useEffect, useMemo, useState } from "react";
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

export type PlannerData = {
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
  setAssignments: React.Dispatch<React.SetStateAction<RosterAssignmentRead[]>>;
  findings: RosterValidationFindingRead[];
  people: WorkforcePersonRead[];
  templates: ShiftTemplateRead[];
  contracts: RosterContractResponse | null;
  refresh: () => Promise<void>;
  moveWeek: (direction: -1 | 1) => void;
};

function latestVersion(period: RosterPeriodRead | undefined): RosterVersionRead | undefined {
  return [...(period?.versions || [])].sort((a, b) => b.version_no - a.version_no)[0];
}

export function useRosterPlannerData(): PlannerData {
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

  const loadCatalog = useCallback(async () => {
    const [periodRows, personRows, templateRows, contractRows] = await Promise.all([
      listRosterPeriods({ from: week.from, to: week.to }),
      listWorkforcePeople({ active_only: true, roster_eligible_only: true, limit: 1000 }),
      listShiftTemplates(false),
      getRosterContracts(),
    ]);
    setPeriods(periodRows);
    setPeople(personRows);
    setTemplates(templateRows);
    setContracts(contractRows);
    const preferredPeriod = periodRows.find((period) => period.id === selectedPeriodId)
      || periodRows.find((period) => period.starts_on <= week.to && period.ends_on >= week.from)
      || periodRows[0];
    const periodId = preferredPeriod?.id || "";
    setSelectedPeriodId(periodId);
    const preferredVersion = preferredPeriod?.versions.find((version) => version.id === selectedVersionId)
      || latestVersion(preferredPeriod);
    setSelectedVersionId(preferredVersion?.id || "");
  }, [selectedPeriodId, selectedVersionId, week.from, week.to]);

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

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      await loadCatalog();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setRefreshing(false);
    }
  }, [loadCatalog]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    loadCatalog()
      .catch((reason) => active && setError(errorMessage(reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [loadCatalog]);

  useEffect(() => {
    let active = true;
    loadVersion(selectedVersionId).catch((reason) => active && setError(errorMessage(reason)));
    return () => { active = false; };
  }, [loadVersion, selectedVersionId]);

  useEffect(() => {
    const period = periods.find((row) => row.id === selectedPeriodId);
    if (!period) return;
    const version = period.versions.find((row) => row.id === selectedVersionId) || latestVersion(period);
    if (version && version.id !== selectedVersionId) setSelectedVersionId(version.id);
  }, [periods, selectedPeriodId, selectedVersionId]);

  const moveWeek = useCallback((direction: -1 | 1) => {
    setAnchor((value) => addWeeks(value, direction));
  }, []);

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
    moveWeek,
  };
}
