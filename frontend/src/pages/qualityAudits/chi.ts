import type { QMSFindingOut } from "../../services/qms";

type TrendPoint = { label: string; score: number | null; findingCount: number };

const PENALTIES: Record<string, number> = {
  LEVEL_1: 5,
  LEVEL_2: 2,
  LEVEL_3: 0.5,
};

const scoreForFindings = (findings: QMSFindingOut[]): number => {
  const penalty = findings.reduce((sum, finding) => sum + (PENALTIES[finding.level] ?? 0), 0);
  return Math.max(0, Math.min(100, Number((100 - penalty).toFixed(1))));
};

const monthCutoff = (): Date => {
  const now = new Date();
  now.setMonth(now.getMonth() - 12);
  return now;
};

export const computeChi = (
  findingsByAudit: Array<{ auditLabel: string; findings: QMSFindingOut[]; createdAt: string | null | undefined }>
): {
  score: number | null;
  trend: TrendPoint[];
  interpretation: string;
  hasEnoughData: boolean;
} => {
  const cutoff = monthCutoff().getTime();
  const scoped = findingsByAudit
    .filter((entry) => {
      const created = entry.createdAt ? new Date(entry.createdAt).getTime() : Number.NaN;
      return Number.isFinite(created) && created >= cutoff;
    })
    .sort((a, b) => {
      const ta = a.createdAt ? new Date(a.createdAt).getTime() : 0;
      const tb = b.createdAt ? new Date(b.createdAt).getTime() : 0;
      return ta - tb;
    });

  const trend = scoped.slice(-4).map((entry) => ({
    label: entry.auditLabel,
    score: scoreForFindings(entry.findings),
    findingCount: entry.findings.length,
  }));

  if (scoped.length === 0) {
    return {
      score: null,
      trend,
      interpretation: "No audits in the last 12 months.",
      hasEnoughData: false,
    };
  }

  const weightedScore = Number(
    (
      scoped.reduce((sum, entry) => sum + scoreForFindings(entry.findings), 0) / Math.max(scoped.length, 1)
    ).toFixed(1)
  );

  const interpretation =
    weightedScore >= 90
      ? "Stable compliance posture. Keep monitoring critical findings."
      : weightedScore >= 75
      ? "Moderate exposure. Close major findings to improve CHI."
      : "High compliance risk. Immediate corrective focus recommended.";

  return {
    score: weightedScore,
    trend,
    interpretation,
    hasEnoughData: scoped.length >= 2,
  };
};
