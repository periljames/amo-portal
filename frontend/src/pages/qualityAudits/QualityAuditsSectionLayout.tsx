import React, { useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../../components/QMS/QMSLayout";
import { getContext } from "../../services/auth";

type Props = {
  title: string;
  subtitle: string;
  children: React.ReactNode;
};

type SubpageLink = {
  id: string;
  label: string;
  to: string;
  prefixes?: string[];
};

const QualityAuditsSectionLayout: React.FC<Props> = ({ title, subtitle, children }) => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const location = useLocation();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";

  const links = useMemo<SubpageLink[]>(
    () => [
      {
        id: "plan-schedule",
        label: "Plan / Schedule",
        to: `/maintenance/${amoCode}/${department}/qms/audits/schedules/calendar`,
        prefixes: [
          `/maintenance/${amoCode}/${department}/qms/audits/schedules/list`,
          `/maintenance/${amoCode}/${department}/qms/audits/schedules/`,
        ],
      },
      {
        id: "register",
        label: "Register",
        to: `/maintenance/${amoCode}/${department}/qms/audits/closeout/findings`,
        prefixes: [`/maintenance/${amoCode}/${department}/qms/audits/closeout/cars`],
      },
      {
        id: "evidence-library",
        label: "Evidence Library",
        to: `/maintenance/${amoCode}/${department}/qms/evidence`,
        prefixes: [`/maintenance/${amoCode}/${department}/qms/evidence/`],
      },
    ],
    [amoCode, department]
  );

  const actions = (
    <div className="qms-nav__items" role="tablist" aria-label="Audit planner and viewer pages">
      {links.map((link) => {
        const active =
          location.pathname === link.to ||
          location.pathname.startsWith(`${link.to}/`) ||
          (link.prefixes ?? []).some((prefix) => location.pathname.startsWith(prefix));
        return (
          <button
            key={link.id}
            type="button"
            className={`qms-nav__link${active ? " qms-nav__link--active" : ""}`}
            onClick={() => navigate(link.to)}
            aria-current={active ? "page" : undefined}
          >
            <span className="qms-nav__label">{link.label}</span>
          </button>
        );
      })}
    </div>
  );

  return (
    <QMSLayout amoCode={amoCode} department={department} title={title} subtitle={subtitle} actions={actions}>
      {children}
    </QMSLayout>
  );
};

export default QualityAuditsSectionLayout;
