from pathlib import Path


workflow = Path(".github/workflows/pr364-reachable-controls-fix.yml").read_text(encoding="utf-8")
marker = "          python - <<'PY'\n"
start = workflow.index(marker) + len(marker)
end = workflow.index("\n          PY\n", start)
script = "\n".join(
    line[10:] if line.startswith("          ") else line
    for line in workflow[start:end].splitlines()
)

matcher_start = script.index("approval_marker =")
matcher_end = script.index("\n\n# Re-expose", matcher_start)
structural_matcher = '''approval_heading = '<div><h2>Roster approval</h2></div>'
if approval_heading in governance_text and '{showApprovalWorkflow ? (' not in governance_text:
    heading_position = governance_text.index(approval_heading)
    start = governance_text.rfind('      <section className="wr-panel">', 0, heading_position)
    if start < 0:
        raise RuntimeError('Roster approval section start not found')
    end = governance_text.index('      </section>', heading_position) + len('      </section>')
    block = governance_text[start:end]
    wrapped = '      {showApprovalWorkflow ? (\\n' + indent(block, '  ') + '\\n      ) : null}'
    governance_text = governance_text[:start] + wrapped + governance_text[end:]
    governance_file.write_text(governance_text, encoding='utf-8')
elif '{showApprovalWorkflow ? (' not in governance_text:
    raise RuntimeError('Roster approval section anchor not found')'''
script = script[:matcher_start] + structural_matcher + script[matcher_end:]
exec(compile(script, "/tmp/pr364_reachable_controls.py", "exec"))
