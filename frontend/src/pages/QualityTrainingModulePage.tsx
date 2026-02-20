import React, { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  getTrainingDashboard,
  getTrainingCourse,
  getTrainingSession,
  getTrainingSettings,
  getTrainingStaff,
  listTrainingCatalog,
  listTrainingMatrix,
  listTrainingSessions,
  listTrainingStaff,
} from "../services/qualityTraining";

const tabsMap: Record<string, string[]> = {
  catalogDetail: ["Overview", "Syllabus/Assets", "Requirements", "Recurrence", "Sessions", "Evidence", "Audit Log"],
  sessionDetail: ["Overview", "Roster", "Attendance", "Results", "Evidence", "Audit Log"],
  staffDetail: ["Profile", "Required Training", "Completed", "Authorisations", "Evidence", "Audit Log"],
};

const QualityTrainingModulePage: React.FC = () => {
  const location = useLocation();
  const { courseId, sessionId, staffId } = useParams();
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const path = location.pathname;
    if (path.endsWith("/quality/training")) getTrainingDashboard().then(setData);
    else if (path.endsWith("/catalog")) listTrainingCatalog().then(setData);
    else if (courseId) getTrainingCourse(courseId).then(setData);
    else if (path.endsWith("/sessions")) listTrainingSessions().then(setData);
    else if (sessionId) getTrainingSession(sessionId).then(setData);
    else if (path.endsWith("/staff")) listTrainingStaff().then(setData);
    else if (staffId) getTrainingStaff(staffId).then(setData);
    else if (path.endsWith("/matrix")) listTrainingMatrix().then(setData);
    else if (path.endsWith("/settings")) getTrainingSettings().then(setData);
    else setData({ reports: ["Overdue training report", "Expiring authorisations report", "Training completion report", "Evidence completeness report", "Instructor activity report"] });
  }, [location.pathname, courseId, sessionId, staffId]);

  const path = location.pathname;
  return (
    <div className="page training-page">
      <h1>Quality → Training</h1>
      <nav style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <Link to="/quality/training">Dashboard</Link><Link to="/quality/training/catalog">Catalog</Link><Link to="/quality/training/sessions">Sessions</Link><Link to="/quality/training/staff">Staff</Link><Link to="/quality/training/matrix">Matrix</Link><Link to="/quality/training/reports">Reports</Link><Link to="/quality/training/settings">Settings</Link>
      </nav>
      {path.endsWith("/quality/training") && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(180px, 1fr))", gap: 12 }}>
          {[
            ["Training due in 30 days", "training_due_30_days"],
            ["Training overdue", "training_overdue"],
            ["Authorisations expiring in 60 days", "authorisations_expiring_60_days"],
            ["Sessions scheduled next 14 days", "sessions_next_14_days"],
            ["Completions last 30 days", "completions_last_30_days"],
            ["Evidence missing", "evidence_missing"],
          ].map(([label, key]) => <div key={key} className="card"><strong>{label}</strong><div>{data?.[key] ?? 0}</div></div>)}
        </div>
      )}
      {(path.endsWith("/catalog") || path.endsWith("/sessions") || path.endsWith("/staff") || path.endsWith("/matrix")) && <pre>{JSON.stringify(data, null, 2)}</pre>}
      {(courseId || sessionId || staffId) && <div><div style={{ display: "flex", gap: 8 }}>{(courseId ? tabsMap.catalogDetail : sessionId ? tabsMap.sessionDetail : tabsMap.staffDetail).map((t) => <span key={t} className="badge">{t}</span>)}</div><pre>{JSON.stringify(data, null, 2)}</pre></div>}
      {path.endsWith("/reports") && <ul>{(data?.reports || []).map((r: string) => <li key={r}>{r} (PDF/CSV export)</li>)}</ul>}
      {path.endsWith("/settings") && <pre>{JSON.stringify(data, null, 2)}</pre>}
    </div>
  );
};

export default QualityTrainingModulePage;
