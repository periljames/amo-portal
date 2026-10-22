import { useMemo, useState } from "react";
import type { CarRcaDocument, CarRcaInvestigation, CarRcaMethod, CarRcaNode, CauseEntryType, CarRcaEffectivenessProposal } from "../../../services/qmsCarRca";

const METHOD_GUIDE: Array<{ id: CarRcaMethod; title: string; description: string }> = [
  { id: "FIVE_WHYS", title: "5 Whys", description: "Explore why each condition occurred. You can branch and use more than five questions." },
  { id: "ISHIKAWA", title: "Fishbone", description: "Sort possible causes by people, process, equipment, materials, management and environment." },
  { id: "PARETO", title: "Pareto", description: "Compare documented frequencies. Frequency alone does not prove a root cause." },
  { id: "CAUSAL_FACTOR", title: "Cause map", description: "Map linked conditions, direct causes and systemic contributing factors." },
  { id: "BARRIER_ANALYSIS", title: "Barrier analysis", description: "Identify missing or ineffective safeguards and the evidence for each." },
  { id: "CHANGE_ANALYSIS", title: "Change analysis", description: "Compare what changed in people, materials, procedures or operating conditions." },
  { id: "HUMAN_ORGANIZATIONAL", title: "Human/organisational", description: "Examine workload, supervision, communication, training and system factors without assigning blame." },
  { id: "EIGHT_D", title: "8D", description: "Record each of the eight disciplines of team-based problem solving." },
  { id: "FMEA", title: "FMEA", description: "Assess prospective failure modes and risk-priority numbers, not proof of actual causation." },
];
const CATEGORIES = ["People", "Process", "Equipment", "Materials", "Environment", "Management", "Measurement"];
const D_STAGES = ["D1 Team", "D2 Problem", "D3 Containment", "D4 Root cause", "D5 Permanent action", "D6 Implementation", "D7 Recurrence prevention", "D8 Recognition"];
const EVIDENCE_TYPES: { value: CauseEntryType; label: string }[] = [
  { value: "HYPOTHESIS", label: "Hypothesis — not verified" },
  { value: "FACT", label: "Recorded fact — verify the source" },
  { value: "CAUSAL_CONCLUSION", label: "Evidence-supported proposed cause" },
  { value: "RULED_OUT", label: "Ruled-out factor" },
];
const nextId = () => typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `rca-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const blankNode = (category: string, parent_id: string | null = null): CarRcaNode => ({
  id: nextId(), parent_id, statement: "", category, entry_type: "HYPOTHESIS",
  evidence_references: [], rationale: "",
});
const paths = (nodes: CarRcaNode[], parent_id: string | null = null, depth = 0): Array<{ node: CarRcaNode; depth: number }> =>
  nodes.filter(node => node.parent_id === parent_id).flatMap(node => [
    { node, depth },
    ...paths(nodes, node.id, depth + 1),
  ]);
const csv = (text: string) => text.split("\n").map(s => s.trim()).filter(Boolean);
const labelFor = (id: CarRcaMethod) => METHOD_GUIDE.find(m => m.id === id)?.title || id;
const valueOf = (value: unknown) => typeof value === "string" ? value : "";
const countOf = (value: unknown) => Number.isFinite(Number(value)) ? Math.max(0, Math.floor(Number(value))) : 0;

export default function CarRcaWorkbench({ value, disabled, onChange, onSave, saveState }: {
  value: CarRcaDocument;
  disabled: boolean;
  onChange: (next: CarRcaDocument) => void;
  onSave: () => void;
  saveState: string;
}) {
  const [selected, setSelected] = useState<CarRcaMethod>("FIVE_WHYS");
  const [category, setCategory] = useState("Process");
  const [parentId, setParentId] = useState("");
  const [statement, setStatement] = useState("");
  const [kind, setKind] = useState<CauseEntryType>("HYPOTHESIS");
  const [evidence, setEvidence] = useState("");
  const [rationale, setRationale] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [paretoCategory, setParetoCategory] = useState("");
  const [paretoCount, setParetoCount] = useState("1");
  const [paretoSource, setParetoSource] = useState("");
  const [paretoFrom, setParetoFrom] = useState("");
  const [paretoTo, setParetoTo] = useState("");
  const [paretoPopulation, setParetoPopulation] = useState("");
  const [scoreS, setScoreS] = useState(5);
  const [scoreO, setScoreO] = useState(5);
  const [scoreD, setScoreD] = useState(5);

  const current = value.investigations.find(item => item.method === selected);
  const nodes = current?.nodes ?? [];
  const ordered = useMemo(() => paths(nodes), [nodes]);
  const updateMethod = (next: CarRcaInvestigation) => {
    onChange({
      ...value,
      investigations: current
        ? value.investigations.map(item => item.id === current.id ? next : item)
        : [...value.investigations, next],
    });
  };
  const createMethod = () => current ?? { id: nextId(), method: selected, version: 1, nodes: [], context: {} } as CarRcaInvestigation;
  const selectMethod = (method: CarRcaMethod) => {
    setSelected(method); setEditingId(null); setStatement(""); setParentId("");
    setCategory(method === "EIGHT_D" ? D_STAGES[0] : "Process");
  };
  const changeContext = (patch: Record<string, unknown>) => {
    const base = createMethod();
    updateMethod({ ...base, context: { ...base.context, ...patch } });
  };
  const startEdit = (node: CarRcaNode) => {
    setEditingId(node.id);
    setParentId(node.parent_id ?? "");
    setStatement(node.statement); setCategory(node.category);
    setKind(node.entry_type); setEvidence(node.evidence_references.join("\n"));
    setRationale(node.rationale);
  };
  const resetEdit = () => {
    setEditingId(null); setParentId(""); setStatement(""); setKind("HYPOTHESIS");
    setEvidence(""); setRationale("");
  };
  const persistNode = () => {
    if (statement.trim().length < 2) return;
    const base = createMethod();
    const updated: CarRcaNode = {
      ...(editingId ? (nodes.find(node => node.id === editingId) ?? blankNode(category)) : blankNode(category)),
      parent_id: parentId || null, statement: statement.trim(), category,
      entry_type: kind, evidence_references: csv(evidence), rationale: rationale.trim(),
    };
    if (updated.entry_type === "CAUSAL_CONCLUSION" && !updated.evidence_references.length) return;
    updateMethod({ ...base, nodes: editingId
      ? base.nodes.map(node => node.id === editingId ? updated : node)
      : [...base.nodes, updated] });
    resetEdit();
  };
  const deleteNode = (id: string) => {
    if (!window.confirm("Remove this draft cause and its descendants? Revision history will retain earlier saved versions.")) return;
    const ids = new Set([id]);
    let changed = true;
    while (changed) {
      changed = false;
      nodes.forEach(node => { if (node.parent_id && ids.has(node.parent_id) && !ids.has(node.id)) { ids.add(node.id); changed = true; } });
    }
    if (ids.has(editingId ?? "")) resetEdit();
    const trimmed = nodes.filter(node => !ids.has(node.id));
    const next = { ...createMethod(), nodes: trimmed };
    onChange({
      ...value, supported_cause_ids: value.supported_cause_ids.filter(cause => !ids.has(cause)),
      investigations: current
        ? value.investigations.map(method => method.id === current.id ? next : method)
        : [...value.investigations, next],
    });
  };

  const pareto = (Array.isArray(current?.context?.frequencies) ? current.context.frequencies : []) as Array<{ category: string; count: number; source_ref: string }>;
  const orderedPareto = [...pareto].sort((a, b) => b.count - a.count || a.category.localeCompare(b.category));
  const total = orderedPareto.reduce((n, item) => n + countOf(item.count), 0);
  let cum = 0;
  const cumulative = orderedPareto.map(item => {
    cum += countOf(item.count);
    return { ...item, count: countOf(item.count), percentage: total ? Math.round(cum / total * 10000) / 100 : 0 };
  });
  const causes = nodes.filter(item => item.entry_type !== "RULED_OUT");
  const fishboneGroups = [...new Set([...CATEGORIES, ...causes.map(node => node.category)])]
    .filter(group => causes.some(node => node.category === group));
  const supported = value.investigations.flatMap(item => item.nodes)
    .filter(node => node.entry_type === "CAUSAL_CONCLUSION" && node.evidence_references.length > 0);
  const proposal: CarRcaEffectivenessProposal = value.effectiveness_proposal || {
    expected_result: "", measurable_success_criterion: "", verification_method: "",
    observation_period: "", proposed_review_date: null, supporting_records: [],
  };
  const patchProposal = (patch: Partial<CarRcaEffectivenessProposal>) =>
    onChange({ ...value, effectiveness_proposal: { ...proposal, ...patch } });

  return <section className="car-rca" aria-label="Root cause investigation">
    <div className="car-rca-heading">
      <div><h4>Root cause workbench</h4><p>Choose a method. Record observations, explore possible causes and submit only evidence-backed conclusions.</p></div>
      <div className="car-rca-save"><span role="status">{saveState}</span><button type="button" onClick={onSave} disabled={disabled}>Save investigation</button></div>
    </div>
    <label className="car-rca-field">Problem statement from this CAR
      <textarea rows={2} value={value.problem_statement} onChange={e => onChange({ ...value, problem_statement: e.target.value })} disabled={disabled} maxLength={8000} />
    </label>
    <div className="car-rca-methods" aria-label="Investigation methods">
      {METHOD_GUIDE.map(item =>
        <button type="button" key={item.id} aria-pressed={selected === item.id} className={selected === item.id ? "is-selected" : ""}
          onClick={() => selectMethod(item.id)}>{item.title}{value.investigations.some(m => m.method === item.id) ? " •" : ""}</button>
      )}
    </div>
    <p className="car-rca-note">{METHOD_GUIDE.find(m => m.id === selected)?.description}</p>

    {selected === "ISHIKAWA" && <div className="car-rca-fishbone">
      <div className="car-rca-diagram-controls">
        <strong>Editable cause-and-effect diagram</strong>
        <button type="button" onClick={() => setZoom(z => Math.max(.65, z - .15))}>−</button>
        <span>{Math.round(zoom * 100)}%</span>
        <button type="button" onClick={() => setZoom(z => Math.min(2, z + .15))}>+</button>
        <button type="button" onClick={() => setZoom(1)}>Fit</button>
        <button type="button" onClick={() => window.print()}>Print</button>
      </div>
      <div className="car-rca-diagram-scroller" tabIndex={0} aria-label="Scroll the Fishbone diagram">
        <svg role="img" aria-label={`Fishbone diagram with ${causes.length} recorded causes`} width={1000 * zoom} height={460 * zoom} viewBox="0 0 1000 460">
          <line x1={85} y1={235} x2={770} y2={235} stroke="currentColor" strokeWidth={4} />
          <path d="M770 195 L950 195 L950 275 L770 275 Z" stroke="currentColor" fill="none" strokeWidth={2} />
          <text x={860} y={226} textAnchor="middle" fontSize={14} fill="currentColor">Finding</text>
          <text x={860} y={247} textAnchor="middle" fontSize={11} fill="currentColor">{value.problem_statement.slice(0, 24) || "Problem"}</text>
          {fishboneGroups.slice(0, 10).map((branch, index) => {
            const x = 145 + Math.floor(index / 2) * 125;
            const upper = index % 2 === 0;
            const y = upper ? 55 : 415;
            const sub = causes.filter(cause => cause.category === branch).slice(0, 4);
            return <g key={branch}>
              <line x1={x} y1={235} x2={x - 58} y2={y} stroke="currentColor" strokeWidth={2} />
              <text x={x - 55} y={upper ? y - 12 : y + 12} fill="currentColor" fontSize={14} fontWeight={600}>{branch}</text>
              {sub.map((cause, i) => <g key={cause.id}>
                <line x1={x - 13 - i * 12} y1={235 - (235 - y) * (i + 1) / 5} x2={x + 38 - i * 12} y2={235 - (235 - y) * (i + 1) / 5} stroke="currentColor" />
                <text x={x + 42 - i * 12} y={238 - (235 - y) * (i + 1) / 5} fill="currentColor" fontSize={10}>
                  {cause.statement.slice(0, 21)}{cause.entry_type === "CAUSAL_CONCLUSION" ? " *" : " ?"}
                </text>
              </g>)}
            </g>;
          })}
        </svg>
      </div>
      <p>Question mark = candidate or hypothesis; asterisk = evidence-linked proposed conclusion. The Quality reviewer must independently accept any causal conclusion. All diagram entries are editable below.</p>
    </div>}

    {selected === "PARETO" ? <div className="car-rca-analysis">
      <div className="car-rca-grid">
        <label>Analysis population<input value={paretoPopulation || valueOf(current?.context.population)} onChange={e => setParetoPopulation(e.target.value)} disabled={disabled} placeholder="e.g. audit nonconformities in reviewed sample" /></label>
        <label>Period from<input type="date" value={paretoFrom || valueOf(current?.context.period_from)} onChange={e => setParetoFrom(e.target.value)} disabled={disabled} /></label>
        <label>Period to<input type="date" value={paretoTo || valueOf(current?.context.period_to)} onChange={e => setParetoTo(e.target.value)} disabled={disabled} /></label>
      </div>
      <button type="button" disabled={disabled || !(paretoPopulation || current?.context.population)}
        onClick={() => changeContext({ population: paretoPopulation || current?.context.population, period_from: paretoFrom || current?.context.period_from, period_to: paretoTo || current?.context.period_to })}>
        Save source scope</button>
      <p className="car-rca-note">These are respondent-entered source counts, not an independently verified QMS dataset. Enter a traceable source for each category. Quality must validate underlying records before reliance.</p>
      <div className="car-rca-grid">
        <label>Category<input value={paretoCategory} onChange={e => setParetoCategory(e.target.value)} disabled={disabled}/></label>
        <label>Occurrences<input type="number" min={1} max={1000000} value={paretoCount} onChange={e => setParetoCount(e.target.value)} disabled={disabled}/></label>
        <label>Evidence or record reference<input value={paretoSource} onChange={e => setParetoSource(e.target.value)} disabled={disabled}/></label>
        <button type="button" disabled={disabled || !paretoCategory.trim() || !paretoSource.trim() || !Number.isInteger(Number(paretoCount)) || Number(paretoCount) < 1}
          onClick={() => { changeContext({ frequencies: [...pareto, { category: paretoCategory.trim(), count: Number(paretoCount), source_ref: paretoSource.trim() }] }); setParetoCategory(""); setParetoSource(""); }}>Add frequency</button>
      </div>
      {total > 0 ? <>
        <svg className="car-rca-pareto" viewBox="0 0 650 240" role="img" aria-label={`Pareto chart, ${total} total events`}>
          {cumulative.slice(0, 15).map((row, i, list) => <g key={i}>
            <rect x={35 + i * (580 / list.length)} y={210 - row.count / Math.max(...list.map(x => x.count)) * 160}
              width={Math.max(8, 580 / list.length - 10)} height={row.count / Math.max(...list.map(x => x.count)) * 160} fill="currentColor" opacity=".35" />
            <circle cx={35 + (i + .5) * (580 / list.length)} cy={210 - row.percentage * 1.6} r={4} fill="currentColor" />
            <text x={35 + i * (580 / list.length)} y={228} fill="currentColor" fontSize={9}>{row.category.slice(0, 9)}</text>
          </g>)}
          <polyline points={cumulative.slice(0, 15).map((x, i, list) => `${35 + (i + .5) * (580 / list.length)},${210 - x.percentage * 1.6}`).join(" ")} stroke="currentColor" strokeWidth={2} fill="none" />
          <text x={4} y={20} fontSize={12} fill="currentColor">100%</text>
        </svg>
        <div className="car-rca-table-scroll"><table><caption>Frequency and cumulative percentages — total {total}</caption>
          <thead><tr><th>Category</th><th>Count</th><th>Cumulative %</th><th>Source</th><th>Action</th></tr></thead>
          <tbody>{cumulative.map((row, i) => <tr key={i}><td>{row.category}</td><td>{row.count}</td><td>{row.percentage}%</td><td>{row.source_ref}</td><td><button type="button" disabled={disabled} onClick={() => changeContext({ frequencies: pareto.filter(item => item !== row && !(item.category === row.category && item.count === row.count && item.source_ref === row.source_ref)) })}>Remove</button></td></tr>)}</tbody></table></div>
      </> : <p>No documented occurrences have been entered. A Pareto conclusion cannot be calculated without observations.</p>}
    </div> : <div className="car-rca-analysis">
      {selected === "FMEA" && <div className="car-rca-grid">
        <label>Severity (1–10)<input type="number" min={1} max={10} value={scoreS} disabled={disabled} onChange={e => setScoreS(Math.min(10, Math.max(1, Number(e.target.value))))}/></label>
        <label>Occurrence (1–10)<input type="number" min={1} max={10} value={scoreO} disabled={disabled} onChange={e => setScoreO(Math.min(10, Math.max(1, Number(e.target.value))))}/></label>
        <label>Detection difficulty (1–10)<input type="number" min={1} max={10} value={scoreD} disabled={disabled} onChange={e => setScoreD(Math.min(10, Math.max(1, Number(e.target.value))))}/></label>
        <p>Provisional RPN = {scoreS * scoreO * scoreD}. This prioritizes prospective risk; it does not verify root cause.</p>
        <button type="button" disabled={disabled} onClick={() => changeContext({ severity: scoreS, occurrence: scoreO, detection: scoreD, rpn: scoreS * scoreO * scoreD })}>Save FMEA scoring basis</button>
      </div>}
      <div className="car-rca-table-scroll"><table>
        <caption>{labelFor(selected)} causal entries — {nodes.length}</caption>
        <thead><tr><th>Entry</th><th>Classification</th><th>Evidence</th><th>Modify</th></tr></thead>
        <tbody>{(selected === "FIVE_WHYS" || selected === "CAUSAL_FACTOR" ? ordered : nodes.map(node => ({ node, depth: 0 }))).map(({ node, depth }) =>
          <tr key={node.id}><td style={{ paddingLeft: `${Math.min(6, depth) * 12 + 10}px` }}>{selected === "FIVE_WHYS" ? `Why ${depth + 1}:` : node.category} {node.statement}</td>
            <td>{node.entry_type.replaceAll("_", " ")}</td><td>{node.evidence_references.length} references</td>
            <td><button type="button" disabled={disabled} onClick={() => startEdit(node)}>Edit</button>
              <button type="button" disabled={disabled} onClick={() => deleteNode(node.id)}>Delete</button></td></tr>
        )}</tbody></table></div>
      {!nodes.length && <p>No causal entries yet. Start with a possible cause and link evidence as facts become available.</p>}
      <div className="car-rca-grid">
        <label>{selected === "EIGHT_D" ? "Discipline" : "Theme / branch"}
          {selected === "EIGHT_D" ?
            <select value={category} onChange={e => setCategory(e.target.value)} disabled={disabled}>{D_STAGES.map(x => <option key={x}>{x}</option>)}</select> :
            <input list="rca-cause-branches" value={category} onChange={e => setCategory(e.target.value)} disabled={disabled} />}
          <datalist id="rca-cause-branches">{CATEGORIES.map(x => <option key={x} value={x}/>)}</datalist>
        </label>
        {(selected === "FIVE_WHYS" || selected === "CAUSAL_FACTOR" || selected === "ISHIKAWA") && <label>Caused by / preceding question
          <select value={parentId} onChange={e => setParentId(e.target.value)} disabled={disabled}>
            <option value="">Problem statement / main branch</option>
            {nodes.filter(node => node.id !== editingId).map(node => <option key={node.id} value={node.id}>{node.statement.slice(0, 90)}</option>)}
          </select>
        </label>}
        <label>Evidence classification
          <select value={kind} onChange={e => setKind(e.target.value as CauseEntryType)} disabled={disabled}>
            {EVIDENCE_TYPES.map(x => <option key={x.value} value={x.value}>{x.label}</option>)}
          </select>
        </label>
      </div>
      <label className="car-rca-field">{selected === "FIVE_WHYS" ? "Why did the preceding condition occur?" : selected === "BARRIER_ANALYSIS" ? "Which safeguard failed or was missing?" : selected === "CHANGE_ANALYSIS" ? "What changed, compared with the previous state?" : selected === "HUMAN_ORGANIZATIONAL" ? "Which work-system factor contributed?" : selected === "FMEA" ? "Failure mode and effect" : "Causal observation / explanation"}
        <textarea value={statement} onChange={e => setStatement(e.target.value)} disabled={disabled} rows={3} maxLength={4000} />
      </label>
      <label className="car-rca-field">Evidence references (one record per line)
        <textarea value={evidence} onChange={e => setEvidence(e.target.value)} disabled={disabled} rows={2} placeholder="Attachment name, controlled record ID, interview record..." />
      </label>
      <label className="car-rca-field">Evidence interpretation / why this cause is supported
        <textarea value={rationale} onChange={e => setRationale(e.target.value)} disabled={disabled} rows={2} maxLength={4000}/>
      </label>
      {kind === "CAUSAL_CONCLUSION" && !csv(evidence).length && <p role="alert">Record supporting evidence before classifying an entry as a proposed causal conclusion.</p>}
      <div className="car-rca-row">
        <button type="button" disabled={disabled || statement.trim().length < 2 || (kind === "CAUSAL_CONCLUSION" && !csv(evidence).length)}
          onClick={persistNode}>{editingId ? "Save edited cause" : "Add cause / analysis entry"}</button>
        {editingId && <button type="button" onClick={resetEdit}>Cancel edit</button>}
      </div>
    </div>}

    <div className="car-rca-conclusions">
      <h4>Consolidated root-cause conclusion</h4>
      <p>Separate hypotheses from supported causes. The Quality department will independently review these proposed conclusions.</p>
      {supported.length === 0 && <p>No evidence-linked proposed causes are available yet.</p>}
      {supported.map(node => <label key={node.id} className="car-rca-check">
        <input type="checkbox" disabled={disabled} checked={value.supported_cause_ids.includes(node.id)}
          onChange={e => onChange({ ...value, supported_cause_ids: e.target.checked ? [...value.supported_cause_ids, node.id] : value.supported_cause_ids.filter(id => id !== node.id) })}/>
        {node.statement} ({node.evidence_references.length} references)
      </label>)}
      <label className="car-rca-field">Final root cause explanation
        <textarea value={value.conclusion} disabled={disabled} rows={4} maxLength={8000}
          onChange={e => onChange({ ...value, conclusion: e.target.value })} />
      </label>
      <label className="car-rca-field">Evidence supporting the consolidated conclusion (one per line)
        <textarea value={value.conclusion_evidence_references.join("\n")} disabled={disabled} rows={2}
          onChange={e => onChange({ ...value, conclusion_evidence_references: csv(e.target.value) })}/>
      </label>
      <p className="car-rca-note">Submission requires a supported causal entry and evidence references. An approved RCA is distinct from corrective-action implementation and effectiveness verification.</p>
    </div>
    <section className="car-rca-conclusions" aria-label="Proposed effectiveness verification">
      <h4>Propose an effectiveness check</h4>
      <p>Suggest how Quality can check that the solution prevents recurrence. This is a proposal only; the responsible Quality reviewer independently sets and concludes the formal plan.</p>
      <div className="car-rca-grid">
        <label>Expected result<textarea rows={2} value={proposal.expected_result} maxLength={8000} disabled={disabled} onChange={e => patchProposal({ expected_result: e.target.value })}/></label>
        <label>Measurable success criterion<textarea rows={2} value={proposal.measurable_success_criterion} maxLength={8000} disabled={disabled} onChange={e => patchProposal({ measurable_success_criterion: e.target.value })}/></label>
        <label>Verification method<textarea rows={2} value={proposal.verification_method} maxLength={8000} disabled={disabled} onChange={e => patchProposal({ verification_method: e.target.value })}/></label>
        <label>Observation period<input value={proposal.observation_period} maxLength={255} disabled={disabled} onChange={e => patchProposal({ observation_period: e.target.value })} placeholder="e.g. next three scheduled inspections"/></label>
        <label>Proposed independent review date<input type="date" value={proposal.proposed_review_date || ""} disabled={disabled} onChange={e => patchProposal({ proposed_review_date: e.target.value || null })}/></label>
      </div>
      <label className="car-rca-field">Proposed supporting records (one per line)
        <textarea rows={2} value={proposal.supporting_records.join("\n")} disabled={disabled}
          onChange={e => patchProposal({ supporting_records: csv(e.target.value) })}/></label>
      {!disabled && value.effectiveness_proposal && <button type="button" onClick={() => onChange({ ...value, effectiveness_proposal: null })}>Clear proposal</button>}
    </section>
  </section>;
}
