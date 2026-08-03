from pathlib import Path

path = Path(__file__).resolve().parents[1] / "amodb/apps/reliability/advanced_services.py"
text = path.read_text(encoding="utf-8")
broken = '''    review.notes = f"{review.notes or ''}
Approval rationale: {rationale}".strip()
'''
fixed = '''    review.notes = f"{review.notes or ''}\\nApproval rationale: {rationale}".strip()
'''
if broken not in text:
    raise SystemExit("Generated effectiveness-approval newline defect was not found")
path.write_text(text.replace(broken, fixed, 1), encoding="utf-8")
print("Generated Reliability approval newline corrected.")
