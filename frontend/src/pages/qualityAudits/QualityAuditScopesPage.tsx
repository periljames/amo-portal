import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  CheckCircle2,
  CircleOff,
  FileKey2,
  ListFilter,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";

import Button from "../../components/UI/Button";
import { useToast } from "../../components/feedback/ToastProvider";
import { getCachedUser, getContext } from "../../services/auth";
import {
  qmsCreateAuditScope,
  qmsGetWorkflowSettings,
  qmsListAuditScopes,
  qmsUpdateAuditScope,
  qmsUpdateWorkflowSettings,
  type QMSAuditScopeOut,
} from "../../services/qms";
import {
  auditReferenceFamilyValidationError,
  auditScopeFormFromRecord,
  auditScopeUsageLabel,
  auditScopeValidationError,
  canManageAuditScopes,
  DEFAULT_AUDIT_REFERENCE_FAMILY,
  emptyAuditScopeForm,
  formatAuditReferenceExample,
  normalizeAuditReferenceFamily,
  type AuditScopeDefaultKind,
  type AuditScopeFormState,
  type AuditScopePartyLevel,
} from "./auditScopeModel";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";
import "./quality-audit-scopes.css";

type ScopeFilter = "all" | "active" | "inactive";

const PARTY_LEVELS: Array<{ value: AuditScopePartyLevel; label: string }> = [
  { value: "FIRST_PARTY", label: "1st party / internal" },
  { value: "SECOND_PARTY", label: "2nd party / supplier" },
  { value: "THIRD_PARTY", label: "3rd party / independent" },
  { value: "REGULATORY", label: "Regulatory external" },
];

const AUDIT_KINDS: Array<{ value: AuditScopeDefaultKind; label: string }> = [
  { value: "INTERNAL", label: "Internal" },
  { value: "EXTERNAL", label: "External" },
  { value: "THIRD_PARTY", label: "Third party" },
];

function humanise(value: string): string {
  return value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function scopeMatches(scope: QMSAuditScopeOut, query: string, filter: ScopeFilter): boolean {
  if (filter === "active" && !scope.is_active) return false;
  if (filter === "inactive" && scope.is_active) return false;
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [scope.code, scope.name, scope.description || "", scope.party_level, scope.default_kind]
    .join(" ")
    .toLowerCase()
    .includes(needle);
}

const QualityAuditScopesPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const context = getContext();
  const amoCode = params.amoCode ?? context.amoCode ?? "UNKNOWN";
  const currentUser = getCachedUser();
  const canManage = canManageAuditScopes(currentUser);
  const queryClient = useQueryClient();
  const { pushToast } = useToast();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ScopeFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<AuditScopeFormState | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [familyDraft, setFamilyDraft] = useState(DEFAULT_AUDIT_REFERENCE_FAMILY);
  const [familyError, setFamilyError] = useState<string | null>(null);

  const scopesQuery = useQuery({
    queryKey: ["qms-audit-scopes", amoCode, { active: "all" }],
    queryFn: () => qmsListAuditScopes(),
    staleTime: 60_000,
  });
  const workflowQuery = useQuery({
    queryKey: ["qms-workflow-settings", amoCode],
    queryFn: () => qmsGetWorkflowSettings(),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (workflowQuery.data?.audit_reference_family) {
      setFamilyDraft(normalizeAuditReferenceFamily(workflowQuery.data.audit_reference_family));
    }
  }, [workflowQuery.data?.audit_reference_family]);

  const referenceFamily = normalizeAuditReferenceFamily(
    familyDraft || workflowQuery.data?.audit_reference_family || DEFAULT_AUDIT_REFERENCE_FAMILY,
  ) || DEFAULT_AUDIT_REFERENCE_FAMILY;

  const scopes = useMemo(
    () => [...(scopesQuery.data || [])].sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code)),
    [scopesQuery.data],
  );
  const filteredScopes = useMemo(
    () => scopes.filter((scope) => scopeMatches(scope, query, filter)),
    [filter, query, scopes],
  );
  const selectedScope = filteredScopes.find((scope) => scope.id === selectedId) || filteredScopes[0] || null;
  const activeCount = scopes.filter((scope) => scope.is_active).length;
  const inactiveCount = scopes.length - activeCount;
  const exampleScopeCode = selectedScope?.code || form?.code || "SCOPE";
  const exampleSequence = selectedScope?.next_sequence ?? 1;
  const liveExample = formatAuditReferenceExample(referenceFamily, exampleScopeCode, new Date().getFullYear(), exampleSequence);

  const saveScope = useMutation({
    mutationFn: async (next: AuditScopeFormState) => {
      const validationError = auditScopeValidationError(next);
      if (validationError) throw new Error(validationError);
      const payload = {
        code: next.code.trim().toUpperCase(),
        name: next.name.trim(),
        description: next.description.trim() || null,
        party_level: next.partyLevel,
        default_kind: next.defaultKind,
        is_active: next.active,
        sort_order: Number(next.sortOrder),
      };
      return next.id ? qmsUpdateAuditScope(next.id, payload) : qmsCreateAuditScope(payload);
    },
    onSuccess: async (saved) => {
      setSelectedId(saved.id);
      setForm(null);
      setLocalError(null);
      await queryClient.invalidateQueries({ queryKey: ["qms-audit-scopes", amoCode] });
      pushToast({
        title: "Audit scope saved",
        message: `${saved.code} will govern future audit references for this tenant.`,
        variant: "success",
      });
    },
    onError: (cause) => {
      const message = cause instanceof Error ? cause.message : "The audit scope could not be saved.";
      setLocalError(message);
      pushToast({ title: "Scope not saved", message, variant: "error" });
    },
  });

  const saveFamily = useMutation({
    mutationFn: async (nextFamily: string) => {
      const validationError = auditReferenceFamilyValidationError(nextFamily);
      if (validationError) throw new Error(validationError);
      return qmsUpdateWorkflowSettings({
        audit_reference_family: normalizeAuditReferenceFamily(nextFamily),
      });
    },
    onSuccess: async (saved) => {
      setFamilyDraft(normalizeAuditReferenceFamily(saved.audit_reference_family));
      setFamilyError(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["qms-workflow-settings", amoCode] }),
        queryClient.invalidateQueries({ queryKey: ["qms-audit-scopes", amoCode] }),
      ]);
      pushToast({
        title: "Reference family updated",
        message: `Future audits will use the ${saved.audit_reference_family}/scope/year/no. pattern.`,
        variant: "success",
      });
    },
    onError: (cause) => {
      const message = cause instanceof Error ? cause.message : "The reference family could not be saved.";
      setFamilyError(message);
      pushToast({ title: "Reference family not saved", message, variant: "error" });
    },
  });

  const beginCreate = () => {
    setLocalError(null);
    setForm(emptyAuditScopeForm());
  };
  const beginEdit = (scope: QMSAuditScopeOut) => {
    setSelectedId(scope.id);
    setLocalError(null);
    setForm(auditScopeFormFromRecord(scope));
  };
  const updateForm = <K extends keyof AuditScopeFormState>(key: K, value: AuditScopeFormState[K]) => {
    setForm((current) => current ? { ...current, [key]: value } : current);
  };
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!form || !canManage) return;
    const validationError = auditScopeValidationError(form);
    setLocalError(validationError);
    if (!validationError) saveScope.mutate(form);
  };
  const submitFamily = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canManage) return;
    const validationError = auditReferenceFamilyValidationError(familyDraft);
    setFamilyError(validationError);
    if (!validationError) saveFamily.mutate(familyDraft);
  };

  const plannerHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/plan`;
  const programmeHref = `/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program`;
  const familyDirty =
    normalizeAuditReferenceFamily(familyDraft)
    !== normalizeAuditReferenceFamily(workflowQuery.data?.audit_reference_family || DEFAULT_AUDIT_REFERENCE_FAMILY);

  return (
    <QualityAuditsSectionLayout
      title="Audit scopes"
      subtitle="Govern tenant-specific reference families used by programmes, schedules and audit records."
      toolbar={(
        <div className="qa-scope-toolbar-actions">
          <Link className="btn btn--secondary btn--sm" to={plannerHref}>Schedules & runs</Link>
          <Button variant="secondary" size="sm" onClick={() => { void scopesQuery.refetch(); void workflowQuery.refetch(); }} loading={scopesQuery.isFetching || workflowQuery.isFetching}>
            <RefreshCw size={14} /> Refresh
          </Button>
        </div>
      )}
    >
      <main className="qa-scopes-page" aria-label="Audit scope administration">
        <section className="qa-scopes-summary" aria-label="Audit scope summary">
          <article><FileKey2 size={16} aria-hidden /><span>Total scopes</span><strong>{scopes.length}</strong></article>
          <article><CheckCircle2 size={16} aria-hidden /><span>Available</span><strong>{activeCount}</strong></article>
          <article><CircleOff size={16} aria-hidden /><span>Inactive</span><strong>{inactiveCount}</strong></article>
          <article><ShieldCheck size={16} aria-hidden /><span>Live example</span><strong><code>{liveExample}</code></strong></article>
        </section>

        <section className="qa-scopes-family" aria-label="Audit reference family">
          <form onSubmit={submitFamily}>
            <div>
              <span>Tenant reference family</span>
              <h2>Prefix for future audit references</h2>
              <p>Existing issued references stay immutable. Changing the family only affects newly reserved numbers.</p>
            </div>
            <label>
              <span>Family prefix</span>
              <input
                value={familyDraft}
                disabled={!canManage || saveFamily.isPending || workflowQuery.isLoading}
                onChange={(event) => {
                  setFamilyDraft(normalizeAuditReferenceFamily(event.target.value));
                  setFamilyError(null);
                }}
                maxLength={16}
                placeholder="QAR"
                aria-describedby="qa-scopes-family-help"
              />
            </label>
            <div className="qa-scopes-family__example">
              <span>Pattern</span>
              <code>{referenceFamily}/SCOPE/YY/###</code>
              <small id="qa-scopes-family-help">Example with selected scope: {liveExample}</small>
            </div>
            {canManage ? (
              <Button type="submit" size="sm" loading={saveFamily.isPending} disabled={!familyDirty || Boolean(familyError)}>
                Save family
              </Button>
            ) : (
              <small className="qa-scopes-family__readonly">Read-only — Quality Manager or AMO Admin required to change.</small>
            )}
          </form>
          {familyError ? <p className="qa-scope-form-error" role="alert">{familyError}</p> : null}
          {workflowQuery.isError ? (
            <p className="qa-scope-form-error" role="alert">
              {workflowQuery.error instanceof Error ? workflowQuery.error.message : "Workflow settings unavailable."}
            </p>
          ) : null}
        </section>

        {!canManage ? (
          <section className="qa-scopes-access-note" role="note">
            <ShieldCheck size={18} aria-hidden />
            <div><strong>Read-only scope catalogue</strong><span>Only an AMO Admin or Quality Manager can create, rename, reorder, activate or deactivate audit scopes.</span></div>
          </section>
        ) : null}

        <section className="qa-scopes-workspace">
          <div className="qa-scopes-catalogue">
            <header>
              <div><span>Tenant catalogue</span><h2>Reference units</h2></div>
              {canManage ? <Button size="sm" onClick={beginCreate}><Plus size={15} /> New scope</Button> : null}
            </header>
            <div className="qa-scopes-filters">
              <label><Search size={15} aria-hidden /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search code, name or party level" /></label>
              <label><ListFilter size={15} aria-hidden /><select value={filter} onChange={(event) => setFilter(event.target.value as ScopeFilter)}><option value="all">All scopes</option><option value="active">Available</option><option value="inactive">Inactive</option></select></label>
            </div>

            {scopesQuery.isLoading ? (
              <div className="qa-scopes-state" role="status"><RefreshCw className="is-spinning" size={22} /><strong>Loading tenant scopes…</strong></div>
            ) : scopesQuery.isError ? (
              <div className="qa-scopes-state qa-scopes-state--error" role="alert"><strong>Audit scopes are unavailable.</strong><span>{scopesQuery.error instanceof Error ? scopesQuery.error.message : "Try again."}</span><Button variant="secondary" size="sm" onClick={() => void scopesQuery.refetch()}>Retry</Button></div>
            ) : filteredScopes.length ? (
              <div className="qa-scopes-table" role="table" aria-label="Audit scope catalogue">
                <div className="qa-scopes-table__head" role="row">
                  <span role="columnheader">Code</span>
                  <span role="columnheader">Name</span>
                  <span role="columnheader">This year</span>
                  <span role="columnheader">Status</span>
                </div>
                {filteredScopes.map((scope) => (
                  <button
                    key={scope.id}
                    type="button"
                    role="row"
                    className={`qa-scopes-table__row${selectedScope?.id === scope.id ? " is-selected" : ""}${scope.is_active ? "" : " is-inactive"}`}
                    onClick={() => { setSelectedId(scope.id); setForm(null); setLocalError(null); }}
                  >
                    <span className="qa-scopes-table__code" role="cell">{scope.code}</span>
                    <span className="qa-scopes-table__copy" role="cell">
                      <strong>{scope.name}</strong>
                      <small>{humanise(scope.party_level)} · {humanise(scope.default_kind)}</small>
                    </span>
                    <span className="qa-scopes-table__usage" role="cell">{auditScopeUsageLabel(scope)}</span>
                    <span className={`qa-scopes-table__status${scope.is_active ? " is-active" : ""}`} role="cell">
                      {scope.is_active ? "Available" : "Inactive"}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="qa-scopes-state"><strong>No audit scopes match this view.</strong><span>Clear the search or choose another availability filter.</span></div>
            )}
          </div>

          <aside className="qa-scopes-detail" aria-label={form ? "Audit scope editor" : "Selected audit scope"}>
            {form ? (
              <form onSubmit={submit}>
                <header><div><span>{form.id ? "Edit reference unit" : "Create reference unit"}</span><h2>{form.id ? form.code || "Audit scope" : "New audit scope"}</h2></div></header>
                <div className="qa-scope-form-grid">
                  <label><span>Scope code</span><input value={form.code} onChange={(event) => updateForm("code", event.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 16))} placeholder="AC" autoFocus /><small>2–16 letters or numbers; used in future {referenceFamily} references.</small></label>
                  <label><span>Scope name</span><input value={form.name} onChange={(event) => updateForm("name", event.target.value)} placeholder="Aircraft audit" /></label>
                  <label><span>Party level</span><select value={form.partyLevel} onChange={(event) => updateForm("partyLevel", event.target.value as AuditScopePartyLevel)}>{PARTY_LEVELS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
                  <label><span>Default audit type</span><select value={form.defaultKind} onChange={(event) => updateForm("defaultKind", event.target.value as AuditScopeDefaultKind)}>{AUDIT_KINDS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
                  <label><span>Sort order</span><input type="number" min={0} max={9999} step={1} value={form.sortOrder} onChange={(event) => updateForm("sortOrder", event.target.value)} /></label>
                  <label className="qa-scope-form-grid__availability"><input type="checkbox" checked={form.active} onChange={(event) => updateForm("active", event.target.checked)} /><span><strong>Available for new audits</strong><small>Deactivate instead of deleting so historical references remain valid.</small></span></label>
                  <label className="qa-scope-form-grid__wide"><span>Description</span><textarea rows={4} value={form.description} onChange={(event) => updateForm("description", event.target.value)} placeholder="Processes, approvals or operational areas covered by this reference unit" /></label>
                </div>
                {localError ? <p className="qa-scope-form-error" role="alert">{localError}</p> : null}
                <footer><Button type="button" variant="secondary" onClick={() => { setForm(null); setLocalError(null); }}>Cancel</Button><Button type="submit" loading={saveScope.isPending}>Save scope</Button></footer>
              </form>
            ) : selectedScope ? (
              <div className="qa-scope-detail-card">
                <header>
                  <div>
                    <span>Selected reference unit</span>
                    <h2>{selectedScope.code} · {selectedScope.name}</h2>
                  </div>
                  {canManage ? <Button variant="secondary" size="sm" onClick={() => beginEdit(selectedScope)}><Pencil size={14} /> Edit</Button> : null}
                </header>
                <dl>
                  <div><dt>Status</dt><dd>{selectedScope.is_active ? "Available for new audits" : "Inactive — historical use only"}</dd></div>
                  <div><dt>Party level</dt><dd>{humanise(selectedScope.party_level)}</dd></div>
                  <div><dt>Default audit type</dt><dd>{humanise(selectedScope.default_kind)}</dd></div>
                  <div><dt>Sort order</dt><dd>{selectedScope.sort_order}</dd></div>
                  <div><dt>Issued this year</dt><dd>{selectedScope.issued_this_year ?? 0}</dd></div>
                  <div><dt>Next reference</dt><dd><code>{formatAuditReferenceExample(referenceFamily, selectedScope.code, new Date().getFullYear(), selectedScope.next_sequence ?? 1)}</code></dd></div>
                  <div><dt>Counter last value</dt><dd>{selectedScope.last_value ?? 0}</dd></div>
                  <div><dt>Description</dt><dd>{selectedScope.description || "No description recorded."}</dd></div>
                </dl>
                <p>Existing audit references are immutable. Changes apply only when future schedules and audits resolve this scope.</p>
              </div>
            ) : scopes.length ? (
              <div className="qa-scopes-state"><ListFilter size={24} /><strong>No scope is selected in this view.</strong><span>Clear the catalogue filters or select a visible reference unit.</span></div>
            ) : (
              <div className="qa-scopes-state"><FileKey2 size={24} /><strong>No audit scope is configured.</strong><span>{canManage ? "Create the first tenant scope before scheduling an audit." : "An AMO Admin or Quality Manager must create the first scope."}</span>{canManage ? <Button size="sm" onClick={beginCreate}><Plus size={15} /> New scope</Button> : null}<Link to={programmeHref}>Open audit programme</Link></div>
            )}
          </aside>
        </section>
      </main>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditScopesPage;
