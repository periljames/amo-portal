from pathlib import Path

root = Path(r"frontend/src/features/qms/auditSession")
closing = (root / "AuditClosingWorkspace.tsx").read_text(encoding="utf-8")
setup = (root / "AuditSetupWorkspace.tsx").read_text(encoding="utf-8")
helpers = (root / "closingProgress.ts").read_text(encoding="utf-8")

print("=== Closing ===")
print("lines", len(closing.splitlines()))
print("blank_pairs", closing.count("\n\n"))
print(
    "balance braces",
    closing.count("{") - closing.count("}"),
    "parens",
    closing.count("(") - closing.count(")"),
)
for name in [
    "resolveActiveClosingStep",
    "closingCardTone",
    "closingLockedReason",
    "closingStepAllowsActions",
    "closingCardClass",
    "lockedReason",
    "stepAllowsActions",
]:
    print(f"  {name}: {closing.count(name)}")
for line in closing.splitlines():
    if any(
        s in line
        for s in (
            "const canApprove",
            "const canSign",
            "const canIssue",
            "const canExecutionClose",
            "const canGenerateAssurance",
            "const canGenerate ",
            "const canSubmit",
        )
    ):
        print(" ", line.strip())
print("sections", closing.count("<section"))
print("imports closingProgress", "from \"./closingProgress\"" in closing)

print("\n=== Helpers exports ===")
for line in helpers.splitlines():
    if line.startswith("export function"):
        print(" ", line)

print("\n=== Setup auditQuery ===")
decl = setup.find("const auditQuery = useQuery")
print("decl index", decl)
print("refs before decl", setup[:decl].count("auditQuery") if decl >= 0 else "N/A")
# find first auditQuery use
idx = 0
uses = []
while True:
    i = setup.find("auditQuery", idx)
    if i < 0:
        break
    uses.append(i)
    idx = i + 1
print("first use index", uses[0] if uses else None)
print("decl before first use", decl < uses[0] if uses and decl >= 0 else None)
