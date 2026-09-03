from pathlib import Path
import re

p = Path(r"D:\XLK-Assets-AMO-Portal-and-DB\amo-portal\frontend\src\features\qms\auditSession\AuditClosingWorkspace.tsx")
text = p.read_text(encoding="utf-8")

anchor = (
    "  const canGenerateAssurance = Boolean(canManage && supplementaryPolicy && "
    "currentSignature && issuedRevision && !currentAssuranceArtifact);\n"
)
insert = '''  const canGenerateAssurance = Boolean(canManage && supplementaryPolicy && currentSignature && issuedRevision && !currentAssuranceArtifact);

  /** Progressive closing: current gate dominates; later gates stay locked. */
  const activeClosingStep = (() => {
    if (!latestGenerated || !activeRevision) return 1;
    if (activeRevision.status === "DRAFT" && !currentAcknowledgement) return 2;
    if (activeRevision.status === "DRAFT" || activeRevision.status === "INTERNAL_REVIEW") return 3;
    if (activeRevision.status === "APPROVED" && !currentSignature) return 4;
    if (activeRevision.status === "APPROVED" && currentSignature) return 5;
    if (issuedRevision && closure?.execution_status !== "CLOSED") return 6;
    return 7;
  })();

  const closingCardClass = (step: number) => {
    if (step === activeClosingStep) return "qms-audit-closing__card is-current";
    if (step < activeClosingStep) return "qms-audit-closing__card is-complete";
    return "qms-audit-closing__card is-locked";
  };

  const lockedReason = (step: number) => {
    if (step <= activeClosingStep) return null;
    if (activeClosingStep === 1) return "Complete freeze and generate/adopt a closing draft first.";
    if (activeClosingStep === 2) return "Awaiting auditee acknowledgement on the governed draft.";
    if (activeClosingStep === 3) return "Complete Quality review/approval before this step unlocks.";
    if (activeClosingStep === 4) return "Passkey approval of the exact approved report is required first.";
    if (activeClosingStep === 5) return "Issue the passkey-approved report before this step unlocks.";
    if (activeClosingStep === 6) return "Close execution before assurance/verification outputs.";
    return "Complete the preceding closing gate first.";
  };

'''

if "activeClosingStep" not in text:
    if anchor not in text:
        raise SystemExit(f"anchor missing. snippet nearby:\n" + "\n".join(
            f"{i}: {line}" for i, line in enumerate(text.splitlines(), 1)
            if "canGenerateAssurance" in line or "canExecutionClose" in line
        ))
    text = text.replace(anchor, insert, 1)
    print("inserted progressive logic")
else:
    print("logic already present")

lines = text.splitlines(True)
out = []
step = 0
for line in lines:
    if '<section className="qms-audit-closing__card">' in line:
        step += 1
        indent = line[: len(line) - len(line.lstrip())]
        out.append(
            f'{indent}<section className={{closingCardClass({step})}} '
            f'aria-current={{activeClosingStep === {step} ? "step" : undefined}}>\n'
        )
        continue
    out.append(line)

text2 = "".join(out)

text3, n = re.subn(
    r'(<section className=\{closingCardClass\((\d+)\)\} aria-current=\{activeClosingStep === \2 \? "step" : undefined\}>\n)'
    r'(\s*<header>[\s\S]*?</header>)',
    lambda m: (
        f"{m.group(1)}{m.group(3)}\n"
        f"          {{lockedReason({m.group(2)}) ? "
        f'<div className="qms-audit-closing__locked" role="status">'
        f"{{lockedReason({m.group(2)})}}</div> : null}}\n"
    ),
    text2,
    count=7,
)
print("lock banners injected", n)
print("closingCardClass usages", text3.count("closingCardClass("))
p.write_text(text3, encoding="utf-8")
print("wrote", p)
