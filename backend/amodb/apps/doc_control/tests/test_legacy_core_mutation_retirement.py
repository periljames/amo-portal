from pathlib import Path


def test_parallel_legacy_document_control_issuer_is_retired() -> None:
    root = Path(__file__).resolve().parents[5]
    guard = (root / "backend/amodb/apps/doc_control/workspace_compatibility_guard.py").read_text(encoding="utf-8")
    composition = (root / "backend/amodb/apps/doc_control/router.py").read_text(encoding="utf-8")

    assert "quarantine_legacy_core_mutations(core_router)" in composition
    assert "DOCUMENT_CONTROL_LEGACY_MUTATION_RETIRED" in guard
    assert 'mutation_methods = methods.intersection({"POST", "PUT", "PATCH", "DELETE"})' in guard
    assert "retained.append(route)" in guard

    assert "GET routes stay available during migration" in guard
