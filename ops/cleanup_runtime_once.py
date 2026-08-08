from pathlib import Path
import ast
import re


def remove_py_function(path: str, name: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)
    if node is None:
        return
    start = min([d.lineno for d in node.decorator_list], default=node.lineno) - 1
    lines = text.splitlines(True)
    end = node.end_lineno
    while end < len(lines) and not lines[end].strip():
        end += 1
    p.write_text("".join(lines[:start] + lines[end:]), encoding="utf-8")


def replace_py_function(path: str, name: str, replacement: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    tree = ast.parse(text)
    node = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name), None)
    if node is None:
        raise RuntimeError(f"missing {name} in {path}")
    lines = text.splitlines(True)
    p.write_text("".join(lines[: node.lineno - 1] + [replacement.rstrip() + "\n\n"] + lines[node.end_lineno :]), encoding="utf-8")


def remove_ts_function(text: str, name: str) -> str:
    marker = f"function {name}"
    pos = text.find(marker)
    if pos < 0:
        return text
    line_start = text.rfind("\n", 0, pos) + 1
    brace = text.find("{", pos)
    if brace < 0:
        raise RuntimeError(name)
    depth = 0
    i = brace
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                while end < len(text) and text[end] in " \t\r":
                    end += 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return text[:line_start] + text[end:]
        i += 1
    raise RuntimeError(f"unclosed {name}")


def remove_route_using(text: str, component: str) -> str:
    while component in text:
        hit = text.find(component)
        start = text.rfind("<Route", 0, hit)
        end = text.find("/>", hit)
        if start < 0 or end < 0:
            break
        text = text[:start] + text[end + 2 :]
    return text


def clean_eof(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


# Commercial module catalog owns product boundaries directly.
mc = Path("backend/amodb/apps/platform/module_commerce.py")
text = mc.read_text(encoding="utf-8")
text = text.replace(', "document_control_legacy"', "")
text = text.replace('"finance_inventory"', '"supply_chain_finance_suite"')
text = text.replace('        "legacy_compatibility": True,\n', "")
text = text.replace('            "legacy_compatibility": bool(base.get("legacy_compatibility", False)),\n', "")
text = text.replace('        if row.module_code == "supply_chain_finance_suite":\n            result.update({"finance", "inventory", "procurement"})\n', "")
if '"document_control": {' not in text:
    insert = '''    "document_control": {
        "name": "Document Control & Publications",
        "description": "Controlled manuals/publications, revisions, LEP, distribution, controlled copies, external sources and governed reader workflows.",
        "kind": "STANDALONE",
        "hard_requires": [],
        "embedded_capabilities": ["controlled_documents", "publications", "revision_control", "temporary_revisions", "lep", "controlled_distribution", "controlled_copies", "external_sources", "document_reviews", "governed_reader"],
        "customer_selectable": True,
        "implemented": True,
    },
    "compliance_suite": {
        "name": "Compliance Governance Suite",
        "description": "Quality & Compliance, Training & Competence and Document Control as one governance package.",
        "kind": "BUNDLE",
        "hard_requires": [],
        "included_modules": ["quality", "training", "document_control"],
        "embedded_capabilities": [],
        "customer_selectable": True,
        "implemented": True,
    },
'''
    text = text.replace('    "rostering": {', insert + '    "rostering": {', 1)
text = text.replace("    # Compatibility bundle for tenants licensed before finance/inventory/procurement\n    # were separated. New buyers may still choose it as a suite.\n", "")
enrich_old = '''        subscription = subscriptions.get(code)
        missing = validate_dependencies(db, tenant_id=tenant_id, module_code=code)
        items.append({
            **definition,
            "prices": module_prices,
            "subscription_status": getattr(subscription.status, "value", None) if subscription else None,
            "is_active_for_tenant": code in active,
            "missing_dependencies": missing,
            "can_subscribe": bool(module_prices and not missing and code not in active),
        })'''
enrich_new = '''        subscription = subscriptions.get(code)
        missing = validate_dependencies(db, tenant_id=tenant_id, module_code=code)
        metadata = _decode_metadata(subscription)
        commercial_terms = metadata.get("commercial_terms") if isinstance(metadata.get("commercial_terms"), dict) else {}
        valid_until = commercial_terms.get("valid_until") if commercial_terms else None
        offer_expired = bool(commercial_terms and not _offer_is_current(commercial_terms, now=now))
        effective_from = subscription.effective_from if subscription else None
        effective_to = subscription.effective_to if subscription else None
        if effective_from and effective_from.tzinfo is None:
            effective_from = effective_from.replace(tzinfo=timezone.utc)
        if effective_to and effective_to.tzinfo is None:
            effective_to = effective_to.replace(tzinfo=timezone.utc)
        items.append({
            **definition,
            "prices": module_prices,
            "subscription_status": getattr(subscription.status, "value", None) if subscription else None,
            "is_active_for_tenant": code in active,
            "missing_dependencies": missing,
            "can_subscribe": bool(module_prices and not missing and code not in active),
            "effective_from": effective_from.isoformat() if effective_from else None,
            "effective_to": effective_to.isoformat() if effective_to else None,
            "plan_code": subscription.plan_code if subscription else None,
            "contract_module_code": metadata.get("contract_module_code"),
            "bundle_parent": metadata.get("bundle_parent"),
            "auto_renew": bool(metadata.get("auto_renew", False)),
            "cancel_at_period_end": bool(metadata.get("cancel_at_period_end", False)),
            "is_root_contract": bool(subscription and not metadata.get("commercial_offer_only") and not metadata.get("bundle_parent") and str(metadata.get("contract_module_code") or subscription.module_code) == str(subscription.module_code)),
            "tenant_offer_valid_until": valid_until,
            "tenant_offer_expired": offer_expired,
        })'''
if enrich_old in text:
    text = text.replace(enrich_old, enrich_new, 1)
mc.write_text(text, encoding="utf-8")
remove_py_function(str(mc), "resolve_access_aliases")

# Catalog monkeypatch installers are obsolete after folding their behavior above.
init = Path("backend/amodb/apps/platform/__init__.py")
source = init.read_text(encoding="utf-8")
for line in [
    "from .module_product_boundary_policy import install_module_product_boundary_policy\n",
    "from .module_catalog_runtime_policy import install_module_catalog_runtime_policy\n",
    "install_module_product_boundary_policy()\n",
    "install_module_catalog_runtime_policy()\n",
]:
    source = source.replace(line, "")
init.write_text(source, encoding="utf-8")
for stale in ["module_product_boundary_policy.py", "module_catalog_runtime_policy.py"]:
    p = Path("backend/amodb/apps/platform") / stale
    if p.exists():
        p.unlink()

# Presence semantics belong directly to router_admin.
ra = Path("backend/amodb/apps/accounts/router_admin.py")
text = ra.read_text(encoding="utf-8")
text = re.sub(r"PRESENCE_HEARTBEAT_GRACE_SECONDS\s*=\s*20", 'PRESENCE_HEARTBEAT_GRACE_SECONDS = max(45, int(os.getenv("PRESENCE_HEARTBEAT_GRACE_SECONDS", "90")))', text)
ra.write_text(text, encoding="utf-8")
replace_py_function(
    str(ra),
    "_resolve_presence_state",
    '''def _resolve_presence_state(*, raw_state: str, last_seen_at: Optional[datetime], now: datetime) -> tuple[str, bool]:
    normalized_state = str(raw_state or "offline").lower()
    current_time = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    last_seen = last_seen_at
    if last_seen is not None and last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    fresh = bool(last_seen and last_seen >= current_time - timedelta(seconds=PRESENCE_HEARTBEAT_GRACE_SECONDS))
    if not fresh:
        return "offline", False
    return ("away", True) if normalized_state == "away" else ("online", True)''',
)
replace_py_function(
    str(ra),
    "_presence_display_for_user",
    '''def _presence_display_for_user(*, user: models.User, presence: schemas.UserPresenceRead, availability_status: Optional[str] = None) -> schemas.UserPresenceDisplayRead:
    last_seen = presence.last_seen_at or user.last_login_at
    if not user.is_active:
        return schemas.UserPresenceDisplayRead(status_label="Inactive", last_seen_label="Never seen" if not last_seen else "Inactive", last_seen_at=last_seen, last_seen_at_display=last_seen.isoformat() if last_seen else None)
    if availability_status == "ON_LEAVE":
        return schemas.UserPresenceDisplayRead(status_label="On leave", last_seen_label="Leave scheduled", last_seen_at=last_seen, last_seen_at_display=last_seen.isoformat() if last_seen else None)
    if presence.is_online and presence.state == "away":
        return schemas.UserPresenceDisplayRead(status_label="Away", last_seen_label="Connected, idle", last_seen_at=last_seen, last_seen_at_display=last_seen.isoformat() if last_seen else None)
    if presence.is_online:
        return schemas.UserPresenceDisplayRead(status_label="Online", last_seen_label="Active now", last_seen_at=last_seen, last_seen_at_display=last_seen.isoformat() if last_seen else None)
    return schemas.UserPresenceDisplayRead(status_label="Offline", last_seen_label="Never seen" if not last_seen else "Last seen", last_seen_at=last_seen, last_seen_at_display=last_seen.isoformat() if last_seen else None)''',
)
remove_py_function(str(ra), "get_user_directory_admin")
text = ra.read_text(encoding="utf-8")
text = re.sub(r'PLATFORM_MODULE_CATALOG = \[.*?\]\nPLATFORM_MODULE_CODES = \{item\["code"\] for item in PLATFORM_MODULE_CATALOG\}\n', "", text, flags=re.S)
ra.write_text(text, encoding="utf-8")

rud = Path("backend/amodb/apps/accounts/router_user_directory.py")
remove_py_function(str(rud), "_remove_legacy_route")
rud.write_text(rud.read_text(encoding="utf-8").replace("_remove_legacy_route()\n\n", ""), encoding="utf-8")

accinit = Path("backend/amodb/apps/accounts/__init__.py")
text = accinit.read_text(encoding="utf-8")
if "router_user_directory as _router_user_directory" not in text:
    text = text.replace("from . import router_admin as _router_admin\n", "from . import router_admin as _router_admin\nfrom . import router_user_directory as _router_user_directory\n")
accinit.write_text(text, encoding="utf-8")
p = Path("backend/amodb/apps/accounts/presence_policy.py")
if p.exists():
    p.unlink()

# Parallel direct module administration bypasses commercial invoice/payment controls.
for app in ["backend/amodb/main.py", "backend/amodb/quality_main.py"]:
    p = Path(app)
    t = p.read_text(encoding="utf-8")
    t = "".join(line for line in t.splitlines(True) if "accounts_modules_router" not in line and "router_modules_admin" not in line)
    p.write_text(t, encoding="utf-8")
p = Path("backend/amodb/apps/accounts/router_modules_admin.py")
if p.exists():
    p.unlink()

# Delete executable frontend route aliases and redirect shells.
pr = Path("frontend/src/portalRoutes.tsx")
text = pr.read_text(encoding="utf-8")
old_components = [
    "LegacyTrainingCompetenceRedirect",
    "QualityTrainingCompetenceRedirect",
    "LegacyQmsRedirect",
    "QmsInboxRedirect",
    "QmsProgrammeRedirect",
    "LegacyEngineeringRedirect",
    "LegacyTechnicalRecordsRedirect",
    "LegacyDocControlRedirectPage",
]
for name in old_components:
    text = remove_route_using(text, name)
    text = remove_ts_function(text, name)
    text = "".join(line for line in text.splitlines(True) if name not in line)
pr.write_text(text, encoding="utf-8")

dcp = Path("frontend/src/pages/DocControlPages.tsx")
text = dcp.read_text(encoding="utf-8")
text = remove_ts_function(text, "LegacyDocControlRedirectPage")
dcp.write_text(text, encoding="utf-8")

for p in [mc, init, ra, rud, accinit, pr, dcp]:
    clean_eof(p)
