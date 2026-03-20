import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ClipboardList, ShieldAlert, TableProperties } from "lucide-react";
import SpreadsheetToolbar from "../../components/shared/SpreadsheetToolbar";
import { ResponsiveSegmentedControl } from "../../components/qms/ResponsiveSegmentedControl";
import { useDensityPreference } from "../../hooks/useDensityPreference";
import { getContext } from "../../services/auth";
import { qmsGetAuditRegister, type CAROut, type QMSAuditOut, type QMSFindingOut } from "../../services/qms";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";

type RegisterTab = "findings" | "cars";

type Props = {
  defaultTab: RegisterTab;
};

type RegisterRow = {
  audit: QMSAuditOut;
  finding: QMSFindingOut;
  linkedCars: CAROut[];
};

const QualityAuditRegisterPage: React.FC<Props> = ({ defaultTab }) => {
  const [tab, setTab] = useState<RegisterTab>(defaultTab);
  const [wrapText, setWrapText] = useState(false);
  const [showFilters, setShowFilters] = useState(true);
  const [showOwner, setShowOwner] = useState(true);
  const [quickFilter, setQuickFilter] = useState("");
  const [headerFilters, setHeaderFilters] = useState({
    ref: "",
    finding: "",
    audit: "",
    type: "",
    owner: "",
    car: "",
  });
  const { density, setDensity } = useDensityPreference("audit-register", "compact");

  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();

  const registerQuery = useQuery({
    queryKey: ["qms-audit-register", amoCode],
    queryFn: () => qmsGetAuditRegister({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const rows = useMemo<RegisterRow[]>(() => {
    return (registerQuery.data?.rows ?? []).map((row) => ({
      audit: row.audit,
      finding: row.finding,
      linkedCars: row.linked_cars,
    }));
  }, [registerQuery.data]);

  const filteredRows = useMemo(() => {
    const q = quickFilter.trim().toLowerCase();
    return rows.filter(({ audit, finding, linkedCars }) => {
      if (tab === "cars" && linkedCars.length === 0) return false;
      const haystack = [
        audit.audit_ref,
        audit.title,
        finding.finding_ref || finding.id,
        finding.description,
        finding.finding_type,
        finding.acknowledged_by_name || "",
        ...linkedCars.map((car) => `${car.car_number} ${car.title} ${car.summary}`),
      ]
        .join(" ")
        .toLowerCase();

      if (q && !haystack.includes(q)) return false;
      if (headerFilters.ref && !(finding.finding_ref || finding.id).toLowerCase().includes(headerFilters.ref.toLowerCase())) return false;
      if (headerFilters.finding && !finding.description.toLowerCase().includes(headerFilters.finding.toLowerCase())) return false;
      if (headerFilters.audit && !`${audit.audit_ref} ${audit.title}`.toLowerCase().includes(headerFilters.audit.toLowerCase())) return false;
      if (headerFilters.type && !finding.finding_type.toLowerCase().includes(headerFilters.type.toLowerCase())) return false;
      if (headerFilters.owner && !(finding.acknowledged_by_name || "").toLowerCase().includes(headerFilters.owner.toLowerCase())) return false;
      if (headerFilters.car && !linkedCars.some((car) => `${car.car_number} ${car.title}`.toLowerCase().includes(headerFilters.car.toLowerCase()))) return false;
      return true;
    });
  }, [headerFilters, quickFilter, rows, tab]);

  const rowSize = density === "compact"
    ? {
        cell: "px-3 py-2 text-xs",
        chip: "px-2 py-0.5 text-[11px]",
        filter: "h-8 text-xs",
        title: "text-sm",
      }
    : {
        cell: "px-4 py-3 text-sm",
        chip: "px-2.5 py-1 text-xs",
        filter: "h-10 text-sm",
        title: "text-[15px]",
      };

  const textBehavior = wrapText ? "whitespace-normal break-words" : "truncate whitespace-nowrap";
  const loading = registerQuery.isLoading;

  return (
    <QualityAuditsSectionLayout
      title="Register"
      subtitle="Operational closeout register for findings and linked CAR actions."
      toolbar={
        <ResponsiveSegmentedControl
          label="Register dataset"
          value={tab}
          onChange={setTab}
          compactIconsOnMobile
          options={[
            { value: "findings", label: "Findings", icon: ClipboardList },
            { value: "cars", label: "CARs", icon: ShieldAlert },
          ]}
        />
      }
    >
      <div className="space-y-3">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div className="flex min-w-0 items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2">
            <TableProperties className="h-4 w-4 text-slate-500" />
            <input
              value={quickFilter}
              onChange={(event) => setQuickFilter(event.target.value)}
              placeholder="Quick filter across audit ref, finding, owner, CAR, and summary"
              className="w-full bg-transparent text-sm text-slate-100 outline-none placeholder:text-slate-500"
            />
          </div>
          <SpreadsheetToolbar
            density={density}
            onDensityChange={setDensity}
            wrapText={wrapText}
            onWrapTextChange={setWrapText}
            showFilters={showFilters}
            onShowFiltersChange={setShowFilters}
            columnToggles={[
              { id: "owner", label: "Owner", checked: showOwner, onToggle: () => setShowOwner((current) => !current) },
            ]}
          />
        </div>

        <div className="rounded-3xl border border-slate-800 bg-slate-900/70 shadow-[0_20px_60px_rgba(2,6,23,0.18)]">
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <div>
              <h2 className="text-base font-semibold text-slate-50">Closeout register</h2>
              <p className="text-sm text-slate-400">{filteredRows.length} visible rows · {tab === "cars" ? "CAR-linked findings only" : "all findings"}</p>
            </div>
            <div className="rounded-full border border-slate-800 bg-slate-950 px-3 py-1 text-xs text-slate-400">
              {density === "compact" ? "Compact density" : "Comfortable density"}
            </div>
          </div>

          <div className="hidden overflow-auto lg:block">
            <table className="min-w-full table-fixed text-left text-slate-200">
              <thead className="sticky top-0 z-10 bg-slate-950/95 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <tr>
                  <th className={`${rowSize.cell} w-[11rem]`}>Finding ref</th>
                  <th className={`${rowSize.cell} w-[10rem]`}>Audit ref</th>
                  <th className={`${rowSize.cell}`}>Finding</th>
                  <th className={`${rowSize.cell} w-[9rem]`}>Type</th>
                  {showOwner ? <th className={`${rowSize.cell} w-[10rem]`}>Owner</th> : null}
                  <th className={`${rowSize.cell} w-[16rem]`}>Linked CARs</th>
                  <th className={`${rowSize.cell} w-[8rem]`}>Action</th>
                </tr>
                {showFilters ? (
                  <tr className="border-t border-slate-800/80 bg-slate-950/90">
                    {[
                      ["ref", "Find ref"],
                      ["audit", "Audit ref / title"],
                      ["finding", "Finding text"],
                      ["type", "Type"],
                    ].map(([key, placeholder]) => (
                      <th key={key} className={rowSize.cell}>
                        <input
                          value={headerFilters[key as keyof typeof headerFilters]}
                          onChange={(event) => setHeaderFilters((current) => ({ ...current, [key]: event.target.value }))}
                          placeholder={placeholder}
                          className={`w-full rounded-xl border border-slate-800 bg-slate-900 px-3 text-slate-100 placeholder:text-slate-500 ${rowSize.filter}`}
                        />
                      </th>
                    ))}
                    {showOwner ? (
                      <th className={rowSize.cell}>
                        <input
                          value={headerFilters.owner}
                          onChange={(event) => setHeaderFilters((current) => ({ ...current, owner: event.target.value }))}
                          placeholder="Owner"
                          className={`w-full rounded-xl border border-slate-800 bg-slate-900 px-3 text-slate-100 placeholder:text-slate-500 ${rowSize.filter}`}
                        />
                      </th>
                    ) : null}
                    <th className={rowSize.cell}>
                      <input
                        value={headerFilters.car}
                        onChange={(event) => setHeaderFilters((current) => ({ ...current, car: event.target.value }))}
                        placeholder="CAR number / title"
                        className={`w-full rounded-xl border border-slate-800 bg-slate-900 px-3 text-slate-100 placeholder:text-slate-500 ${rowSize.filter}`}
                      />
                    </th>
                    <th className={rowSize.cell} />
                  </tr>
                ) : null}
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={showOwner ? 7 : 6} className="px-4 py-10 text-center text-sm text-slate-500">Loading register…</td>
                  </tr>
                ) : filteredRows.length === 0 ? (
                  <tr>
                    <td colSpan={showOwner ? 7 : 6} className="px-4 py-10 text-center text-sm text-slate-500">No register rows match the current filters.</td>
                  </tr>
                ) : (
                  filteredRows.map(({ audit, finding, linkedCars }) => (
                    <tr key={finding.id} className="border-t border-slate-800/80 align-top hover:bg-slate-800/30">
                      <td className={`${rowSize.cell} text-cyan-300`}>{finding.finding_ref || finding.id}</td>
                      <td className={rowSize.cell}>
                        <div className={`max-w-[9rem] font-medium text-slate-100 ${textBehavior}`}>{audit.audit_ref}</div>
                        <div className={`max-w-[9rem] text-slate-500 ${textBehavior}`}>{audit.title}</div>
                      </td>
                      <td className={rowSize.cell}>
                        <div className={`${rowSize.title} font-medium text-slate-100 ${textBehavior}`}>{finding.description}</div>
                        <div className={`mt-1 text-slate-500 ${wrapText ? "line-clamp-2" : "truncate"}`}>{finding.objective_evidence || "No objective evidence captured."}</div>
                      </td>
                      <td className={rowSize.cell}>
                        <span className={`inline-flex rounded-full border border-slate-700 bg-slate-950 text-slate-200 ${rowSize.chip}`}>{finding.finding_type}</span>
                      </td>
                      {showOwner ? <td className={`${rowSize.cell} text-slate-300`}>{finding.acknowledged_by_name || "Unassigned"}</td> : null}
                      <td className={rowSize.cell}>
                        <div className="flex flex-wrap gap-2">
                          {linkedCars.length === 0 ? <span className="text-slate-500">No linked CARs</span> : linkedCars.map((car) => (
                            <button
                              key={car.id}
                              type="button"
                              onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/closeout/cars/${car.id}`)}
                              className={`inline-flex max-w-full items-center rounded-full border border-amber-500/30 bg-amber-500/10 font-medium text-amber-200 transition hover:border-amber-400/50 ${rowSize.chip}`}
                              title={`${car.car_number} · ${car.title}`}
                            >
                              <span className="truncate">{car.car_number}</span>
                            </button>
                          ))}
                        </div>
                      </td>
                      <td className={rowSize.cell}>
                        <button
                          type="button"
                          onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${audit.id}`)}
                          className="rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-700"
                        >
                          View audit
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="grid gap-3 p-3 lg:hidden">
            {loading ? <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-8 text-center text-sm text-slate-500">Loading register…</div> : null}
            {!loading && filteredRows.length === 0 ? <div className="rounded-2xl border border-slate-800 bg-slate-950 px-4 py-8 text-center text-sm text-slate-500">No register rows match the current filters.</div> : null}
            {!loading && filteredRows.map(({ audit, finding, linkedCars }) => (
              <article key={finding.id} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-cyan-300">{audit.audit_ref}</p>
                    <h3 className="mt-1 text-sm font-semibold text-slate-100">{finding.finding_ref || finding.id}</h3>
                  </div>
                  {linkedCars.length > 0 ? <span className="inline-flex rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs text-amber-200">{linkedCars.length} CARs</span> : null}
                </div>
                <p className="mt-3 text-sm text-slate-200">{finding.description}</p>
                <div className="mt-3 grid gap-2 text-xs text-slate-400">
                  <div>Type: {finding.finding_type}</div>
                  {showOwner ? <div>Owner: {finding.acknowledged_by_name || "Unassigned"}</div> : null}
                  <div>Audit title: {audit.title}</div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button type="button" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${audit.id}`)} className="rounded-xl bg-cyan-500 px-3 py-2 text-xs font-medium text-slate-950">View audit</button>
                  {linkedCars.map((car) => (
                    <button key={car.id} type="button" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/closeout/cars/${car.id}`)} className="rounded-xl border border-slate-800 px-3 py-2 text-xs text-slate-200">
                      {car.car_number}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200"><ClipboardList className="h-4 w-4 text-cyan-300" /> Findings in scope</div>
            <div className="mt-3 text-3xl font-semibold text-slate-50">{rows.length}</div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200"><ShieldAlert className="h-4 w-4 text-amber-300" /> Findings with CARs</div>
            <div className="mt-3 text-3xl font-semibold text-slate-50">{rows.filter((row) => row.linkedCars.length > 0).length}</div>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200"><AlertTriangle className="h-4 w-4 text-rose-300" /> Open CAR count</div>
            <div className="mt-3 text-3xl font-semibold text-slate-50">{rows.flatMap((row) => row.linkedCars).filter((car) => car.status !== "CLOSED").length}</div>
          </div>
        </div>
      </div>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRegisterPage;
