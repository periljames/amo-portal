import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import RecordTable from "./RecordTable";

describe("bounded operational register table", () => {
  it("renders usable rows and headers immediately without a grid startup or loader", () => {
    const html = renderToStaticMarkup(<RecordTable label="Findings" rows={[{ id: "a", name: "QAR/006-F-001" }]} columns={[{ headerName: "Finding", field: "name", minWidth: 100 }]} />);
    expect(html).toContain('aria-label="Findings"');
    expect(html).toContain('scope="col"');
    expect(html).toContain("QAR/006-F-001");
    expect(html).not.toContain("ag-root");
    expect(html).not.toContain("inline-loading");
  });
  it("keeps workflow links, custom classifications and formatted values", () => {
    const html = renderToStaticMarkup(<RecordTable label="Audits" rows={[{ id: "a", title: "Maintenance" }]} columns={[
      { headerName: "Audit", cellRenderer: ({ data }: { data: { title: string } }) => <a href="/audit/a">{data.title}</a> },
      { headerName: "Class", valueGetter: () => "LEVEL_4", valueFormatter: ({ value }) => value === "LEVEL_4" ? "Observation" : "" },
    ]} />);
    expect(html).toContain('href="/audit/a"');
    expect(html).toContain("Maintenance");
    expect(html).toContain("Observation");
  });
  it("uses an explicit loading state only when no rows exist", () => {
    const html = renderToStaticMarkup(<RecordTable label="Audits" rows={[]} columns={[{ headerName: "Audit" }]} loading />);
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("inline-loading");
    expect(html).not.toContain("No records");
  });
});
