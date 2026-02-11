import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Line, LineChart, ResponsiveContainer, Tooltip, CartesianGrid, XAxis, YAxis, Legend } from "recharts";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { demoTrendSeries } from "../../demo/ehmDemoData";
import { decodeAmoCertFromUrl } from "../../utils/amo";
import "../../styles/ehm.css";

const EhmTrendsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string }>();
  const amoSlug = params.amoCode ?? "UNKNOWN";
  const amoDisplay = amoSlug !== "UNKNOWN" ? decodeAmoCertFromUrl(amoSlug) : "AMO";
  const [metricFilter, setMetricFilter] = useState("ITT");

  const activeSeries = useMemo(() => demoTrendSeries[metricFilter] ?? null, [metricFilter]);

  const chartData = useMemo(
    () =>
      (activeSeries?.points ?? []).map((point) => ({
        date: point.date,
        raw: point.raw,
        corrected: point.corrected,
      })),
    [activeSeries]
  );

  return (
    <DepartmentLayout amoCode={amoSlug} activeDepartment="reliability">
      <header className="ehm-hero ehm-hero--compact">
        <div>
          <p className="ehm-eyebrow">Engine Health Monitoring</p>
          <h1>Trend Graphs · {amoDisplay}</h1>
        </div>
      </header>

      <section className="ehm-surface">
        <div className="ehm-toolbar">
          <label className="ehm-control">
            Metric
            <select value={metricFilter} onChange={(e) => setMetricFilter(e.target.value)}>
              <option value="ITT">ITT</option>
              <option value="NG">NG</option>
              <option value="NH">NH</option>
              <option value="FF">Fuel Flow</option>
              <option value="OAT">OAT / ISA</option>
            </select>
          </label>
        </div>

        <div style={{ width: "100%", height: 380 }}>
          <ResponsiveContainer>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="raw" stroke="#0ea5e9" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="corrected" stroke="#2563eb" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default EhmTrendsPage;
