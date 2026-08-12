from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {rel}, found {count}: {old[:160]!r}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


replace_once(
    "frontend/tests/e2e/qms-car-control-loop.spec.ts",
    '  await expect(page.getByText("At Risk · 55/100")).toBeVisible();\n',
    '  await expect(page.locator(".page-header").getByText("At Risk · 55/100")).toBeVisible();\n',
)

replace_once(
    "frontend/src/pages/PublicCarInvitePage.tsx",
    '''  useEffect(() => stopCamera, []);\n''',
    '''  useEffect(() => {\n    const stream = camera?.stream;\n    return () => stream?.getTracks().forEach((track) => track.stop());\n  }, [camera?.stream]);\n''',
)

replace_once(
    "frontend/src/pages/PublicCarInvitePage.tsx",
    '''  const isStepComplete = (entry: InviteEntry, stepId: InviteStepId): boolean => {\n''',
    '''  const isStepComplete = React.useCallback((entry: InviteEntry, stepId: InviteStepId): boolean => {\n''',
)
replace_once(
    "frontend/src/pages/PublicCarInvitePage.tsx",
    '''      default:\n        return false;\n    }\n  };\n\n  const firstIncompleteStep = (entry: InviteEntry): InviteStepId => {\n    return INVITE_STEPS.find((step) => !isStepComplete(entry, step.id))?.id ?? "review";\n  };\n''',
    '''      default:\n        return false;\n    }\n  }, []);\n\n  const firstIncompleteStep = React.useCallback((entry: InviteEntry): InviteStepId => {\n    return INVITE_STEPS.find((step) => !isStepComplete(entry, step.id))?.id ?? "review";\n  }, [isStepComplete]);\n''',
)
replace_once(
    "frontend/src/pages/PublicCarInvitePage.tsx",
    '''  }, []);\n\n  useEffect(() => {\n    if (initialized.current) return;\n''',
    '''  }, [firstIncompleteStep]);\n\n  useEffect(() => {\n    if (initialized.current) return;\n''',
)

print("QMS CAR frontend browser/hook follow-up applied")
