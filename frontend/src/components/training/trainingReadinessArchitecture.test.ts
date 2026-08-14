import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const source = (relativePath: string) => readFileSync(resolve(process.cwd(), relativePath), "utf8");

describe("Training readiness architecture", () => {
  it("does not embed the legacy TrainingCompetencePage in canonical Training OS routes", () => {
    const page = source("src/pages/training/TrainingOperatingSystemPage.tsx");
    expect(page).not.toContain("TrainingCompetencePage");
    for (const workspace of ["TrainingPeopleWorkspace", "TrainingRequirementsWorkspace", "TrainingSessionPlanner", "TrainingCertificatesWorkspace", "TrainingReportsWorkspace"]) {
      expect(page).toContain(workspace);
    }
  });

  it("keeps explicit imports and setup modes visible from route-owned workspaces", () => {
    const people = source("src/components/training/TrainingPeopleWorkspace.tsx");
    const requirements = source("src/components/training/TrainingRequirementsWorkspace.tsx");
    const setup = source("src/components/training/TrainingSetupWorkspace.tsx");
    expect(people).toContain("Import people / history");
    expect(requirements).toContain("Import course / matrix");
    expect(setup).toContain('"BLANK"');
    expect(setup).toContain('"TEMPLATE_PACK"');
    expect(setup).toContain('"WORKBOOK"');
  });

  it("renders source outages as Unknown and provides server pagination", () => {
    const people = source("src/components/training/TrainingPeopleWorkspace.tsx");
    const controlRoom = source("src/pages/training/TrainingOperatingSystemPage.tsx");
    expect(people).toContain("Unknown");
    expect(people).toContain("has_more");
    expect(controlRoom).toContain('queue.count == null ? "?"');
  });

  it("keeps every personnel row linked to the canonical individual training record", () => {
    const people = source("src/components/training/TrainingPeopleWorkspace.tsx");
    const routes = source("src/portalRoutes.tsx");
    expect(people).toContain("buildCanonicalRoute.qmsTrainingPerson");
    expect(people).toContain("openRecord(row)");
    expect(routes).toContain('/training/competence/people/:userId/*');
    expect(routes).toContain("<QMSTrainingUserPage />");
  });

  it("exposes invitation delivery, controlled workflows and retained report jobs", () => {
    expect(source("src/components/training/TrainingSessionPlanner.tsx")).toContain("delivery_status");
    expect(source("src/components/training/TrainingWorkflowWorkspace.tsx")).toContain("QAM_51_INDUCTION");
    expect(source("src/components/training/TrainingReportsWorkspace.tsx")).toContain("source_cutoff_at");
    expect(source("src/components/training/MyTrainingTaskInbox.tsx")).toContain("listMyTrainingTasks");
  });

  it("keeps governed imports, report downloads and certificate batches operable after drawers close", () => {
    expect(source("src/components/training/TrainingSetupWorkspace.tsx")).toContain("Workbook import history");
    expect(source("src/components/training/TrainingSetupWorkspace.tsx")).toContain("downloadTrainingWorkbookTemplate");
    expect(source("src/components/training/TrainingReportsWorkspace.tsx")).toContain("downloadTrainingReportJob");
    expect(source("src/components/training/TrainingCertificatesWorkspace.tsx")).toContain("listCertificateEligibility");
    expect(source("src/components/training/TrainingCertificatesWorkspace.tsx")).toContain("batchIssueTrainingCertificates");
  });

  it("keeps the completed workbook result visible and exposes secure account onboarding", () => {
    const dialog = source("src/components/training/TrainingWorkbookImportDialog.tsx");
    const operatingPage = source("src/pages/training/TrainingOperatingSystemPage.tsx");
    expect(dialog).toContain("Import completed successfully");
    expect(dialog).toContain("No default password is issued or displayed");
    expect(dialog).toContain("buildCanonicalRoute.adminUserDetail");
    expect(dialog).toContain("New accounts awaiting onboarding");
    expect(operatingPage).toContain('onCompleted={async () => { await load(); }}');
    expect(operatingPage).not.toContain('onCompleted={async () => { setWorkbookImportOpen(false); await load(); }}');
  });
});
