import React, { useEffect, useMemo, useState } from "react";
import { BadgeCheck, CalendarDays, ShieldAlert } from "lucide-react";
import { listTrainingPersonnelLicences } from "../../services/trainingWorkbookImport";
import type { PersonnelLicenceRead } from "../../types/trainingWorkbookImport";
import "../../styles/personnel-licences.css";

interface FallbackLicence {
  authority?: string | null;
  licenceNumber?: string | null;
  country?: string | null;
  expiresOn?: string | null;
}

interface Props {
  userId: string;
  fallback?: FallbackLicence;
}

function formatDate(value?: string | null): string {
  if (!value) return "Not recorded";
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
}

const PersonnelLicencePanel: React.FC<Props> = ({ userId, fallback }) => {
  const [rows, setRows] = useState<PersonnelLicenceRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    listTrainingPersonnelLicences(userId)
      .then((items) => {
        if (mounted) setRows(items);
      })
      .catch((reason) => {
        if (mounted) setError(reason instanceof Error ? reason.message : "Licence register unavailable.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [userId]);

  const displayed = useMemo(() => {
    if (rows.length) return rows;
    if (!fallback?.licenceNumber) return [];
    return [{
      id: `fallback-${userId}`,
      personnel_profile_id: "",
      user_id: userId,
      authority: fallback.authority || "Regulatory authority",
      country: fallback.country || null,
      licence_number: fallback.licenceNumber,
      category_code: null,
      category_source: null,
      issued_on: null,
      expires_on: fallback.expiresOn || null,
      expiry_source_record_id: null,
      expiry_source_course_id: null,
      expiry_synced_at: null,
      internal_stamp_no: null,
      initial_authorization_date: null,
      status: "ACTIVE",
      is_primary: true,
      created_at: "",
      updated_at: "",
    } satisfies PersonnelLicenceRead];
  }, [fallback, rows, userId]);

  return (
    <section className="personnel-licences" aria-label="Personnel licence register">
      <div className="personnel-licences__header">
        <div>
          <span>Regulatory credentials</span>
          <strong>Licences and certification scope</strong>
        </div>
        <BadgeCheck size={20} />
      </div>
      {loading ? <p className="personnel-licences__state">Loading licence register…</p> : null}
      {!loading && displayed.length === 0 ? <p className="personnel-licences__state">No regulatory licence is recorded for this person.</p> : null}
      {error && displayed.length === 0 ? <p className="personnel-licences__state personnel-licences__state--warning"><ShieldAlert size={15} /> {error}</p> : null}
      {displayed.length > 0 ? (
        <div className="personnel-licences__grid">
          {displayed.map((licence) => (
            <article key={licence.id} className={`personnel-licence ${licence.is_primary ? "is-primary" : ""}`}>
              <div className="personnel-licence__top">
                <span>{licence.authority.replaceAll("_", " ")}</span>
                <small>{licence.status}</small>
              </div>
              <strong>{licence.licence_number}</strong>
              <dl>
                <div><dt>Country</dt><dd>{licence.country || "Not recorded"}</dd></div>
                <div><dt>Category</dt><dd>{licence.category_code || "Not recorded"}</dd></div>
                <div><dt>Initial authorisation</dt><dd>{formatDate(licence.initial_authorization_date)}</dd></div>
                <div><dt>Expiry</dt><dd><CalendarDays size={13} /> {formatDate(licence.expires_on)}</dd></div>
                {licence.expiry_source_record_id ? <div><dt>Expiry source</dt><dd>AMEL renewal training<small>Record {licence.expiry_source_record_id}</small></dd></div> : null}
                {licence.internal_stamp_no ? <div><dt>Internal stamp</dt><dd>{licence.internal_stamp_no}</dd></div> : null}
              </dl>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
};

export default PersonnelLicencePanel;
