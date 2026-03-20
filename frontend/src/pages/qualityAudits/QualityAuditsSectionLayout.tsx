import React, { useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { CalendarDays, Files, TableProperties } from "lucide-react";
import AuditPageShell, { type AuditShellNavItem } from "../../components/qms/AuditPageShell";
import { ResponsiveSegmentedControl } from "../../components/qms/ResponsiveSegmentedControl";
import { getContext } from "../../services/auth";

type Props = {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  toolbar?: React.ReactNode;
};

const QualityAuditsSectionLayout: React.FC<Props> = ({ title, subtitle, children, toolbar }) => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const ctx = getContext();
  const navigate = useNavigate();
  const location = useLocation();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? "quality";

  const links = useMemo<AuditShellNavItem[]>(
    () => [
      {
        id: "plan-schedule",
        label: "Plan / Schedule",
        shortLabel: "Plan",
        icon: CalendarDays,
        href: `/maintenance/${amoCode}/${department}/qms/audits/schedules/calendar`,
        active:
          location.pathname.startsWith(`/maintenance/${amoCode}/${department}/qms/audits/schedules`) ||
          location.pathname === `/maintenance/${amoCode}/${department}/qms/audits/plan`,
      },
      {
        id: "register",
        label: "Register",
        shortLabel: "Register",
        icon: TableProperties,
        href: `/maintenance/${amoCode}/${department}/qms/audits/closeout/findings`,
        active:
          location.pathname.startsWith(`/maintenance/${amoCode}/${department}/qms/audits/closeout`) ||
          location.pathname === `/maintenance/${amoCode}/${department}/qms/audits/register`,
      },
      {
        id: "evidence-library",
        label: "Evidence Library",
        shortLabel: "Evidence",
        icon: Files,
        href: `/maintenance/${amoCode}/${department}/qms/evidence`,
        active: location.pathname.startsWith(`/maintenance/${amoCode}/${department}/qms/evidence`),
      },
    ],
    [amoCode, department, location.pathname]
  );

  const activeId = links.find((link) => link.active)?.id ?? links[0].id;

  return (
    <AuditPageShell
      amoCode={amoCode}
      department={department}
      title={title}
      subtitle={subtitle}
      breadcrumbs={[
        { label: "QMS", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms`) },
        { label: "Audits & Inspections", onClick: () => navigate(`/maintenance/${amoCode}/${department}/qms/audits`) },
        { label: title },
      ]}
      toolbar={toolbar}
      nav={
        <ResponsiveSegmentedControl
          label="Audit pages"
          value={activeId}
          options={links.map((link) => ({
            value: link.id,
            label: link.label,
            shortLabel: link.shortLabel,
            icon: link.icon,
            ariaLabel: link.label,
          }))}
          onChange={(value) => {
            const next = links.find((link) => link.id === value);
            if (next) navigate(next.href);
          }}
          compactIconsOnMobile
        />
      }
    >
      {children}
    </AuditPageShell>
  );
};

export default QualityAuditsSectionLayout;
