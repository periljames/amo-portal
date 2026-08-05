import React from "react";
import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardResponse } from "./reliabilityAnalyticsTypes";
import { CHART_HEIGHT, ChartCard, PIE_COLORS, exportChartSvg } from "./reliabilityAnalyticsUtils";

type PointHandler = (value: unknown, title: string) => void;

export function ReliabilityAnalyticsControlCharts({ data, onPoint }: { data: DashboardResponse; onPoint: PointHandler }): React.ReactElement {
  const handleChartClick = onPoint;
  return <>
            <ChartCard id="rel-chart-deferral-expiry" eyebrow="MEL / CDL forecast" title="Deferral expiry exposure" description="Current open deferrals grouped by approved expiry horizon." empty={data.deferral_expiry.every((point) => !point.metrics.count)} onExport={() => exportChartSvg("rel-chart-deferral-expiry", "reliability-deferral-expiry")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.deferral_expiry.map((point) => ({ ...point, ...point.metrics }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" interval={0} angle={-20} textAnchor="end" height={70} />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" name="Deferrals" radius={[4, 4, 0, 0]} onClick={(value: unknown) => handleChartClick(value, "Deferral expiry")} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-deferral-status" eyebrow="MEL / CDL control" title="Deferral lifecycle status" description="Current deferral population by controlled lifecycle state." empty={data.deferral_status.length === 0} onExport={() => exportChartSvg("rel-chart-deferral-status", "reliability-deferral-status")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <PieChart><Pie data={data.deferral_status.map((point) => ({ ...point, ...point.metrics }))} dataKey="count" nameKey="label" innerRadius={70} outerRadius={112} onClick={(value: unknown) => handleChartClick(value, "Deferral status")}>{data.deferral_status.map((point, index) => <Cell key={point.key} fill={PIE_COLORS[index % PIE_COLORS.length]} />)}</Pie><Tooltip /><Legend /></PieChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-deferral-category" eyebrow="MEL / CDL classification" title="Open deferrals by category" description="Open MEL/CDL exposure grouped by the approved category." empty={data.deferral_categories.length === 0} onExport={() => exportChartSvg("rel-chart-deferral-category", "reliability-deferral-categories")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.deferral_categories.map((point) => ({ ...point, ...point.metrics }))}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" name="Open deferrals" onClick={(value: unknown) => handleChartClick(value, "Deferral category")} /></BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-deferral-extensions" eyebrow="Extension governance" title="Extensions by reason" description="Controlled MEL/CDL extensions grouped by the recorded approval reason." empty={data.deferral_extensions.length === 0} onExport={() => exportChartSvg("rel-chart-deferral-extensions", "reliability-deferral-extensions")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.deferral_extensions.map((point) => ({ ...point, ...point.metrics }))} layout="vertical" margin={{ left: 50 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="label" width={180} /><Tooltip /><Bar dataKey="count" name="Extensions" onClick={(value: unknown) => handleChartClick(value, "Extension reason")} /></BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-deferral-repeats" eyebrow="Repeat exposure" title="Repeated deferral items" description="Aircraft and item-reference combinations raised more than once." empty={data.deferral_repeats.length === 0} onExport={() => exportChartSvg("rel-chart-deferral-repeats", "reliability-repeat-deferrals")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.deferral_repeats.map((point) => ({ ...point, ...point.metrics }))} layout="vertical" margin={{ left: 50 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="label" width={180} /><Tooltip /><Bar dataKey="count" name="Occurrences" onClick={(value: unknown) => handleChartClick(value, "Repeat deferral")} /></BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-deferral-closure" eyebrow="Closure performance" title="Average closure duration" description="Elapsed application-to-closure days by MEL/CDL category." empty={data.deferral_closure.length === 0} onExport={() => exportChartSvg("rel-chart-deferral-closure", "reliability-deferral-closure")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.deferral_closure.map((point) => ({ ...point, ...point.metrics }))}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis /><Tooltip /><Bar dataKey="average_days" name="Average days" onClick={(value: unknown) => handleChartClick(value, "Deferral closure")}/></BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-fracas" eyebrow="Closed-loop control" title="FRACAS stage loading" description="Case distribution across investigation, action, implementation and effectiveness stages." empty={data.fracas_stages.length === 0} onExport={() => exportChartSvg("rel-chart-fracas", "reliability-fracas-stages")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <PieChart>
                  <Pie data={data.fracas_stages.map((point) => ({ ...point, ...point.metrics }))} dataKey="count" nameKey="label" innerRadius={72} outerRadius={116} paddingAngle={2} onClick={(value: unknown) => handleChartClick(value, "FRACAS stage")}>
                    {data.fracas_stages.map((point, index) => <Cell key={point.key} fill={PIE_COLORS[index % PIE_COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-fracas-age" eyebrow="Case ageing" title="Open FRACAS ageing" description="Age bands expose investigation and implementation bottlenecks." empty={data.fracas_ageing.every((point) => !point.metrics.count)} onExport={() => exportChartSvg("rel-chart-fracas-age", "reliability-fracas-ageing")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.fracas_ageing.map((point) => ({ ...point, ...point.metrics }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="count" name="Cases" radius={[4, 4, 0, 0]} onClick={(value: unknown) => handleChartClick(value, "FRACAS age")} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-root-cause" eyebrow="Failure mechanisms" title="Root-cause distribution" description="Approved or recorded root causes, with unclassified cases left visible." empty={data.root_causes.length === 0} onExport={() => exportChartSvg("rel-chart-root-cause", "reliability-root-causes")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.root_causes.map((point) => ({ ...point, ...point.metrics }))} layout="vertical" margin={{ left: 42 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} />
                  <YAxis type="category" dataKey="label" width={170} />
                  <Tooltip />
                  <Bar dataKey="count" name="Cases" radius={[0, 4, 4, 0]} onClick={(value: unknown) => handleChartClick(value, "Root cause")} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-effectiveness" eyebrow="Verification" title="Effectiveness outcomes" description="Approved and pending effectiveness results for corrective actions." empty={data.effectiveness.length === 0} onExport={() => exportChartSvg("rel-chart-effectiveness", "reliability-effectiveness")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.effectiveness.map((point) => ({ ...point, ...point.metrics }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="label" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="count" name="Reviews" radius={[4, 4, 0, 0]} onClick={(value: unknown) => handleChartClick(value, "Effectiveness")} />
                  <Bar dataKey="approved" name="Approved" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-fracas-actions" eyebrow="Action control" title="FRACAS action status" description="Corrective and preventive actions by current state, including overdue work." empty={data.fracas_actions.length === 0} onExport={() => exportChartSvg("rel-chart-fracas-actions", "reliability-fracas-actions")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <BarChart data={data.fracas_actions.map((point) => ({ ...point, ...point.metrics }))}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" name="Actions" onClick={(value: unknown) => handleChartClick(value, "FRACAS action status")} /></BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-fracas-action-trend" eyebrow="Implementation flow" title="Action creation, completion and overdue trend" description="Period movement of corrective and preventive actions." empty={data.fracas_action_trend.length === 0} wide onExport={() => exportChartSvg("rel-chart-fracas-action-trend", "reliability-fracas-action-trend")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <ComposedChart data={data.fracas_action_trend.map((point) => ({ ...point, ...point.metrics }))}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="label" /><YAxis allowDecimals={false} /><Tooltip /><Legend /><Bar dataKey="created" name="Created" onClick={(value: unknown) => handleChartClick(value, "FRACAS action period")} /><Bar dataKey="completed" name="Completed" onClick={(value: unknown) => handleChartClick(value, "FRACAS action period")} /><Line dataKey="overdue" name="Overdue" stroke={PIE_COLORS[4]} strokeWidth={2} /></ComposedChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard id="rel-chart-fracas-reopened" eyebrow="Effectiveness failure" title="Reopened FRACAS cases" description="Cases that remained closed versus those reopened after ineffective resolution." empty={data.fracas_reopened.length === 0} onExport={() => exportChartSvg("rel-chart-fracas-reopened", "reliability-fracas-reopened")}>
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <PieChart><Pie data={data.fracas_reopened.map((point) => ({ ...point, ...point.metrics }))} dataKey="count" nameKey="label" innerRadius={70} outerRadius={112} onClick={(value: unknown) => handleChartClick(value, "FRACAS reopened")}>{data.fracas_reopened.map((point, index) => <Cell key={point.key} fill={PIE_COLORS[index % PIE_COLORS.length]} />)}</Pie><Tooltip /><Legend /></PieChart>
              </ResponsiveContainer>
            </ChartCard>
  </>;
}
