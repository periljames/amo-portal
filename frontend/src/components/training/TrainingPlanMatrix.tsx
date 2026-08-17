import React, { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Copy, Loader2, Search, UsersRound } from "lucide-react";

import Drawer from "../shared/Drawer";
import { getTrainingPlanMatrix, getTrainingPlanMatrixCell } from "../../services/trainingOperating";
import type { TrainingPlanMatrixCell, TrainingPlanMatrixCourse, TrainingPlanMatrixPersonPage } from "../../types/trainingOperating";

type Props = { planId: string; planYear: number };
type SelectedCell = { course: TrainingPlanMatrixCourse; cell: TrainingPlanMatrixCell };

const PAGE_SIZE = 20;
const PERSON_PAGE_SIZE = 100;

function monthLabel(month: number, long = false): string {
  return new Date(2000, month - 1, 1).toLocaleString(undefined, { month: long ? "long" : "short" });
}

const TrainingPlanMatrix: React.FC<Props> = ({ planId, planYear }) => {
  const [offset, setOffset] = useState(0);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("ALL");
  const [page, setPage] = useState<Awaited<ReturnType<typeof getTrainingPlanMatrix>> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedCell | null>(null);
  const [drawerCell, setDrawerCell] = useState<SelectedCell | null>(null);
  const [peoplePage, setPeoplePage] = useState<TrainingPlanMatrixPersonPage | null>(null);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [copyState, setCopyState] = useState("Copy list");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getTrainingPlanMatrix(planId, { search, training_kind: kind === "ALL" ? undefined : kind, limit: PAGE_SIZE, offset, preview_limit: 5 })
      .then((result) => { if (active) setPage(result); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "The plan matrix could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [kind, offset, planId, search]);

  useEffect(() => {
    if (!drawerCell) { setPeoplePage(null); return; }
    let active = true;
    setPeopleLoading(true);
    getTrainingPlanMatrixCell(planId, drawerCell.course.course_key, drawerCell.cell.month, PERSON_PAGE_SIZE, 0)
      .then((result) => { if (active) setPeoplePage(result); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Personnel could not be loaded."); })
      .finally(() => { if (active) setPeopleLoading(false); });
    return () => { active = false; };
  }, [drawerCell, planId]);

  const kindPills = useMemo(() => ["ALL", ...Object.keys(page?.kind_counts || {}).sort()], [page?.kind_counts]);

  const copyPeople = async () => {
    if (!drawerCell || !peoplePage) return;
    setCopyState("Preparing…");
    try {
      let items = [...peoplePage.items];
      let nextOffset = items.length;
      while (nextOffset < peoplePage.total) {
        const next = await getTrainingPlanMatrixCell(planId, drawerCell.course.course_key, drawerCell.cell.month, 500, nextOffset);
        items = [...items, ...next.items];
        nextOffset += next.items.length;
        if (!next.items.length) break;
      }
      setPeoplePage({ ...peoplePage, items, offset: 0, has_more: items.length < peoplePage.total });
      await navigator.clipboard.writeText(items.map((person) => `${person.person_name}\t${person.staff_code || person.user_id}\t${person.planned_due_date || ""}`).join("\n"));
      setCopyState("Copied");
      window.setTimeout(() => setCopyState("Copy list"), 1600);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The personnel list could not be copied.");
      setCopyState("Copy list");
    }
  };

  const loadMorePeople = async () => {
    if (!drawerCell || !peoplePage?.has_more) return;
    setPeopleLoading(true);
    try {
      const next = await getTrainingPlanMatrixCell(planId, drawerCell.course.course_key, drawerCell.cell.month, PERSON_PAGE_SIZE, peoplePage.offset + peoplePage.items.length);
      setPeoplePage({ ...next, items: [...peoplePage.items, ...next.items], offset: 0 });
    } finally { setPeopleLoading(false); }
  };

  return (
    <section className="tos-card tos-plan-matrix-card">
      <div className="tos-section-heading">
        <div><h2>Course-by-month plan</h2><p>Rows are governed courses; month cells show unique personnel due for enrolment.</p></div>
        <span className="tos-quiet-metric">{page?.total ?? 0} courses · {planYear}</span>
      </div>
      <div className="tos-plan-matrix-toolbar">
        <form onSubmit={(event) => { event.preventDefault(); setOffset(0); setSearch(searchInput.trim()); }}>
          <Search size={16} /><input value={searchInput} onChange={(event) => setSearchInput(event.target.value)} placeholder="Search course" aria-label="Search plan courses" />
        </form>
        <div className="tos-pill-row" aria-label="Training kind filter">
          {kindPills.map((item) => <button key={item} type="button" className={kind === item ? "is-active" : ""} onClick={() => { setKind(item); setOffset(0); }}>{item.replaceAll("_", " ")} {item === "ALL" ? page?.total ?? 0 : page?.kind_counts[item] ?? 0}</button>)}
        </div>
      </div>
      {error ? <div className="tos-banner tos-banner--error">{error}<button onClick={() => setError(null)}>×</button></div> : null}
      <p className="tos-plan-matrix-legend"><strong>Values</strong> = unique personnel due / planned</p>
      <div className="tos-plan-matrix-scroll">
        <table className="tos-plan-matrix">
          <thead><tr><th>Course</th>{Array.from({ length: 12 }, (_, index) => <th key={index}>{monthLabel(index + 1)}</th>)}</tr></thead>
          <tbody>
            {(page?.items || []).map((course) => <tr key={course.course_key}>
              <th scope="row"><strong>{course.course_code || "COURSE"}</strong><span>{course.course_name}</span><small>{course.training_kind.replaceAll("_", " ")} · Total {course.personnel_count}</small></th>
              {course.cells.map((cell) => {
                const isSelected = selected?.course.course_key === course.course_key && selected.cell.month === cell.month;
                const label = `${cell.personnel_count} personnel due or planned for ${course.course_name} in ${monthLabel(cell.month, true)} ${planYear}`;
                return <td key={cell.month} className={isSelected ? "is-selected" : ""}>
                  {cell.personnel_count ? <button className="tos-plan-cell" type="button" aria-label={label} aria-expanded={isSelected} onClick={() => setSelected(isSelected ? null : { course, cell })}><strong>{cell.personnel_count}</strong></button> : <span className="tos-plan-cell--empty" aria-label={`No personnel due or planned for ${course.course_name} in ${monthLabel(cell.month, true)} ${planYear}`}>—</span>}
                  {isSelected ? <div className="tos-plan-cell-preview">{cell.preview.map((person) => <span key={person.user_id} title={person.staff_code || person.user_id}>{person.person_name}</span>)}{cell.personnel_count > 5 ? <button type="button" onClick={() => setDrawerCell({ course, cell })}>+ More ({cell.personnel_count - 5})</button> : null}</div> : null}
                </td>;
              })}
            </tr>)}
            {loading ? <tr><td colSpan={13}><Loader2 className="tos-spin" size={18} /> Loading monthly plan…</td></tr> : null}
            {!loading && !page?.items.length ? <tr><td colSpan={13}>No courses match the current plan filters.</td></tr> : null}
          </tbody>
        </table>
      </div>
      {page ? <div className="tos-pagination"><span>{page.total ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, page.total)} of ${page.total} courses` : "0 courses"}</span><button className="tos-icon-button" aria-label="Previous course page" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={18} /></button><button className="tos-icon-button" aria-label="Next course page" disabled={!page.has_more || loading} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={18} /></button></div> : null}

      <Drawer title={drawerCell ? `${drawerCell.course.course_code || "Course"} · ${monthLabel(drawerCell.cell.month, true)} personnel` : "Planned personnel"} isOpen={Boolean(drawerCell)} onClose={() => setDrawerCell(null)} panelClassName="training-form-drawer">
        <div className="tos-drawer-form">
          <div className="tos-section-heading"><div><h3>{drawerCell?.course.course_name}</h3><p>{peoplePage?.total ?? drawerCell?.cell.personnel_count ?? 0} unique personnel due for enrolment.</p></div><button disabled={!peoplePage?.items.length || copyState === "Preparing…"} onClick={() => void copyPeople()}><Copy size={16} /> {copyState}</button></div>
          {peopleLoading && !peoplePage ? <div className="tos-empty"><Loader2 className="tos-spin" size={22} /><span>Loading personnel…</span></div> : null}
          <div className="tos-copy-columns">{peoplePage?.items.map((person, index) => <div key={person.user_id}><span>{index + 1}</span><strong>{person.person_name}</strong><small>{person.staff_code || person.user_id}{person.planned_due_date ? ` · due ${person.planned_due_date}` : ""}</small></div>)}</div>
          {peoplePage?.has_more ? <button disabled={peopleLoading} onClick={() => void loadMorePeople()}><UsersRound size={16} /> Load next {Math.min(PERSON_PAGE_SIZE, peoplePage.total - peoplePage.items.length)}</button> : null}
        </div>
      </Drawer>
    </section>
  );
};

export default TrainingPlanMatrix;
