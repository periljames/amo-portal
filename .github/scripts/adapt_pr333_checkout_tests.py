from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"Expected one occurrence in {path}: {old!r}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    path = "backend/amodb/apps/platform/tests/test_saas_final_review_safeguards.py"
    replace_exact(
        path,
        '''def test_checkout_completion_rejects_non_portal_session():
    event = _checkout_event("cs_external")
    account = _pending_checkout_account()
    db = MagicMock()
    db.get.return_value = event
    query = MagicMock()
    query.filter.return_value.first.return_value = account
    db.query.return_value = query

    with pytest.raises(ValueError, match="does not match the pending portal checkout"):
        saas_worker._process_stripe_webhook(db, _webhook_job())
''',
        '''def test_checkout_completion_rejects_non_portal_session(monkeypatch: pytest.MonkeyPatch):
    event = _checkout_event("cs_external")
    account = _pending_checkout_account()
    db = MagicMock()
    db.get.return_value = event
    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    monkeypatch.setattr(
        saas_worker,
        "_checkout_price",
        lambda *_args, **_kwargs: SimpleNamespace(
            id="price-row-1", module_code="quality", external_price_ref="price_stripe_1"
        ),
    )

    with pytest.raises(ValueError, match="does not match the pending portal checkout"):
        saas_worker._process_stripe_webhook(db, _webhook_job())
''',
    )
    replace_exact(
        path,
        '''    query = MagicMock()
    query.filter.return_value.first.return_value = account
    db.query.return_value = query
    set_module_state = MagicMock()
''',
        '''    monkeypatch.setattr(saas_worker, "_stripe_billing_account", lambda *_args, **_kwargs: account)
    monkeypatch.setattr(saas_worker, "_checkout_price", lambda *_args, **_kwargs: price)
    set_module_state = MagicMock()
''',
    )


if __name__ == "__main__":
    main()
