import React, { useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { CalendarDays, Files, Gauge, TableProperties, Trash2 } from "lucide-react";
import AuditPageShell, { type AuditShellNavItem } from "../../components/QMS/AuditPageShell";
import { ResponsiveSegmentedControl } from "../../components/QMS/ResponsiveSegmentedControl";
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
        id: "dashboard",
        label: "Dash",
        shortLabel: "Dash",
        icon: Gauge,
        href: `/maintenance/${amoCode}/quality/audits/dashboard`,
        active: location.pathname === `/maintenance/${amoCode}/quality/audits` || location.pathname === `/maintenance/${amoCode}/quality/audits/dashboard`,
      },
      {
        id: "plan-schedule",
        label: "Planner",
        shortLabel: "Planner",
        icon: CalendarDays,
        href: `/maintenance/${amoCode}/quality/audits/plan?view=calendar`,
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/plan` || location.pathname === `/maintenance/${amoCode}/quality/audits/schedule`,
      },
      {
        id: "register",
        label: "Register",
        shortLabel: "Register",
        icon: TableProperties,
        href: `/maintenance/${amoCode}/quality/audits/register?tab=findings`,
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/register`,
      },
      {
        id: "evidence-library",
        label: "Evidence",
        shortLabel: "Evidence",
        icon: Files,
        href: `/maintenance/${amoCode}/quality/evidence-vault`,
        active: location.pathname.startsWith(`/maintenance/${amoCode}/quality/evidence-vault`),
      },
      {
        id: "bin",
        label: "Bin",
        shortLabel: "Bin",
        icon: Trash2,
        href: `/maintenance/${amoCode}/quality/audits/bin`,
        active: location.pathname === `/maintenance/${amoCode}/quality/audits/bin`,
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
        { label: "QMS", onClick: () => navigate(`/maintenance/${amoCode}/quality`) },
        { label: "Audits", onClick: () => navigate(`/maintenance/${amoCode}/quality/audits`) },
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
          onChange={(value: string) => {
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
