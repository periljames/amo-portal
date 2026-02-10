import React from "react";

type Props = {
  departmentLabel: string;
};

const DepartmentLandingScaffold: React.FC<Props> = ({ departmentLabel }) => {
  return (
    <section className="department-landing" aria-label={`${departmentLabel} landing`}>
      <div className="department-landing__card">
        <h1 className="department-landing__title">{departmentLabel} dashboard</h1>
        <p className="department-landing__subtitle">
          Department dashboard coming soon. Use the module launcher or sidebar to access active tools.
        </p>
      </div>
    </section>
  );
};

export default DepartmentLandingScaffold;
