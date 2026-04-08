import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from "@tremor/react";
import { FileSearch, FileText, Send, SplitSquareVertical } from "lucide-react";

import {
  getMasterList,
  getRevisionRead,
  getRevisionWorkflow,
  listManuals,
  listRevisions,
  searchPublicationSelector,
  submitPublicationChangeRequest,
  subscribeManualsUpdated,
  type ManualRevision,
  type ManualSummary,
  type PublicationSelectorItem,
} from "../../services/manuals";
import { getCachedUser } from "../../services/auth";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";
import DocumentReader from "./DocumentReader";
import "./manualsDashboard.css";

type MasterRow = { manual_id: string; pending_ack_count: number; current_status: string; current_revision: string | null };
type ReaderState = { mode: "section" | "continuous"; activeSectionId: string; scrollTop: number };

type PcrFormState = {
  requestedByFirstName: string;
  requestedByLastName: string;
  email: string;
  phone: string;
  manualId: string;
  partNumber: string;
  manualType: string;
  title: string;
  model: string;
  publicationDate: string;
  revisionNumber: string;
  ataChapter: string;
  section: string;
  subSection: string;
  figure: string;
  pageNumber: string;
  artFigure: string;
  other: string;
  otherPublicationsAffected: string;
  suggestionForChange: string;
  requestUpdates: boolean;
};

function splitName(fullName: string | undefined | null) {
  const parts = (fullName || "").trim().split(/\s+/).filter(Boolean);
  return {
    first: parts[0] || "",
    last: parts.length > 1 ? parts.slice(1).join(" ") : "",
  };
}


export function resolveNextRevisionId<T extends { id: string }>(previousRevisionId: string, rows: T[]): string {
  if (previousRevisionId && rows.some((row) => row.id === previousRevisionId)) return previousRevisionId;
  return rows[0]?.id || "";
}

function inferAtaChapter(label?: string | null): string {
  const match = String(label || "").match(/(\d{2})/);
  return match ? match[1] : "";
}

export default function ManualsDashboardPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useManualRouteContext();
  const user = getCachedUser();
  const requestor = splitName((user as any)?.full_name || (user as any)?.name);

  const [activeTab, setActiveTab] = useState(0);
  const [manuals, setManuals] = useState<ManualSummary[]>([]);
  const [masterRows, setMasterRows] = useState<MasterRow[]>([]);
  const [revisions, setRevisions] = useState<ManualRevision[]>([]);
  const [activeManualId, setActiveManualId] = useState<string>("");
  const [activeRevisionId, setActiveRevisionId] = useState<string>("");
  const [readPayload, setReadPayload] = useState<any | null>(null);
  const [workflow, setWorkflow] = useState<any | null>(null);
  const [librarySearch, setLibrarySearch] = useState("");
  const [selectorQuery, setSelectorQuery] = useState("");
  const [selectorItems, setSelectorItems] = useState<PublicationSelectorItem[]>([]);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [selectorLoading, setSelectorLoading] = useState(false);
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "done" | "error">("idle");
  const [submitMessage, setSubmitMessage] = useState("");
  const [readerState, setReaderState] = useState<ReaderState>({ mode: "section", activeSectionId: "", scrollTop: 0 });
  const [pcrForm, setPcrForm] = useState<PcrFormState>({
    requestedByFirstName: requestor.first,
    requestedByLastName: requestor.last,
    email: (user as any)?.email || "",
    phone: (user as any)?.phone || (user as any)?.secondary_phone || "",
    manualId: "",
    partNumber: "",
    manualType: "",
    title: "",
    model: "",
    publicationDate: "",
    revisionNumber: "",
    ataChapter: "",
    section: "",
    subSection: "",
    figure: "",
    pageNumber: "",
    artFigure: "",
    other: "",
    otherPublicationsAffected: "",
    suggestionForChange: "",
    requestUpdates: true,
  });

  const refresh = () => {
    if (!tenant) return;
    listManuals(tenant)
      .then((data) => {
        setManuals(data);
        const first = data[0]?.id || "";
        setActiveManualId((prev) => prev || first);
      })
      .catch(() => setManuals([]));

    getMasterList(tenant)
      .then((rows) => setMasterRows(rows as MasterRow[]))
      .catch(() => setMasterRows([]));
  };

  useEffect(() => {
    refresh();
  }, [tenant]);

  useEffect(() => {
    if (!tenant) return;
    const unsubscribe = subscribeManualsUpdated((detail) => {
      if (detail.tenantSlug === tenant) refresh();
    });
    return unsubscribe;
  }, [tenant]);

  useEffect(() => {
    if (!tenant || !activeManualId) {
      setRevisions([]);
      return;
    }
    listRevisions(tenant, activeManualId)
      .then((rows) => {
        setRevisions(rows);
        setActiveRevisionId((prev) => resolveNextRevisionId(prev, rows));
      })
      .catch(() => setRevisions([]));
  }, [tenant, activeManualId]);

  useEffect(() => {
    if (!tenant || !activeManualId || !activeRevisionId) {
      setReadPayload(null);
      setWorkflow(null);
      return;
    }
    getRevisionRead(tenant, activeManualId, activeRevisionId).then(setReadPayload).catch(() => setReadPayload(null));
    getRevisionWorkflow(tenant, activeManualId, activeRevisionId).then(setWorkflow).catch(() => setWorkflow(null));
  }, [tenant, activeManualId, activeRevisionId]);

  useEffect(() => {
    const activeManual = manuals.find((row) => row.id === activeManualId);
    const activeRevision = revisions.find((row) => row.id === activeRevisionId);
    const firstSection = readPayload?.sections?.[0];
    setPcrForm((prev) => ({
      ...prev,
      manualId: activeManualId || prev.manualId,
      partNumber: activeManual?.code || prev.partNumber,
      manualType: activeManual?.manual_type || prev.manualType,
      title: activeManual?.title || prev.title,
      publicationDate: prev.publicationDate || new Date().toISOString().slice(0, 10),
      revisionNumber: activeRevision?.rev_number || prev.revisionNumber,
      ataChapter: prev.ataChapter || inferAtaChapter(firstSection?.heading),
      section: prev.section || firstSection?.heading || "",
    }));
  }, [activeManualId, activeRevisionId, manuals, readPayload?.sections, revisions]);

  const filteredManuals = useMemo(() => {
    const needle = librarySearch.trim().toLowerCase();
    if (!needle) return manuals;
    return manuals.filter((manual) => `${manual.code} ${manual.title} ${manual.manual_type}`.toLowerCase().includes(needle));
  }, [librarySearch, manuals]);

  const activeManual = manuals.find((row) => row.id === activeManualId) || null;
  const activeRevision = revisions.find((row) => row.id === activeRevisionId) || null;
  const activeMasterRow = masterRows.find((row) => row.manual_id === activeManualId) || null;

  const selectorSearch = async () => {
    if (!tenant) return;
    setSelectorLoading(true);
    try {
      const rows = await searchPublicationSelector(tenant, { q: selectorQuery });
      setSelectorItems(rows);
    } finally {
      setSelectorLoading(false);
    }
  };

  useEffect(() => {
    if (!selectorOpen || !tenant) return;
    void selectorSearch();
  }, [selectorOpen, tenant]);

  const pickPublication = (item: PublicationSelectorItem) => {
    setActiveManualId(item.manual_id);
    setPcrForm((prev) => ({
      ...prev,
      manualId: item.manual_id,
      partNumber: item.code,
      manualType: item.manual_type,
      title: item.title,
      model: item.model || prev.model,
      publicationDate: item.publication_date || prev.publicationDate,
      revisionNumber: item.current_revision || prev.revisionNumber,
    }));
    setSelectorOpen(false);
    setActiveTab(2);
  };

  const submitPcr = async () => {
    if (!tenant || !pcrForm.manualId || !pcrForm.partNumber || !pcrForm.revisionNumber || !pcrForm.suggestionForChange.trim()) {
      setSubmitState("error");
      setSubmitMessage("Complete the publication, revision, and suggestion fields before submitting.");
      return;
    }
    setSubmitState("submitting");
    setSubmitMessage("");
    try {
      const response = await submitPublicationChangeRequest(tenant, {
        requested_by_first_name: pcrForm.requestedByFirstName,
        requested_by_last_name: pcrForm.requestedByLastName,
        email: pcrForm.email,
        phone: pcrForm.phone,
        manual_id: pcrForm.manualId,
        part_number: pcrForm.partNumber,
        manual_type: pcrForm.manualType,
        title: pcrForm.title,
        model: pcrForm.model || null,
        publication_date: pcrForm.publicationDate || null,
        revision_number: pcrForm.revisionNumber,
        ata_chapter: pcrForm.ataChapter || null,
        section: pcrForm.section || null,
        sub_section: pcrForm.subSection || null,
        figure: pcrForm.figure || null,
        page_number: pcrForm.pageNumber || null,
        art_figure: pcrForm.artFigure || null,
        other: pcrForm.other || null,
        other_publications_affected: pcrForm.otherPublicationsAffected || null,
        suggestion_for_change: pcrForm.suggestionForChange,
        request_updates: pcrForm.requestUpdates,
      });
      setSubmitState("done");
      setSubmitMessage(`${response.message} Ref ${response.id}`);
      setPcrForm((prev) => ({ ...prev, suggestionForChange: "", otherPublicationsAffected: "", other: "" }));
    } catch (error) {
      setSubmitState("error");
      setSubmitMessage(error instanceof Error ? error.message : "Unable to submit the change request.");
    }
  };

  return (
    <ManualsPageLayout
      title="Technical Publications"
      subtitle="Read, route, and raise publication change requests without extra clutter."
      actions={
        <div className="manuals-header-actions">
          <button className="manuals-link-btn" onClick={() => setSelectorOpen(true)}>
            <FileSearch size={16} />
            Select publication
          </button>
          <button className="manuals-link-btn" onClick={() => navigate(`${basePath}/master-list`)}>
            <SplitSquareVertical size={16} />
            Master list
          </button>
        </div>
      }
    >
      <TabGroup index={activeTab} onIndexChange={setActiveTab}>
        <TabList className="manuals-top-tabs">
          <Tab>Library</Tab>
          <Tab>Reader</Tab>
          <Tab>Publication Change Request</Tab>
        </TabList>
        <TabPanels>
          <TabPanel>
            <div className="manuals-shell-grid">
              <aside className="manuals-pane manuals-pane--catalog">
                <div className="manuals-pane__header">
                  <strong>Manual library</strong>
                  <span>{filteredManuals.length}</span>
                </div>
                <input className="manuals-search" placeholder="Search code or title" value={librarySearch} onChange={(e) => setLibrarySearch(e.target.value)} />
                <div className="manuals-scroll-list">
                  {filteredManuals.map((manual) => (
                    <button key={manual.id} className={`manuals-library-row${manual.id === activeManualId ? " active" : ""}`} onClick={() => setActiveManualId(manual.id)}>
                      <strong>{manual.code}</strong>
                      <span>{manual.title}</span>
                      <small>{manual.manual_type}</small>
                    </button>
                  ))}
                </div>
              </aside>

              <section className="manuals-pane manuals-pane--content">
                <div className="manuals-pane__header">
                  <div>
                    <strong>{activeManual?.title || "Select a manual"}</strong>
                    <p className="manuals-muted">{activeManual?.code || ""} {activeManual?.manual_type ? `· ${activeManual.manual_type}` : ""}</p>
                  </div>
                  {activeManual && activeRevision ? (
                    <button className="manuals-primary-btn" onClick={() => navigate(`${basePath}/${activeManual.id}/rev/${activeRevision.id}/read`)}>
                      <FileText size={16} />
                      Open reader
                    </button>
                  ) : null}
                </div>
                <div className="manuals-summary-grid">
                  <div className="manuals-summary-card"><span>Status</span><strong>{activeMasterRow?.current_status || "No published revision"}</strong></div>
                  <div className="manuals-summary-card"><span>Current revision</span><strong>{activeMasterRow?.current_revision || "—"}</strong></div>
                  <div className="manuals-summary-card"><span>Pending acknowledgements</span><strong>{activeMasterRow?.pending_ack_count ?? 0}</strong></div>
                </div>
                <div className="manuals-revision-table-wrap">
                  <table className="manuals-data-table">
                    <thead>
                      <tr>
                        <th>Revision</th>
                        <th>Issue</th>
                        <th>Status</th>
                        <th>Effective</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {revisions.map((revision) => (
                        <tr key={revision.id} className={revision.id === activeRevisionId ? "is-active" : ""}>
                          <td>Rev {revision.rev_number}</td>
                          <td>{revision.issue_number || "—"}</td>
                          <td>{revision.status_enum}</td>
                          <td>{revision.effective_date || "—"}</td>
                          <td>
                            <button className="manuals-table-link" onClick={() => setActiveRevisionId(revision.id)}>Preview</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          </TabPanel>

          <TabPanel>
            <div className="manuals-reader-preview-shell">
              <div className="manuals-reader-preview-header">
                <div>
                  <strong>{activeManual?.title || "Reader preview"}</strong>
                  <p className="manuals-muted">{activeRevision ? `Rev ${activeRevision.rev_number}` : "Choose a manual and revision from the library."}</p>
                </div>
                {activeManual && activeRevision ? (
                  <button className="manuals-primary-btn" onClick={() => navigate(`${basePath}/${activeManual.id}/rev/${activeRevision.id}/read`)}>
                    Open full reader
                  </button>
                ) : null}
              </div>
              <DocumentReader
                file={null}
                fallbackSections={readPayload?.sections || []}
                fallbackBlocks={readPayload?.blocks || []}
                meta={{
                  revisionNumber: activeRevision?.rev_number,
                  issueNumber: activeRevision?.issue_number,
                  approvalStatus: workflow?.status || activeRevision?.status_enum,
                  pendingAcknowledgements: activeMasterRow?.pending_ack_count || 0,
                }}
                readerState={readerState}
                onReaderStateChange={(next) => setReaderState((prev) => ({ ...prev, ...next }))}
              />
            </div>
          </TabPanel>

          <TabPanel>
            <div className="manuals-pcr-layout">
              <section className="manuals-pane manuals-pane--content">
                <div className="manuals-pane__header">
                  <div>
                    <strong>Publication Change Request</strong>
                    <p className="manuals-muted">Only the publication and location fields available from the current reader context are shown.</p>
                  </div>
                  <button className="manuals-link-btn" onClick={() => setSelectorOpen(true)}>Select publication</button>
                </div>
                <div className="manuals-pcr-form">
                  <div className="manuals-pcr-section">
                    <h3>Requested by</h3>
                    <div className="manuals-pcr-grid manuals-pcr-grid--4">
                      <label><span>First name</span><input value={pcrForm.requestedByFirstName} onChange={(e) => setPcrForm((prev) => ({ ...prev, requestedByFirstName: e.target.value }))} /></label>
                      <label><span>Last name</span><input value={pcrForm.requestedByLastName} onChange={(e) => setPcrForm((prev) => ({ ...prev, requestedByLastName: e.target.value }))} /></label>
                      <label><span>Email address</span><input type="email" value={pcrForm.email} onChange={(e) => setPcrForm((prev) => ({ ...prev, email: e.target.value }))} /></label>
                      <label><span>Phone number</span><input value={pcrForm.phone} onChange={(e) => setPcrForm((prev) => ({ ...prev, phone: e.target.value }))} /></label>
                    </div>
                  </div>

                  <div className="manuals-pcr-section">
                    <h3>Publication affected</h3>
                    <div className="manuals-pcr-grid manuals-pcr-grid--4">
                      <label><span>Part number</span><input value={pcrForm.partNumber} onChange={(e) => setPcrForm((prev) => ({ ...prev, partNumber: e.target.value }))} /></label>
                      <label><span>Manual type</span><input value={pcrForm.manualType} onChange={(e) => setPcrForm((prev) => ({ ...prev, manualType: e.target.value }))} /></label>
                      <label><span>Title</span><input value={pcrForm.title} onChange={(e) => setPcrForm((prev) => ({ ...prev, title: e.target.value }))} /></label>
                      <label><span>Model</span><input value={pcrForm.model} onChange={(e) => setPcrForm((prev) => ({ ...prev, model: e.target.value }))} /></label>
                      <label><span>Publication date</span><input type="date" value={pcrForm.publicationDate} onChange={(e) => setPcrForm((prev) => ({ ...prev, publicationDate: e.target.value }))} /></label>
                      <label><span>Revision number</span><input value={pcrForm.revisionNumber} onChange={(e) => setPcrForm((prev) => ({ ...prev, revisionNumber: e.target.value }))} /></label>
                    </div>
                  </div>

                  <div className="manuals-pcr-section">
                    <h3>Location</h3>
                    <div className="manuals-pcr-grid manuals-pcr-grid--4">
                      <label><span>ATA chapter</span><input value={pcrForm.ataChapter} onChange={(e) => setPcrForm((prev) => ({ ...prev, ataChapter: e.target.value }))} /></label>
                      <label><span>Section</span><input value={pcrForm.section} onChange={(e) => setPcrForm((prev) => ({ ...prev, section: e.target.value }))} /></label>
                      <label><span>Sub section</span><input value={pcrForm.subSection} onChange={(e) => setPcrForm((prev) => ({ ...prev, subSection: e.target.value }))} /></label>
                      <label><span>Figure</span><input value={pcrForm.figure} onChange={(e) => setPcrForm((prev) => ({ ...prev, figure: e.target.value }))} /></label>
                      <label><span>Page number</span><input value={pcrForm.pageNumber} onChange={(e) => setPcrForm((prev) => ({ ...prev, pageNumber: e.target.value }))} /></label>
                      <label><span>Art/Figure</span><input value={pcrForm.artFigure} onChange={(e) => setPcrForm((prev) => ({ ...prev, artFigure: e.target.value }))} /></label>
                      <label className="manuals-pcr-span-2"><span>Other</span><input value={pcrForm.other} onChange={(e) => setPcrForm((prev) => ({ ...prev, other: e.target.value }))} /></label>
                    </div>
                  </div>

                  <div className="manuals-pcr-section">
                    <h3>Change requested</h3>
                    <div className="manuals-pcr-grid">
                      <label className="manuals-pcr-span-2"><span>Other publications affected</span><textarea rows={3} value={pcrForm.otherPublicationsAffected} onChange={(e) => setPcrForm((prev) => ({ ...prev, otherPublicationsAffected: e.target.value }))} /></label>
                      <label className="manuals-pcr-span-2"><span>Suggestion for change</span><textarea rows={6} value={pcrForm.suggestionForChange} onChange={(e) => setPcrForm((prev) => ({ ...prev, suggestionForChange: e.target.value }))} /></label>
                    </div>
                    <label className="manuals-checkbox-row"><input type="checkbox" checked={pcrForm.requestUpdates} onChange={(e) => setPcrForm((prev) => ({ ...prev, requestUpdates: e.target.checked }))} /> Receive email updates for this request</label>
                  </div>

                  {submitMessage ? <div className={`manuals-inline-state manuals-inline-state--${submitState === "done" ? "success" : submitState === "error" ? "error" : "muted"}`}>{submitMessage}</div> : null}

                  <div className="manuals-form-actions">
                    <button className="manuals-link-btn" onClick={() => setPcrForm((prev) => ({ ...prev, otherPublicationsAffected: "", suggestionForChange: "", other: "" }))}>Reset note fields</button>
                    <button className="manuals-primary-btn" disabled={submitState === "submitting"} onClick={submitPcr}>
                      <Send size={16} />
                      {submitState === "submitting" ? "Submitting…" : "Submit PCR"}
                    </button>
                  </div>
                </div>
              </section>
            </div>
          </TabPanel>
        </TabPanels>
      </TabGroup>

      {selectorOpen ? (
        <div className="manuals-modal-backdrop" role="presentation" onClick={() => setSelectorOpen(false)}>
          <div className="manuals-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="manuals-modal__header">
              <strong>Select publication</strong>
              <button className="manuals-link-btn" onClick={() => setSelectorOpen(false)}>Close</button>
            </div>
            <div className="manuals-modal__filters">
              <input className="manuals-search" placeholder="Search publication" value={selectorQuery} onChange={(e) => setSelectorQuery(e.target.value)} />
              <button className="manuals-primary-btn" onClick={() => void selectorSearch()}>Search</button>
            </div>
            <div className="manuals-revision-table-wrap">
              <table className="manuals-data-table">
                <thead>
                  <tr>
                    <th>Part number</th>
                    <th>Type</th>
                    <th>Title</th>
                    <th>Current rev</th>
                    <th>Pub date</th>
                  </tr>
                </thead>
                <tbody>
                  {selectorLoading ? <tr><td colSpan={5}>Loading…</td></tr> : null}
                  {!selectorLoading && selectorItems.map((item) => (
                    <tr key={item.manual_id} className="is-clickable" onClick={() => pickPublication(item)}>
                      <td>{item.code}</td>
                      <td>{item.manual_type}</td>
                      <td>{item.title}</td>
                      <td>{item.current_revision || "—"}</td>
                      <td>{item.publication_date || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </ManualsPageLayout>
  );
}
