from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def read(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_procurement_workspace_is_split_and_canonical():
    module = read("pages/procurement/ProcurementModule.tsx")
    shared = read("pages/procurement/procurementUiShared.tsx")
    router = read("router.tsx")
    assert "ProcurementSections" in module
    assert "ProcurementForms" in module
    assert "ProcurementDocumentCenter" in module
    assert 'activeDepartment="procurement"' in module
    assert 'parts[2] === "procurement"' in router
    assert 'parts[2] === "procurement" || parts[2] === "stores"' not in router
    for section in ["Command", "Requests", "Sourcing", "Orders", "Receiving", "Suppliers", "Quality Control", "Documents"]:
        assert section in shared


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
