from pathlib import Path


workflow = Path(".github/workflows/release-candidate-recheck.yml")
text = workflow.read_text(encoding="utf-8")

compile_marker = "          amodb/apps/platform\n          amodb/apps/quality\n"
compile_replacement = "          amodb/apps/platform\n          amodb/apps/procurement\n          amodb/apps/quality\n"
if "          amodb/apps/procurement\n" not in text:
    if text.count(compile_marker) != 1:
        raise SystemExit("Could not locate backend compile module list")
    text = text.replace(compile_marker, compile_replacement, 1)

route_marker = '              "/api/notifications/tenant-preferences",\n'
route_replacement = (
    '              "/api/notifications/tenant-preferences",\n'
    '              "/api/maintenance/{amo_code}/procurement/documents",\n'
    '              "/api/maintenance/{amo_code}/procurement/requisitions",\n'
)
if '"/api/maintenance/{amo_code}/procurement/documents"' not in text:
    if text.count(route_marker) != 1:
        raise SystemExit("Could not locate critical route set")
    text = text.replace(route_marker, route_replacement, 1)

quality_marker = "      - name: Run Quality regressions\n"
procurement_step = '''      - name: Run Procurement regressions
        working-directory: backend
        run: >-
          pytest -q
          tests/test_procurement_module_contract.py
          tests/test_procurement_document_contract.py
          tests/test_procurement_frontend_contract.py
      - name: Run Quality regressions
'''
if "      - name: Run Procurement regressions\n" not in text:
    if text.count(quality_marker) != 1:
        raise SystemExit("Could not locate Quality regression step")
    text = text.replace(quality_marker, procurement_step, 1)

workflow.write_text(text, encoding="utf-8")

updated = workflow.read_text(encoding="utf-8")
for token in [
    "amodb/apps/procurement",
    '"/api/maintenance/{amo_code}/procurement/documents"',
    '"/api/maintenance/{amo_code}/procurement/requisitions"',
    "tests/test_procurement_module_contract.py",
    "tests/test_procurement_document_contract.py",
    "tests/test_procurement_frontend_contract.py",
]:
    if token not in updated:
        raise SystemExit(f"Required Procurement release-gate token missing: {token}")
