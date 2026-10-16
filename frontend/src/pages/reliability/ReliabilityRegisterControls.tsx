import React, { useMemo, useState } from "react";
import "./ReliabilityRegisterControls.css";

type Props<T> = {
  rows: T[];
  label: string;
  queryText: (row: T) => string;
  children: (rows: T[]) => React.ReactNode;
  pageSize?: number;
};

/** Bounded rendering for already-loaded registers; never represents a partial API response as complete. */
export function ReliabilityRegisterControls<T>({ rows, label, queryText, children, pageSize = 40 }: Props<T>): React.ReactElement {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<"original" | "asc" | "desc">("original");
  const filtered = useMemo(() => {
    const needle = search.toLocaleLowerCase().trim();
    const matches = needle ? rows.filter((row) => queryText(row).toLocaleLowerCase().includes(needle)) : rows;
    if (sort === "original") return matches;
    return [...matches].sort((a, b) => queryText(a).localeCompare(queryText(b)) * (sort === "asc" ? 1 : -1));
  }, [rows, search, sort, queryText]);
  const maxPage = Math.max(0, Math.ceil(filtered.length / pageSize) - 1);
  const currentPage = Math.min(page, maxPage);
  const visible = filtered.slice(currentPage * pageSize, (currentPage + 1) * pageSize);
  return <div className="rel-register-control">
    <div className="rel-register-control__bar">
      <label>Search loaded {label} <input type="search" value={search} placeholder="Aircraft, reference, status…"
        onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label>
      <label>Order <select value={sort} onChange={(event) => { setSort(event.target.value as "original" | "asc" | "desc"); setPage(0); }}>
        <option value="original">Source order</option><option value="asc">A to Z</option><option value="desc">Z to A</option>
      </select></label>
      <span className="rel-register-control__count">{filtered.length.toLocaleString()} matching / {rows.length.toLocaleString()} loaded</span>
    </div>
    {children(visible)}
    <footer className="rel-register-control__footer">
      <span>Showing {filtered.length ? currentPage * pageSize + 1 : 0}–{Math.min((currentPage + 1) * pageSize, filtered.length)} of {filtered.length} loaded rows</span>
      <div><button type="button" disabled={currentPage === 0} onClick={() => setPage((n) => Math.max(0, n - 1))}>Previous</button>
      <span>Page {currentPage + 1} / {maxPage + 1}</span>
      <button type="button" disabled={currentPage >= maxPage} onClick={() => setPage((n) => n + 1)}>Next</button></div>
    </footer>
  </div>;
}
