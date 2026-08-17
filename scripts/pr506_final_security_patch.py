from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Expected patch anchor not found in {path}: {old[:180]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


# The durable notification outbox supersedes fire-and-forget external sends.
# Keep an explicit break-glass compatibility flag for installations that have
# not yet enabled tenant notification policy.
replace_once(
    "backend/amodb/apps/training/router.py",
    'def _maybe_send_email(background_tasks: BackgroundTasks, to_email: Optional[str], subject: str, body: str) -> None:\n    """\n    Optional email hook (safe-by-default).',
    'def _maybe_send_email(background_tasks: BackgroundTasks, to_email: Optional[str], subject: str, body: str) -> None:\n    """\n    Legacy immediate email hook. Durable Training notification dispatch is the default.\n\n    Set TRAINING_LEGACY_IMMEDIATE_EXTERNAL_DELIVERY=1 only as an explicit\n    compatibility escape hatch while migrating tenant notification policy.\n    """\n    if str(os.getenv("TRAINING_LEGACY_IMMEDIATE_EXTERNAL_DELIVERY", "0")).strip().lower() not in {"1", "true", "yes"}:\n        return\n    """\n    Optional email hook (safe-by-default).',
)
replace_once(
    "backend/amodb/apps/training/router.py",
    'def _maybe_send_whatsapp(background_tasks: BackgroundTasks, to_phone: Optional[str], message: str) -> None:\n    """\n    Optional WhatsApp hook (safe-by-default).',
    'def _maybe_send_whatsapp(background_tasks: BackgroundTasks, to_phone: Optional[str], message: str) -> None:\n    """\n    Legacy immediate WhatsApp hook. Durable Training notification dispatch is the default.\n\n    Set TRAINING_LEGACY_IMMEDIATE_EXTERNAL_DELIVERY=1 only as an explicit\n    compatibility escape hatch while migrating tenant notification policy.\n    """\n    if str(os.getenv("TRAINING_LEGACY_IMMEDIATE_EXTERNAL_DELIVERY", "0")).strip().lower() not in {"1", "true", "yes"}:\n        return\n    """\n    Optional WhatsApp hook (safe-by-default).',
)

# A department scope is not itself authorization. Restrict Team Training to
# actual management/admin roles or existing Training editors.
replace_once(
    "backend/amodb/apps/training/workflow_completion.py",
    '    @router.get("/workspace/manager")\n    def manager_workspace(\n        db: Session = Depends(get_read_db),\n        current_user: account_models.User = Depends(get_current_active_user),\n    ):\n        return workspace_payload(db, current_user, coordinator=False)',
    '    @router.get("/workspace/manager")\n    def manager_workspace(\n        db: Session = Depends(get_read_db),\n        current_user: account_models.User = Depends(get_current_active_user),\n    ):\n        manager_roles = {\n            "SUPERUSER",\n            "AMO_ADMIN",\n            "ACCOUNTABLE_EXECUTIVE",\n            "BASE_MAINTENANCE_MANAGER",\n            "LINE_MAINTENANCE_MANAGER",\n            "WORKSHOP_MANAGER",\n            "QUALITY_MANAGER",\n            "SAFETY_MANAGER",\n            "FINANCE_MANAGER",\n            "STORES_MANAGER",\n        }\n        if not router_module._is_training_editor(current_user) and _enum(getattr(current_user, "role", None)) not in manager_roles:\n            raise HTTPException(status_code=403, detail="Management permission is required for Team Training.")\n        return workspace_payload(db, current_user, coordinator=False)',
)

print("PR #506 final security patch applied.")
