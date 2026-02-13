import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import DataTableShell from "../../components/shared/DataTableShell";
import SpreadsheetToolbar from "../../components/shared/SpreadsheetToolbar";
import { getContext } from "../../services/auth";
import {
  qmsListAudits,
  qmsListCars,
  qmsListFindings,
  type CAROut
} from "../../services/qms";
import QualityAuditsSectionLayout from "./QualityAuditsSectionLayout";

type RegisterTab = "findings" | "cars";
type Density = "compact" | "comfortable";

type Props = {
  defaultTab: RegisterTab;
};

const QualityAuditRegisterPage: React.FC<Props> = ({ defaultTab }) => {
  const [tab, setTab] = useState<RegisterTab>(defaultTab);
  const [density, setDensity] = useState<Density>("compact");
  const [wrapText, setWrapText] = useState(false);
  const [showOwner, setShowOwner] = useState(true);
  const [showFilters, setShowFilters] = useState(true);
  const [quickFilter, setQuickFilter] = useState("");
  const [headerFilters, setHeaderFilters] = useState({
    findingId: "",
    findingText: "",
    type: "",
    owner: "",
    car: "",
  });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";
  const navigate = useNavigate();

  const audits = useQuery({
    queryKey: ["qms-audits", "register", amoCode],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    staleTime: 60_000,
  });

  const selectedAuditId = audits.data?.find((a) => a.status === "CLOSED")?.id ?? audits.data?.[0]?.id;

  const findings = useQuery({
    queryKey: ["qms-findings", "register", selectedAuditId],
    queryFn: () => qmsListFindings(selectedAuditId || ""),
    enabled: !!selectedAuditId,
    staleTime: 60_000,
  });

  const cars = useQuery({
    queryKey: ["qms-cars", "register"],
    queryFn: () => qmsListCars({}),
    staleTime: 60_000,
  });

  const grouped = useMemo(() => {
    const carByFinding = new Map<string, CAROut[]>();
    (cars.data ?? []).forEach((car) => {
      if (!car.finding_id) return;
      const bucket = carByFinding.get(car.finding_id) ?? [];
      bucket.push(car);
      carByFinding.set(car.finding_id, bucket);
    });
    return (findings.data ?? []).map((finding) => ({
      finding,
      cars: carByFinding.get(finding.id) ?? [],
    }));
  }, [cars.data, findings.data]);

  const filtered = useMemo(() => {
    const q = quickFilter.trim().toLowerCase();
    if (!q) return grouped;
    return grouped.filter(({ finding, cars: linkedCars }) => {
      const text = `${finding.finding_ref ?? ""} ${finding.description} ${finding.finding_type}`.toLowerCase();
      const carMatch = linkedCars.some((car) => `${car.car_number} ${car.title} ${car.summary}`.toLowerCase().includes(q));
      const quick = text.includes(q) || carMatch;
      if (!quick) return false;

      const owner = (finding.acknowledged_by_name ?? "").toLowerCase();
      const idMatch = `${finding.finding_ref ?? finding.id}`.toLowerCase().includes(headerFilters.findingId.toLowerCase());
      const textMatch = finding.description.toLowerCase().includes(headerFilters.findingText.toLowerCase());
      const typeMatch = finding.finding_type.toLowerCase().includes(headerFilters.type.toLowerCase());
      const ownerMatch = owner.includes(headerFilters.owner.toLowerCase());
      const carsMatch = linkedCars.some((car) => `${car.car_number} ${car.title}`.toLowerCase().includes(headerFilters.car.toLowerCase()));
      const carFilterSatisfied = !headerFilters.car.trim() || carsMatch;

      return idMatch && textMatch && typeMatch && ownerMatch && carFilterSatisfied;
    });
  }, [grouped, headerFilters.car, headerFilters.findingId, headerFilters.findingText, headerFilters.owner, headerFilters.type, quickFilter]);

  const rowStyle: React.CSSProperties = {
    padding: density === "compact" ? "6px 8px" : "12px 10px",
    whiteSpace: wrapText ? "normal" : "nowrap",
  };

  return (
    <QualityAuditsSectionLayout
      title="Register"
      subtitle="Findings and CARs in a linked, spreadsheet-like register."
    >
      <DataTableShell
        title="Closeout Register"
        actions={
          <div className="qms-header__actions">
            <div className="qms-segmented" role="tablist" aria-label="Register tab">
              <button type="button" className={tab === "findings" ? "is-active" : ""} onClick={() => setTab("findings")}>Findings</button>
              <button type="button" className={tab === "cars" ? "is-active" : ""} onClick={() => setTab("cars")}>CARs</button>
            </div>
            <SpreadsheetToolbar
              density={density}
              onDensityChange={setDensity}
              wrapText={wrapText}
              onWrapTextChange={setWrapText}
              showFilters={showFilters}
              onShowFiltersChange={setShowFilters}
              columnToggles={[
                { id: "owner", label: "Owner", checked: showOwner, onToggle: () => setShowOwner((v) => !v) },
              ]}
            />
          </div>
        }
      >
        <div style={{ marginBottom: 8 }}>
          <input
            className="input"
            style={{ maxWidth: 320, height: 38 }}
            placeholder="Quick filter (finding/CAR/summary)"
            value={quickFilter}
            onChange={(e) => setQuickFilter(e.target.value)}
          />
        </div>
        <table className={`table ${density === "compact" ? "table-row--compact" : "table-row--comfortable"} ${wrapText ? "table--wrap" : ""}`}>
          <thead>
            <tr>
              <th style={rowStyle}>Finding ID</th>
              <th style={rowStyle}>Finding</th>
              <th style={rowStyle}>Type</th>
              {showOwner ? <th style={rowStyle}>Owner</th> : null}
              <th style={rowStyle}>Linked CARs</th>
              <th style={rowStyle}>Actions</th>
            </tr>
            {showFilters ? <tr>
              <th style={rowStyle}><input className="input" style={{ height: 30 }} placeholder="Find ID" value={headerFilters.findingId} onChange={(e) => setHeaderFilters((prev) => ({ ...prev, findingId: e.target.value }))} /></th>
              <th style={rowStyle}><input className="input" style={{ height: 30 }} placeholder="Filter finding text" value={headerFilters.findingText} onChange={(e) => setHeaderFilters((prev) => ({ ...prev, findingText: e.target.value }))} /></th>
              <th style={rowStyle}><input className="input" style={{ height: 30 }} placeholder="Type" value={headerFilters.type} onChange={(e) => setHeaderFilters((prev) => ({ ...prev, type: e.target.value }))} /></th>
              {showOwner ? <th style={rowStyle}><input className="input" style={{ height: 30 }} placeholder="Owner" value={headerFilters.owner} onChange={(e) => setHeaderFilters((prev) => ({ ...prev, owner: e.target.value }))} /></th> : null}
              <th style={rowStyle}><input className="input" style={{ height: 30 }} placeholder="CAR" value={headerFilters.car} onChange={(e) => setHeaderFilters((prev) => ({ ...prev, car: e.target.value }))} /></th>
              <th style={rowStyle}></th>
            </tr> : null}
          </thead>
          <tbody>
            {filtered.map(({ finding, cars: linkedCars }) => {
              const isOpen = !!expanded[finding.id];
              if (tab === "cars" && linkedCars.length === 0) return null;
              return (
                <React.Fragment key={finding.id}>
                  <tr>
                    <td style={rowStyle}>{finding.finding_ref ?? finding.id}</td>
                    <td style={rowStyle}>{finding.description}</td>
                    <td style={rowStyle}>{finding.finding_type}</td>
                    {showOwner ? <td style={rowStyle}>{finding.acknowledged_by_name ?? "Unassigned"}</td> : null}
                    <td style={rowStyle}>{linkedCars.length}</td>
                    <td style={rowStyle}>
                      <button type="button" className="secondary-chip-btn" onClick={() => setExpanded((prev) => ({ ...prev, [finding.id]: !isOpen }))}>
                        {isOpen ? "Collapse" : "Expand"}
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td style={rowStyle} colSpan={showOwner ? 6 : 5}>
                        <div className="qms-card" style={{ margin: 0 }}>
                          <strong>Linked CARs (CARs cannot exist without findings)</strong>
                          {linkedCars.length === 0 ? (
                            <p className="text-muted" style={{ marginBottom: 0 }}>No linked CARs yet.</p>
                          ) : (
                            <table className="table" style={{ marginTop: 8 }}>
                              <thead>
                                <tr>
                                  <th>CAR #</th>
                                  <th>Title</th>
                                  <th>Status</th>
                                  <th>Due</th>
                                  <th></th>
                                </tr>
                              </thead>
                              <tbody>
                                {linkedCars.map((car) => (
                                  <tr key={car.id}>
                                    <td>{car.car_number}</td>
                                    <td>{car.title}</td>
                                    <td>{car.status}</td>
                                    <td>{car.due_date ?? "—"}</td>
                                    <td>
                                      <button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/closeout/cars/${car.id}`)}>
                                        Open CAR
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </DataTableShell>
    </QualityAuditsSectionLayout>
  );
};

export default QualityAuditRegisterPage;
