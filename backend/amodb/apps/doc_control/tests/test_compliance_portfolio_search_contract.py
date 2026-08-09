from pathlib import Path


ROUTER = Path(__file__).resolve().parents[1] / "workspace_compliance_portfolio_router.py"


def test_external_source_search_uses_one_combined_predicate():
    source = ROUTER.read_text(encoding="utf-8")
    external_block = source.split('elif view == "external-sources":', 1)[1].split('elif view == "relationships":', 1)[0]

    # Provider/authority-only terms must not first be AND-restricted to the
    # internal document code/title. The external-source branch owns one OR
    # predicate spanning both document identity and source identity fields.
    assert "_document_search(query, q, manual_models.Manual)" not in external_block
    for field in (
        "manual_models.Manual.code.ilike(needle)",
        "manual_models.Manual.title.ilike(needle)",
        "dm.ExternalDocumentSource.provider.ilike(needle)",
        "dm.ExternalDocumentSource.authority.ilike(needle)",
    ):
        assert field in external_block

    assert external_block.count("if q and q.strip():") == 1
