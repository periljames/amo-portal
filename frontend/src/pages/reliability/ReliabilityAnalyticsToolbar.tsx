import React from "react";

import type { DashboardFilters, DashboardResponse, SavedView } from "./reliabilityAnalyticsTypes";
import { FilterSelect } from "./reliabilityAnalyticsUtils";

type Props = {
  filters: DashboardFilters;
  data: DashboardResponse | null;
  loading: boolean;
  savedViews: SavedView[];
  selectedViewId: string;
  savedViewName: string;
  setFilters: React.Dispatch<React.SetStateAction<DashboardFilters>>;
  setSavedViewName: (value: string) => void;
  applyFilters: () => void;
  applyRange: (days: number) => void;
  resetFilters: () => void;
  refresh: () => void;
  saveView: () => void;
  applySavedView: (id: string) => void;
  deleteSavedView: () => void;
  exportCsv: () => void;
};

export function ReliabilityAnalyticsToolbar({
  filters,
  data,
  loading,
  savedViews,
  selectedViewId,
  savedViewName,
  setFilters,
  setSavedViewName,
  applyFilters,
  applyRange,
  resetFilters,
  refresh,
  saveView,
  applySavedView,
  deleteSavedView,
  exportCsv,
}: Props): React.ReactElement {
  return (
    <section className="reliability-analytics__toolbar" aria-label="Reliability dashboard filters">
      <div className="reliability-analytics__toolbar-row reliability-analytics__toolbar-row--dates">
        <label className="reliability-analytics__filter">
          <span>Period start</span>
          <input type="date" value={filters.periodStart} onChange={(event) => setFilters((current) => ({ ...current, periodStart: event.target.value }))} />
        </label>
        <label className="reliability-analytics__filter">
          <span>Period end</span>
          <input type="date" value={filters.periodEnd} onChange={(event) => setFilters((current) => ({ ...current, periodEnd: event.target.value }))} />
        </label>
        <label className="reliability-analytics__filter">
          <span>Chart bucket</span>
          <select value={filters.bucket} onChange={(event) => setFilters((current) => ({ ...current, bucket: event.target.value as DashboardFilters["bucket"] }))}>
            <option value="AUTO">Automatic</option>
            <option value="DAY">Daily</option>
            <option value="WEEK">Weekly</option>
            <option value="MONTH">Monthly</option>
          </select>
        </label>
        <div className="reliability-analytics__quick-ranges">
          <span>Quick range</span>
          <div>
            <button type="button" onClick={() => applyRange(30)}>30d</button>
            <button type="button" onClick={() => applyRange(90)}>90d</button>
            <button type="button" onClick={() => applyRange(365)}>12m</button>
          </div>
        </div>
      </div>
      <div className="reliability-analytics__toolbar-row">
        <FilterSelect label="Aircraft" value={filters.aircraft} options={data?.filters.aircraft || []} onChange={(value) => setFilters((current) => ({ ...current, aircraft: value }))} />
        <FilterSelect label="Fleet / type" value={filters.aircraftType} options={data?.filters.aircraft_types || []} onChange={(value) => setFilters((current) => ({ ...current, aircraftType: value }))} />
        <FilterSelect label="ATA chapter" value={filters.ataChapter} options={data?.filters.ata_chapters || []} onChange={(value) => setFilters((current) => ({ ...current, ataChapter: value }))} />
        <FilterSelect label="Station" value={filters.station} options={data?.filters.stations || []} onChange={(value) => setFilters((current) => ({ ...current, station: value }))} />
        <FilterSelect label="Event type" value={filters.eventType} options={data?.filters.event_types || []} onChange={(value) => setFilters((current) => ({ ...current, eventType: value }))} />
        <FilterSelect label="Severity" value={filters.severity} options={data?.filters.severities || []} onChange={(value) => setFilters((current) => ({ ...current, severity: value }))} />
        <FilterSelect label="Source" value={filters.sourceSystem} options={data?.filters.source_systems || []} onChange={(value) => setFilters((current) => ({ ...current, sourceSystem: value }))} />
      </div>
      <div className="reliability-analytics__toolbar-actions">
        <button type="button" className="btn btn-primary" onClick={applyFilters} disabled={loading}>Apply filters</button>
        <button type="button" className="btn btn-secondary" onClick={resetFilters}>Reset</button>
        <button type="button" className="btn btn-secondary" onClick={refresh} disabled={loading}>Refresh</button>
        <label className="reliability-analytics__save-view">
          <span>Save current view</span>
          <input
            value={savedViewName}
            maxLength={80}
            placeholder="e.g. Monthly fleet review"
            onChange={(event) => setSavedViewName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                saveView();
              }
            }}
          />
          <button type="button" className="btn btn-secondary" onClick={saveView}>Save</button>
        </label>
        <select aria-label="Saved Reliability views" value={selectedViewId} onChange={(event) => applySavedView(event.target.value)}>
          <option value="">Saved views</option>
          {savedViews.map((view) => <option key={view.id} value={view.id}>{view.name}</option>)}
        </select>
        <button type="button" className="reliability-analytics__text-button" onClick={deleteSavedView} disabled={!selectedViewId}>Delete view</button>
        <span className="reliability-analytics__toolbar-spacer" />
        <button type="button" className="btn btn-secondary" onClick={exportCsv} disabled={!data}>Export CSV</button>
        <button type="button" className="btn btn-secondary" onClick={() => window.print()} disabled={!data}>Print / save PDF</button>
      </div>
    </section>
  );
}
