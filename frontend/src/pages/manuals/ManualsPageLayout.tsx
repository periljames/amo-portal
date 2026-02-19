import type { PropsWithChildren, ReactNode } from "react";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { useManualRouteContext } from "./context";

type Props = PropsWithChildren<{
  title: string;
  actions?: ReactNode;
}>;

export default function ManualsPageLayout({ title, actions, children }: Props) {
  const { amoCode, department } = useManualRouteContext();

  const content = (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {actions}
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
