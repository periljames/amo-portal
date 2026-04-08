import type { PropsWithChildren, ReactNode } from "react";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { useManualRouteContext } from "./context";

type Props = PropsWithChildren<{
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}>;

export default function ManualsPageLayout({ title, subtitle, actions, children }: Props) {
  const { amoCode, department } = useManualRouteContext();

  const content = (
    <div className="manuals-page-shell">
      <div className="manuals-page-shell__header">
        <div>
          <h1 className="manuals-page-shell__title">{title}</h1>
          {subtitle ? <p className="manuals-page-shell__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="manuals-page-shell__actions">{actions}</div> : null}
      </div>
      {children}
    </div>
  );

  if (!amoCode) return content;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department || "quality"}>
      {content}
    </DepartmentLayout>
  );
}
