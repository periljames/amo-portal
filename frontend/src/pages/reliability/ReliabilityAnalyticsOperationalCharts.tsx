import React from "react";
import { Bar, BarChart, Brush, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartPoint } from "./reliabilityAnalyticsTypes";
import { CHART_HEIGHT, ChartCard, exportChartSvg } from "./reliabilityAnalyticsUtils";

type PointHandler = (value: unknown, title: string) => void;
type ChartRow = ChartPoint & Record<string, unknown>;

type Props = {
  trendRows: ChartRow[];
  eventMixRows: ChartRow[];
  ataRows: ChartRow[];
  aircraftRows: ChartRow[];
  stationRows: ChartRow[];
  routeRows: ChartRow[];
  componentRows: ChartRow[];
  removalAgeRows: ChartRow[];
  shopVisitRows: ChartRow[];
  oilRows: ChartRow[];
  onPoint: PointHandler;
};

export function ReliabilityAnalyticsOperationalCharts({ trendRows, eventMixRows, ataRows, aircraftRows, stationRows, routeRows, componentRows, removalAgeRows, shopVisitRows, oilRows, onPoint }: Props): React.ReactElement {
  return <>
    <ChartCard id="rel-chart-trend" eyebrow="Normalised trend" title="Fleet reliability over time" description="Event rate per 100 flight hours and dispatch reliability against recorded cycles." empty={trendRows.length === 0} wide tableRows={trendRows} formulaCodes={["event_rate_per_100_fh", "dispatch_reliability_pct"]} onExport={() => exportChartSvg("rel-chart-trend", "reliability-fleet-trend")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={trendRows} onClick={(value: unknown) => onPoint(value, "Measured period")}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" minTickGap={18} />
          <YAxis yAxisId="rate" label={{ value: "Events / 100 FH", angle: -90, position: "insideLeft" }} />
          <YAxis yAxisId="dispatch" orientation="right" domain={[0, 100]} label={{ value: "Dispatch reliability %", angle: 90, position: "insideRight" }} />
          <Tooltip /><Legend />
          <Bar yAxisId="rate" dataKey="event_rate_per_100_fh" name="Event rate /100 FH" radius={[4, 4, 0, 0]} />
          <Line yAxisId="dispatch" type="monotone" dataKey="dispatch_reliability_pct" name="Dispatch reliability %" strokeWidth={2.5} connectNulls />
          {trendRows.length > 12 && <Brush dataKey="label" height={24} travellerWidth={10} />}
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-event-mix" eyebrow="Operational consequence" title="Technical interruption mix" description="Canonical event composition and accumulated delay burden." empty={eventMixRows.length === 0} tableRows={eventMixRows} onExport={() => exportChartSvg("rel-chart-event-mix", "reliability-event-mix")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={eventMixRows.slice(0, 12)} layout="vertical" margin={{ left: 24 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" /><YAxis type="category" dataKey="label" width={138} /><Tooltip /><Legend />
          <Bar dataKey="count" name="Events" radius={[0, 4, 4, 0]} onClick={(value: unknown) => onPoint(value, "Event type")} />
          <Bar dataKey="delay_minutes" name="Delay minutes" radius={[0, 4, 4, 0]} onClick={(value: unknown) => onPoint(value, "Event type")} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-ata" eyebrow="Pareto analysis" title="ATA concentration" description="Top ATA chapters with cumulative share, delay burden and repeat defects." empty={ataRows.length === 0} tableRows={ataRows} formulaCodes={["ata_cumulative_pct"]} onExport={() => exportChartSvg("rel-chart-ata", "reliability-ata-pareto")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ComposedChart data={ataRows.slice(0, 15)}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" angle={-35} textAnchor="end" height={92} interval={0} /><YAxis yAxisId="count" /><YAxis yAxisId="pct" orientation="right" domain={[0, 100]} /><Tooltip /><Legend />
          <Bar yAxisId="count" dataKey="count" name="Events" radius={[4, 4, 0, 0]} onClick={(value: unknown) => onPoint(value, "ATA chapter")} />
          <Line yAxisId="pct" type="monotone" dataKey="cumulative_pct" name="Cumulative %" strokeWidth={2} />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-aircraft" eyebrow="Fleet comparison" title="Aircraft event rate" description="Normalised event rate exposes aircraft performance without rewarding low utilisation." empty={aircraftRows.length === 0} tableRows={aircraftRows} formulaCodes={["event_rate_per_100_fh"]} onExport={() => exportChartSvg("rel-chart-aircraft", "reliability-aircraft-rate")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={aircraftRows.slice(0, 16)} layout="vertical" margin={{ left: 22 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" /><YAxis type="category" dataKey="label" width={120} /><Tooltip />
          <Bar dataKey="event_rate_per_100_fh" name="Events /100 FH" radius={[0, 4, 4, 0]} onClick={(value: unknown) => onPoint(value, "Aircraft")} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-station" eyebrow="Network impact" title="Delay burden by origin station" description="Technical interruptions, delay minutes and cancellations at the dispatch station." empty={stationRows.length === 0} tableRows={stationRows} onExport={() => exportChartSvg("rel-chart-station", "reliability-station-delay")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={stationRows.slice(0, 15)}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis /><Tooltip /><Legend />
          <Bar dataKey="delay_minutes" name="Delay minutes" radius={[4, 4, 0, 0]} onClick={(value: unknown) => onPoint(value, "Station")} />
          <Bar dataKey="cancellations" name="Cancellations" radius={[4, 4, 0, 0]} onClick={(value: unknown) => onPoint(value, "Station")} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-route" eyebrow="Route impact" title="Technical delay by route" description="Delay minutes, interruption volume and cancellations by origin-destination pair." empty={routeRows.length === 0} wide tableRows={routeRows} onExport={() => exportChartSvg("rel-chart-route", "reliability-route-delay")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={routeRows.slice(0, 20)} layout="vertical" margin={{ left: 48 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" /><YAxis type="category" dataKey="label" width={150} /><Tooltip /><Legend />
          <Bar dataKey="delay_minutes" name="Delay minutes" radius={[0, 4, 4, 0]} onClick={(value: unknown) => onPoint(value, "Route")} />
          <Bar dataKey="cancellations" name="Cancellations" radius={[0, 4, 4, 0]} onClick={(value: unknown) => onPoint(value, "Route")} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-components" eyebrow="Component reliability" title="Shop outcomes and removals" description="No-fault-found, confirmed failures and removal mix by part number. Fleet exposure per removal is shown only where measurable." empty={componentRows.length === 0} wide tableRows={componentRows} formulaCodes={["nff_rate_pct", "fleet_exposure_per_unscheduled_removal"]} onExport={() => exportChartSvg("rel-chart-components", "reliability-component-outcomes")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={componentRows.slice(0, 20)} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" /><YAxis type="category" dataKey="label" width={150} /><Tooltip /><Legend />
          <Bar dataKey="unscheduled_removals" name="Unscheduled removals" stackId="removals" onClick={(value: unknown) => onPoint(value, "Component")} />
          <Bar dataKey="scheduled_removals" name="Scheduled removals" stackId="removals" onClick={(value: unknown) => onPoint(value, "Component")} />
          <Bar dataKey="confirmed_failures" name="Confirmed failures" onClick={(value: unknown) => onPoint(value, "Component")} />
          <Bar dataKey="nff" name="NFF" onClick={(value: unknown) => onPoint(value, "Component")} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-component-rates" eyebrow="Exposure-normalised removal" title="Unscheduled removal rate" description="Unscheduled removals per 1,000 flight hours and cycles. Values are withheld when exposure is absent." empty={componentRows.every((row) => row.removal_rate_per_1000_fh == null && row.removal_rate_per_1000_fc == null)} wide tableRows={componentRows} formulaCodes={["removal_rate_per_1000_fh", "removal_rate_per_1000_fc"]} onExport={() => exportChartSvg("rel-chart-component-rates", "reliability-component-removal-rates")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={componentRows.slice(0, 20)} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" /><YAxis type="category" dataKey="label" width={150} /><Tooltip /><Legend />
          <Bar dataKey="removal_rate_per_1000_fh" name="Per 1,000 FH" onClick={(value: unknown) => onPoint(value, "Component removal rate")} />
          <Bar dataKey="removal_rate_per_1000_fc" name="Per 1,000 FC" onClick={(value: unknown) => onPoint(value, "Component removal rate")} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-removal-age" eyebrow="Removal age" title="Usage at component removal" description="Recorded component hours at removal. Missing usage remains visible instead of being silently discarded." empty={removalAgeRows.every((row) => !row.count)} tableRows={removalAgeRows} onExport={() => exportChartSvg("rel-chart-removal-age", "reliability-removal-age")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={removalAgeRows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" interval={0} angle={-20} textAnchor="end" height={70} /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" name="Removals" onClick={(value: unknown) => onPoint(value, "Removal age")} /></BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-shop-visits" eyebrow="Repair exposure" title="Component shop-visit trend" description="Controlled shop-visit records by analytical period." empty={shopVisitRows.length === 0} tableRows={shopVisitRows} onExport={() => exportChartSvg("rel-chart-shop-visits", "reliability-shop-visit-trend")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={shopVisitRows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="shop_visits" name="Shop visits" onClick={(value: unknown) => onPoint(value, "Shop visits")} />{shopVisitRows.length > 12 && <Brush dataKey="label" height={24} travellerWidth={10} />}</BarChart>
      </ResponsiveContainer>
    </ChartCard>

    <ChartCard id="rel-chart-oil-consumption" eyebrow="Oil consumption" title="Engine oil-consumption rate" description="Latest and average quarts per flight hour by aircraft and engine position." empty={oilRows.length === 0} wide tableRows={oilRows} formulaCodes={["oil_consumption_qt_per_fh"]} onExport={() => exportChartSvg("rel-chart-oil-consumption", "reliability-oil-consumption")}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <BarChart data={oilRows.slice(0, 20)} layout="vertical" margin={{ left: 48 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" /><YAxis type="category" dataKey="label" width={180} /><Tooltip /><Legend /><Bar dataKey="latest_qt_per_hour" name="Latest qt/FH" onClick={(value: unknown) => onPoint(value, "Oil consumption")} /><Bar dataKey="average_qt_per_hour" name="Average qt/FH" onClick={(value: unknown) => onPoint(value, "Oil consumption")} /></BarChart>
      </ResponsiveContainer>
    </ChartCard>
  </>;
}
