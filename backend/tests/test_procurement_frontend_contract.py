from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_procurement_workspace_is_split_and_canonical():
    module = read("pages/procurement/ProcurementModule.tsx")
    navigation_model = read("pages/procurement/procurementUiModel.ts")
    router = read("router.tsx")
    assert "ProcurementSections" in module
    assert "ProcurementForms" in module
    assert "ProcurementDocumentCenter" in module
    assert 'activeDepartment="procurement"' in module
    assert 'parts[2] === "procurement"' in router
    assert 'parts[2] === "procurement" || parts[2] === "stores"' not in router
    for section in ["Command", "Requests", "Sourcing", "Orders", "Receiving", "Suppliers", "Quality Control", "Documents"]:
        assert section in navigation_model


def test_procurement_feedback_and_loading_are_accessible():
    module = read("pages/procurement/ProcurementModule.tsx")
    documents = read("pages/procurement/ProcurementDocumentCenter.tsx")
    toast = read("components/feedback/ToastProvider.tsx")
    styles = read("styles/procurement-workspace.css")
    assert "Promise.allSettled" in module
    assert 'role="alert"' in module
    assert 'role="status"' in documents
    assert 'aria-live="polite"' in documents
    assert 'aria-live={urgent ? "assertive" : "polite"}' in toast
    assert "prefers-reduced-motion" in styles
    assert "proc-table-skeleton" in styles
    assert "proc-upload-progress" in styles


def test_every_operational_register_exposes_evidence_linking():
    sections = read("pages/procurement/ProcurementSections.tsx")
    for entity in ["REQUISITION", "RFQ", "QUOTE", "PURCHASE_ORDER", "RECEIPT", "SUPPLIER", "QUALITY_HOLD"]:
        assert f'linkDocument("{entity}"' in sections


def test_evidence_register_pages_and_enforces_independent_quality_actions():
    module = read("pages/procurement/ProcurementModule.tsx")
    documents = read("pages/procurement/ProcurementDocumentCenter.tsx")
    service = read("services/procurement.ts")
    assert "PAGE_SIZE = 100" in documents
    assert "loadPage(documents.length, false)" in documents
    assert "Load older evidence" in documents
    assert "mergeUnique" in documents
    assert "document.is_quality_evidence" in documents
    assert 'document.verification_status === "PENDING"' in documents
    assert "document.uploaded_by_user_id" in documents
    assert "currentUserId={user?.id || null}" in module
    assert "offset?: number" in service
    assert "limit?: number" in service



def test_requisition_actions_match_backend_lifecycle():
    sections = read("pages/procurement/ProcurementSections.tsx")
    assert 'item.id, "TECHNICAL_REVIEW"' not in sections
    for action in ["SUBMIT", "TECHNICAL_APPROVE", "BUDGET_APPROVE", "APPROVE"]:
        assert f'item.id, "{action}"' in sections



def test_voiding_preserves_active_only_pagination_alignment():
    documents = read("pages/procurement/ProcurementDocumentCenter.tsx")
    assert 'mode === "VOID" && !includeVoid' in documents
    assert "current.filter((item) => item.id !== updated.id)" in documents
    assert "loadPage(documents.length, false)" in documents