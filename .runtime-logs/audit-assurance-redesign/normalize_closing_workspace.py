"""Collapse blank-line inflation in AuditClosingWorkspace.tsx; keep logic intact."""
from pathlib import Path

SRC = Path(r"D:\XLK-Assets-AMO-Portal-and-DB\amo-portal\frontend\src\features\qms\auditSession\AuditClosingWorkspace.tsx")


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    # File is fully double-spaced (code, blank, code, blank...). Collapse runs of blanks to none between code lines.
    out: list[str] = []
    for ln in lines:
        if ln.strip() == "":
            # skip inflated blanks; we'll add intentional blanks sparingly later
            continue
        out.append(ln.rstrip())

    # Re-insert a blank line before major declarations for readability
    spaced: list[str] = []
    for ln in out:
        if spaced and ln.startswith(("const ", "function ", "export ", "return (")):
            prev = spaced[-1]
            if prev.endswith((";", "}", ")")) or prev.startswith(("import ", "//", "type ")):
                spaced.append("")
        spaced.append(ln)

    text = "\n".join(spaced) + "\n"

    # Wire helpers if missing
    if 'from "./closingProgress"' not in text:
        needle = 'import { auditSessionPath } from "./auditSessionRoutes";'
        alt = 'import { auditSessionPath } from "./auditSessionRoutes";'
        # try both route import styles present in tree
        for cand in (
            'import { auditSessionPath } from "./auditSessionRoutes";',
            'import { auditSessionPath } from "./auditSessionRoutes";',
            'import { auditSessionPath } from "./auditSessionRoutes";',
        ):
            if cand in text:
                text = text.replace(
                    cand,
                    cand
                    + "\n"
                    + "import {\n"
                    + "  closingCardTone,\n"
                    + "  closingLockedReason,\n"
                    + "  closingStepAllowsActions,\n"
                    + "  resolveActiveClosingStep,\n"
                    + '} from "./closingProgress";',
                    1,
                )
                break
        else:
            # fallback: after css import
            css = 'import "../../../styles/qms-audit-closing-workspace.css";'
            if css in text:
                text = text.replace(
                    css,
                    css
                    + "\n"
                    + "import {\n"
                    + "  closingCardTone,\n"
                    + "  closingLockedReason,\n"
                    + "  closingStepAllowsActions,\n"
                    + "  resolveActiveClosingStep,\n"
                    + '} from "./closingProgress";',
                    1,
                )

    # Replace inline progressive IIFE with helper call when present
    marker = "const activeClosingStep = (() => {"
    if marker in text and "resolveActiveClosingStep(" not in text:
        start = text.find(marker)
        # end at closingCardClass definition
        end = text.find("const closingCardClass = (step: number) => {", start)
        if start >= 0 and end > start:
            # Detect field names from surrounding text
            has_latest = "latestGenerated" in text
            latest = "latestGenerated" if has_latest else "latestGenerated"
            ack = "currentAcknowledgement" if "currentAcknowledgement" in text else "currentAcknowledgement"
            sig = "currentSignature" if "currentSignature" in text else "currentSignature"
            issued = "issuedRevision" if "issuedRevision" in text else "issuedRevision"
            # From collapsed file analysis
            if "const latestGenerated" in text or "latestGenerated =" in text:
                latest = "latestGenerated"
            if "currentAcknowledgement" in text:
                ack = "currentAcknowledgement"
            replacement = f"""const activeClosingStep = resolveActiveClosingStep({{
    hasGeneratedDraft: Boolean({latest}),
    activeRevisionStatus: activeRevision?.status ?? null,
    hasAcknowledgement: Boolean({ack}),
    hasSignature: Boolean({sig}),
    hasIssuedRevision: Boolean({issued}),
    executionClosed: closure?.execution_status === "CLOSED",
  }});

  """
            text = text[:start] + replacement + text[end:]

    # Replace closingCardClass / lockedReason bodies to use helpers when still inline
    if "closingCardTone(" not in text and "const closingCardClass = (step: number) => {" in text:
        import re

        text = re.sub(
            r"const closingCardClass = \(step: number\) => \{.*?\n  \};",
            """const closingCardClass = (step: number) => {
    const tone = closingCardTone(step, activeClosingStep);
    if (tone === "current") return "qms-audit-closing__card is-current";
    if (tone === "complete") return "qms-audit-closing__card is-complete";
    return "qms-audit-closing__card is-locked";
  };""",
            text,
            count=1,
            flags=re.S,
        )
        text = re.sub(
            r"const lockedReason = \(step: number\) => \{.*?\n  \};",
            """const lockedReason = (step: number) => closingLockedReason(step, activeClosingStep);
  const stepAllowsActions = (step: number) => closingStepAllowsActions(step, activeClosingStep);""",
            text,
            count=1,
            flags=re.S,
        )

    if "stepAllowsActions" in text:
        # Gate primary mutations without weakening permission predicates
        replacements = [
            (
                "disabled={!canGenerate || generateMutation.isPending}",
                "disabled={!canGenerate || !stepAllowsActions(1) || generateMutation.isPending}",
            ),
            (
                "disabled={!canManage || adoptMutation.isPending}",
                "disabled={!canManage || !stepAllowsActions(1) || adoptMutation.isPending}",
            ),
            (
                "disabled={!canSubmit || transitionMutation.isPending}",
                "disabled={!canSubmit || !stepAllowsActions(3) || transitionMutation.isPending}",
            ),
            (
                "disabled={!canApprove || transitionMutation.isPending}",
                "disabled={!canApprove || !stepAllowsActions(3) || transitionMutation.isPending}",
            ),
            (
                "disabled={!canSign || !passkeys.length || ceremonyBusy !== null || signReason.trim().length < 8}",
                "disabled={!canSign || !stepAllowsActions(4) || !passkeys.length || ceremonyBusy !== null || signReason.trim().length < 8}",
            ),
            (
                'disabled={!canIssue || transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: "ISSUE" })}',
                'disabled={!canIssue || !stepAllowsActions(5) || transitionMutation.isPending} onClick={() => transitionMutation.mutate({ revision: activeRevision, action: "ISSUE" })}',
            ),
            (
                "disabled={!canExecutionClose || executionCloseMutation.isPending}",
                "disabled={!canExecutionClose || !stepAllowsActions(6) || executionCloseMutation.isPending}",
            ),
        ]
        for old, new in replacements:
            if old in text and new not in text:
                text = text.replace(old, new)

    SRC.write_text(text, encoding="utf-8")
    print("lines", len(text.splitlines()))
    print("has resolveActiveClosingStep", "resolveActiveClosingStep(" in text)
    print("has stepAllowsActions", "stepAllowsActions" in text)
    print("closingCardClass count", text.count("closingCardClass("))
    print("lockedReason count", text.count("lockedReason("))


if __name__ == "__main__":
    main()
