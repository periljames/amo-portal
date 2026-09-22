import type { QmsPrivilegeRule } from "../../services/qmsPeople";

/** Default Lead/Auditor competence package codes (mirror backend people_default_rules). */
export const DEFAULT_QMS_COMPETENCE_CODES = ["QMS-INIT", "QMS-REF", "QMS-ADMIN"] as const;

export type TrainingRuleJoin = "AND" | "OR";

export type QmsCompetencePackage = {
  /** Selected course codes that participate in the rule. */
  codes: string[];
  /** Default join when expression is empty. Always AND unless the user opts into OR / advanced. */
  join: TrainingRuleJoin;
  /** Optional freeform rule using words AND / OR (and parentheses). */
  expression: string | null;
  /** Legacy OR currency list — still read for older saved rules. */
  currency_any_of: string[];
  /** Legacy tracked admin (not a hard gate in old packages). */
  tracked_admin: string | null;
};

type ScopeSchema = Record<string, unknown> & {
  supervised_development?: boolean;
  allowed_assignment_roles?: string[];
  qms_competence?: {
    codes?: string[];
    join?: string;
    expression?: string | null;
    currency_any_of?: string[];
    tracked_admin?: string | null;
  };
};

const AUTHORIZE_DUE_SOON_DAYS = 60;
const INIT_SUFFIXES = ["INITIAL", "INIT"] as const;
const REF_SUFFIXES = ["REFRESHER", "RECURRENT", "REFRESH", "REF"] as const;

export function compactCourseToken(value: unknown): string {
  return String(value || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "");
}

export function normalizeCourseCode(value: unknown): string {
  return String(value || "").trim().toUpperCase();
}

export function uniqueCourseCodes(codes: Iterable<string>): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of codes) {
    const code = normalizeCourseCode(raw);
    if (!code || seen.has(code)) continue;
    seen.add(code);
    out.push(code);
  }
  return out;
}

export function courseCodesMatch(left: string, right: string): boolean {
  const a = normalizeCourseCode(left);
  const b = normalizeCourseCode(right);
  if (!a || !b) return false;
  if (a === b) return true;
  return compactCourseToken(a) === compactCourseToken(b);
}

export function courseCodeSelected(courseId: string, selected: string[]): boolean {
  return selected.some((code) => courseCodesMatch(code, courseId));
}

export type CoursePairKind = "INIT" | "REF";

export function coursePairKind(code: string): CoursePairKind | null {
  const token = compactCourseToken(code);
  if (!token) return null;
  for (const suffix of INIT_SUFFIXES) {
    if (token.endsWith(suffix) && token.length > suffix.length) return "INIT";
  }
  for (const suffix of REF_SUFFIXES) {
    if (token.endsWith(suffix) && token.length > suffix.length) return "REF";
  }
  return null;
}

export function coursePairFamily(code: string): string {
  const token = compactCourseToken(code);
  for (const suffix of [...INIT_SUFFIXES, ...REF_SUFFIXES]) {
    if (token.endsWith(suffix) && token.length > suffix.length) {
      return token.slice(0, -suffix.length);
    }
  }
  return token;
}

function synthesizeCounterpart(code: string, want: CoursePairKind): string {
  const normalized = normalizeCourseCode(code);
  const kind = coursePairKind(normalized);
  if (!kind) return normalized;
  const separators = ["-", "_", " ", ""];
  for (const sep of separators) {
    for (const suffix of kind === "INIT" ? INIT_SUFFIXES : REF_SUFFIXES) {
      const needle = `${sep}${suffix}`;
      const upper = normalized.toUpperCase();
      const idx = upper.lastIndexOf(needle);
      if (idx > 0) {
        const stem = normalized.slice(0, idx);
        const join = sep || "-";
        return `${stem}${join}${want === "INIT" ? "INIT" : "REF"}`;
      }
    }
  }
  const family = coursePairFamily(normalized);
  return `${family}-${want === "INIT" ? "INIT" : "REF"}`;
}

/** Resolve the INIT↔REF counterpart for a course, preferring catalogue matches. */
export function resolveCourseCounterpart(
  code: string,
  catalogueCodes: Iterable<string> = [],
): string | null {
  const kind = coursePairKind(code);
  if (!kind) return null;
  const want: CoursePairKind = kind === "INIT" ? "REF" : "INIT";
  const family = coursePairFamily(code);
  const catalogue = uniqueCourseCodes(catalogueCodes);
  const fromCatalogue = catalogue.find(
    (entry) => coursePairFamily(entry) === family && coursePairKind(entry) === want,
  );
  if (fromCatalogue) return fromCatalogue;
  return synthesizeCounterpart(code, want);
}

export type TrainingSelectionResult = {
  codes: string[];
  /** Human notice when a counterpart was auto-added or pair was cleared together. */
  notice: string | null;
};

/**
 * Toggle a training code while keeping INIT/REF counterparts paired.
 * Selecting one side auto-selects the other; clearing one side clears both.
 */
export function toggleTrainingSelectionWithPairs(
  current: string[],
  courseId: string,
  catalogueCodes: Iterable<string> = [],
): TrainingSelectionResult {
  const normalized = normalizeCourseCode(courseId);
  if (!normalized) return { codes: uniqueCourseCodes(current), notice: null };

  const counterpart = resolveCourseCounterpart(normalized, catalogueCodes);
  const selected = uniqueCourseCodes(current);

  if (courseCodeSelected(normalized, selected)) {
    const without = selected.filter(
      (code) =>
        !courseCodesMatch(code, normalized)
        && !(counterpart && courseCodesMatch(code, counterpart)),
    );
    if (counterpart && courseCodeSelected(counterpart, selected)) {
      return {
        codes: without,
        notice: `Removed ${normalized} and ${counterpart} together — initial and refresher courses stay paired.`,
      };
    }
    return { codes: without, notice: null };
  }

  const next = uniqueCourseCodes([...selected, normalized]);
  if (counterpart && !courseCodeSelected(counterpart, next)) {
    return {
      codes: uniqueCourseCodes([...next, counterpart]),
      notice: `Also selected ${counterpart} — initial and refresher courses cannot be configured alone.`,
    };
  }
  return { codes: next, notice: null };
}

export function formatTrainingRuleSummary(
  codes: Iterable<string>,
  join: TrainingRuleJoin = "AND",
): string {
  const list = uniqueCourseCodes(codes);
  if (!list.length) return "No training required";
  if (list.length === 1) return list[0];
  return list.join(` ${join} `);
}

export function normalizeTrainingExpression(value: string): string {
  return String(value || "")
    .replace(/\s+/g, " ")
    .replace(/\s*([()])\s*/g, " $1 ")
    .replace(/\b&&\b/g, " AND ")
    .replace(/\b\|\|\b/g, " OR ")
    .replace(/\s+/g, " ")
    .trim();
}

export function defaultTrainingExpression(
  codes: Iterable<string>,
  join: TrainingRuleJoin = "AND",
): string {
  const summary = formatTrainingRuleSummary(codes, join);
  return summary === "No training required" ? "" : summary;
}

export type TrainingExpressionParse =
  | { ok: true; codes: string[]; join: TrainingRuleJoin; ast: ExprNode }
  | { ok: false; error: string };

type ExprNode =
  | { type: "code"; code: string }
  | { type: "and" | "or"; left: ExprNode; right: ExprNode };

function tokenizeExpression(raw: string): string[] | null {
  const normalized = normalizeTrainingExpression(raw).toUpperCase();
  if (!normalized) return [];
  const tokens: string[] = [];
  let cursor = 0;
  while (cursor < normalized.length) {
    while (cursor < normalized.length && /\s/.test(normalized[cursor])) cursor += 1;
    if (cursor >= normalized.length) break;
    const ch = normalized[cursor];
    if (ch === "(" || ch === ")") {
      tokens.push(ch);
      cursor += 1;
      continue;
    }
    if (normalized.startsWith("AND", cursor) && (cursor + 3 >= normalized.length || /[\s()]/.test(normalized[cursor + 3]))) {
      tokens.push("AND");
      cursor += 3;
      continue;
    }
    if (normalized.startsWith("OR", cursor) && (cursor + 2 >= normalized.length || /[\s()]/.test(normalized[cursor + 2]))) {
      tokens.push("OR");
      cursor += 2;
      continue;
    }
    let end = cursor;
    while (end < normalized.length && /[A-Z0-9._\-/]/.test(normalized[end])) end += 1;
    if (end === cursor) return null;
    tokens.push(normalizeCourseCode(normalized.slice(cursor, end)));
    cursor = end;
  }
  return tokens;
}

function parseExpressionTokens(tokens: string[]): ExprNode | null {
  let index = 0;

  function peek(): string | undefined {
    return tokens[index];
  }

  function consume(expected?: string): string | undefined {
    const token = tokens[index];
    if (expected && token !== expected) return undefined;
    if (token === undefined) return undefined;
    index += 1;
    return token;
  }

  function parsePrimary(): ExprNode | null {
    const token = peek();
    if (!token) return null;
    if (token === "(") {
      consume("(");
      const inner = parseOr();
      if (!inner || consume(")") !== ")") return null;
      return inner;
    }
    if (token === "AND" || token === "OR" || token === ")") return null;
    consume();
    return { type: "code", code: normalizeCourseCode(token) };
  }

  function parseAnd(): ExprNode | null {
    let left = parsePrimary();
    if (!left) return null;
    while (peek() === "AND") {
      consume("AND");
      const right = parsePrimary();
      if (!right) return null;
      left = { type: "and", left, right };
    }
    return left;
  }

  function parseOr(): ExprNode | null {
    let left = parseAnd();
    if (!left) return null;
    while (peek() === "OR") {
      consume("OR");
      const right = parseAnd();
      if (!right) return null;
      left = { type: "or", left, right };
    }
    return left;
  }

  const ast = parseOr();
  if (!ast || index !== tokens.length) return null;
  return ast;
}

function collectExpressionCodes(node: ExprNode, out: string[] = []): string[] {
  if (node.type === "code") {
    out.push(node.code);
    return out;
  }
  collectExpressionCodes(node.left, out);
  collectExpressionCodes(node.right, out);
  return out;
}

function expressionUsesOr(node: ExprNode): boolean {
  if (node.type === "or") return true;
  if (node.type === "code") return false;
  return expressionUsesOr(node.left) || expressionUsesOr(node.right);
}

export function parseTrainingExpression(value: string): TrainingExpressionParse {
  const tokens = tokenizeExpression(value);
  if (tokens === null) {
    return { ok: false, error: "Use course codes with AND / OR (and parentheses if needed)." };
  }
  if (!tokens.length) {
    return {
      ok: true,
      codes: [],
      join: "AND",
      ast: { type: "code", code: "" },
    };
  }
  const ast = parseExpressionTokens(tokens);
  if (!ast) {
    return { ok: false, error: "Could not read that rule. Example: QMS-INIT AND QMS-REF AND QMS-ADMIN" };
  }
  if (ast.type === "code" && !ast.code) {
    return { ok: true, codes: [], join: "AND", ast };
  }
  return {
    ok: true,
    codes: uniqueCourseCodes(collectExpressionCodes(ast)),
    join: expressionUsesOr(ast) ? "OR" : "AND",
    ast,
  };
}

export function evaluateTrainingExpression(
  expression: string,
  satisfiedCodes: Iterable<string>,
): boolean {
  const parsed = parseTrainingExpression(expression);
  if (!parsed.ok) return false;
  if (!parsed.codes.length) return true;
  const satisfied = uniqueCourseCodes(satisfiedCodes);

  function evalNode(node: ExprNode): boolean {
    if (node.type === "code") {
      if (!node.code) return true;
      return satisfied.some((code) => courseCodesMatch(code, node.code));
    }
    if (node.type === "and") return evalNode(node.left) && evalNode(node.right);
    return evalNode(node.left) || evalNode(node.right);
  }

  return evalNode(parsed.ast);
}

export function resolveRuleCompetencePackage(
  rule: Pick<QmsPrivilegeRule, "scope_schema"> | null | undefined,
): QmsCompetencePackage | null {
  const scope = (rule?.scope_schema || {}) as ScopeSchema;
  const packageRaw = scope.qms_competence;
  if (!packageRaw || typeof packageRaw !== "object") return null;

  const expressionRaw = typeof packageRaw.expression === "string" ? packageRaw.expression.trim() : "";
  const expression = expressionRaw ? normalizeTrainingExpression(expressionRaw) : null;
  const joinRaw = String(packageRaw.join || "").trim().toUpperCase();
  const join: TrainingRuleJoin = joinRaw === "OR" ? "OR" : "AND";

  const legacyCurrency = uniqueCourseCodes(packageRaw.currency_any_of || []);
  const tracked = normalizeCourseCode(packageRaw.tracked_admin) || null;
  const explicitCodes = uniqueCourseCodes(packageRaw.codes || []);

  let codes = explicitCodes;
  if (!codes.length && expression) {
    const parsed = parseTrainingExpression(expression);
    if (parsed.ok) codes = parsed.codes;
  }
  if (!codes.length) {
    codes = uniqueCourseCodes([...legacyCurrency, ...(tracked ? [tracked] : [])]);
  }
  if (!codes.length && !expression && !legacyCurrency.length && !tracked) return null;

  let resolvedJoin: TrainingRuleJoin = join;
  if (expression) {
    const parsed = parseTrainingExpression(expression);
    if (parsed.ok) resolvedJoin = parsed.join;
  } else if (!packageRaw.join && !packageRaw.codes && legacyCurrency.length) {
    // Legacy currency_any_of packages were OR between INIT/REF.
    resolvedJoin = "OR";
  }

  return {
    codes,
    join: resolvedJoin,
    expression,
    currency_any_of: legacyCurrency,
    tracked_admin: tracked,
  };
}

/** Codes shown/edited in the rule form — competence package ∪ legacy required list. */
export function ruleConfiguredTrainingCodes(
  rule: Pick<QmsPrivilegeRule, "required_training_course_codes" | "scope_schema"> | null | undefined,
): string[] {
  if (!rule) return [];
  const packageCodes = resolveRuleCompetencePackage(rule);
  return uniqueCourseCodes([
    ...(packageCodes?.codes || []),
    ...(rule.required_training_course_codes || []),
  ]);
}

export function ruleTrainingExpressionFromRule(
  rule: Pick<QmsPrivilegeRule, "required_training_course_codes" | "scope_schema"> | null | undefined,
): string {
  const packageCodes = resolveRuleCompetencePackage(rule);
  if (packageCodes?.expression) return packageCodes.expression;
  if (packageCodes?.codes.length) {
    return defaultTrainingExpression(packageCodes.codes, packageCodes.join);
  }
  const legacy = uniqueCourseCodes(rule?.required_training_course_codes || []);
  return defaultTrainingExpression(legacy, "AND");
}

export function ruleUsesCompetencePackage(
  rule: Pick<QmsPrivilegeRule, "privilege_type" | "scope_schema"> | null | undefined,
  supervisedDevelopment: boolean,
): boolean {
  if (!rule) return false;
  if (supervisedDevelopment) return false;
  if (resolveRuleCompetencePackage(rule)) return true;
  return rule.privilege_type === "LEAD_AUDITOR" || rule.privilege_type === "AUDITOR";
}

/**
 * Rebuild scope_schema for create/edit rule saves.
 * Selected trainings persist as an AND rule by default (expression optional for Advanced).
 */
export function buildPrivilegeRuleScopeSchema(options: {
  privilegeType: QmsPrivilegeRule["privilege_type"];
  supervisedDevelopment: boolean;
  selectedTrainingCodes: string[];
  join?: TrainingRuleJoin;
  expression?: string | null;
  previousScope?: Record<string, unknown> | null;
}): Record<string, unknown> {
  const previous = { ...(options.previousScope || {}) } as ScopeSchema;
  const selected = uniqueCourseCodes(options.selectedTrainingCodes);
  const previousPackage = resolveRuleCompetencePackage({ scope_schema: previous });
  const join: TrainingRuleJoin = options.join === "OR" ? "OR" : "AND";
  const expressionInput = options.expression != null
    ? normalizeTrainingExpression(options.expression)
    : "";
  const expression = expressionInput || null;

  if (options.privilegeType === "AUDITOR" && options.supervisedDevelopment) {
    const next: ScopeSchema = { ...previous };
    delete next.qms_competence;
    next.supervised_development = true;
    next.allowed_assignment_roles = ["OBSERVER_AUDITOR", "ASSISTANT_AUDITOR"];
    return next;
  }

  const next: ScopeSchema = { ...previous };
  delete next.supervised_development;
  delete next.allowed_assignment_roles;

  const shouldWritePackage =
    Boolean(previousPackage)
    || options.privilegeType === "LEAD_AUDITOR"
    || options.privilegeType === "AUDITOR"
    || selected.length > 0
    || Boolean(expression);

  if (!shouldWritePackage) {
    delete next.qms_competence;
    return next;
  }

  const codesFromExpression = expression ? parseTrainingExpression(expression) : null;
  const codes = codesFromExpression?.ok && codesFromExpression.codes.length
    ? codesFromExpression.codes
    : selected;
  const resolvedJoin = codesFromExpression?.ok ? codesFromExpression.join : join;
  const resolvedExpression = expression || defaultTrainingExpression(codes, resolvedJoin) || null;

  next.qms_competence = {
    codes,
    join: resolvedJoin,
    expression: resolvedExpression,
    // Keep legacy mirrors for older readers during rollout.
    currency_any_of: codes.filter((code) => coursePairKind(code) === "INIT" || coursePairKind(code) === "REF"),
    tracked_admin: codes.find((code) => compactCourseToken(code).endsWith("ADMIN")) || null,
  };
  return next;
}

/** required_training_course_codes payload: empty for competence-package rules. */
export function ruleRequiredTrainingPayload(options: {
  usesCompetencePackage: boolean;
  selectedTrainingCodes: string[];
}): string[] {
  if (options.usesCompetencePackage) return [];
  return uniqueCourseCodes(options.selectedTrainingCodes);
}

export function defaultTrainingCodesForPrivilegeType(
  type: QmsPrivilegeRule["privilege_type"],
  supervisedDevelopment = false,
): string[] {
  if (supervisedDevelopment) return [];
  if (type === "LEAD_AUDITOR" || type === "AUDITOR") {
    return [...DEFAULT_QMS_COMPETENCE_CODES];
  }
  return [];
}

export function defaultCompetenceScopeForPrivilegeType(
  type: QmsPrivilegeRule["privilege_type"],
): Record<string, unknown> {
  if (type !== "LEAD_AUDITOR" && type !== "AUDITOR") return {};
  const codes = [...DEFAULT_QMS_COMPETENCE_CODES];
  return {
    qms_competence: {
      codes,
      join: "AND",
      expression: defaultTrainingExpression(codes, "AND"),
      currency_any_of: ["QMS-INIT", "QMS-REF"],
      tracked_admin: "QMS-ADMIN",
    },
  };
}

export function authorizeValidityLabel(options: {
  validUntil?: string | null;
  matchReasons?: string[] | null;
  asOf?: Date;
}): { text: string; dueSoon: boolean; scheduledOnly: boolean } {
  const reasons = (options.matchReasons || []).map((reason) => String(reason || "").toUpperCase());
  const hasRecord = reasons.includes("RECORD");
  const hasScheduled = reasons.includes("SCHEDULED");
  const until = options.validUntil ? String(options.validUntil).slice(0, 10) : "";
  if (until) {
    const expiry = new Date(`${until}T00:00:00`);
    if (!Number.isNaN(expiry.getTime())) {
      const today = options.asOf ? new Date(options.asOf) : new Date();
      today.setHours(0, 0, 0, 0);
      const days = Math.round((expiry.getTime() - today.getTime()) / 86400000);
      const formatted = expiry.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
      return {
        text: `Valid until: ${formatted}`,
        dueSoon: days >= 0 && days < AUTHORIZE_DUE_SOON_DAYS,
        scheduledOnly: false,
      };
    }
  }
  if (hasScheduled && !hasRecord) {
    return { text: "Scheduled", dueSoon: false, scheduledOnly: true };
  }
  if (hasRecord) {
    return { text: "Valid until: not set", dueSoon: false, scheduledOnly: false };
  }
  return { text: "", dueSoon: false, scheduledOnly: false };
}
