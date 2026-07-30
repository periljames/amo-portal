from pathlib import Path

root = Path(__file__).resolve().parents[2]

component = root / "frontend/src/pages/manuals/DocumentationAssistantPanel.tsx"
text = component.read_text(encoding="utf-8")
text = text.replace("  GripVertical,\n", "", 1)
old_grip = "><GripVertical size={16} /></div> : null}"
new_grip = "><span className=\"documentation-assistant__resize-grip\" aria-hidden=\"true\" /></div> : null}"
if old_grip not in text:
    raise RuntimeError("resize grip JSX anchor missing")
component.write_text(text.replace(old_grip, new_grip, 1), encoding="utf-8")

css_file = root / "frontend/src/pages/manuals/documentationAssistantPanel.css"
css = css_file.read_text(encoding="utf-8")
old_block = '''.documentation-assistant__resize-handle svg {
  position: relative;
  z-index: 1;
  box-sizing: content-box;
  padding: 2px;
  border: 1px solid var(--assistant-border);
  border-radius: 999px;
  background: var(--surface-raised, #fff);
  opacity: 0;
  transition: opacity 140ms ease, transform 140ms ease;
}'''
new_block = '''.documentation-assistant__resize-grip {
  position: relative;
  z-index: 1;
  display: block;
  width: 6px;
  height: 18px;
  border: 1px solid var(--assistant-border);
  border-radius: 999px;
  background:
    radial-gradient(circle, currentColor 1px, transparent 1.4px) center 3px / 4px 6px repeat-y,
    var(--surface-raised, #fff);
  opacity: 0;
  transition: opacity 140ms ease, transform 140ms ease;
}'''
if old_block not in css:
    raise RuntimeError("resize grip CSS block missing")
css = css.replace(old_block, new_block, 1)
css = css.replace(
    '''.documentation-assistant__resize-handle:hover svg,
.documentation-assistant__resize-handle:focus-visible svg,
.documentation-assistant[data-resizing="true"] .documentation-assistant__resize-handle svg {''',
    '''.documentation-assistant__resize-handle:hover .documentation-assistant__resize-grip,
.documentation-assistant__resize-handle:focus-visible .documentation-assistant__resize-grip,
.documentation-assistant[data-resizing="true"] .documentation-assistant__resize-grip {''',
    1,
)
css = css.replace(
    '''  .documentation-assistant__resize-handle::before,
  .documentation-assistant__resize-handle svg {''',
    '''  .documentation-assistant__resize-handle::before,
  .documentation-assistant__resize-grip {''',
    1,
)
css_file.write_text(css, encoding="utf-8")

test_file = root / "frontend/src/pages/rostering/documentationAssistantUx.test.ts"
test = test_file.read_text(encoding="utf-8")
anchor = '    expect(assistant).toContain("role=\\\"separator\\\"");\n'
replacement = anchor + '    expect(assistant).toContain("documentation-assistant__resize-grip");\n    expect(assistant).not.toContain("GripVertical");\n'
if anchor not in test:
    raise RuntimeError("assistant asset test anchor missing")
test_file.write_text(test.replace(anchor, replacement, 1), encoding="utf-8")

print("Removed the standalone grip icon asset from the assistant drawer")
