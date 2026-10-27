"""Vector diagnostic charts in the official CAR RCA PDF.

Diagrams reflect submitted structured nodes and recorded source frequencies.
No category, evidence or Quality verification is inferred by this renderer.
"""
from __future__ import annotations

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit


def _text(pdf, text, x, y, *, size=8, max_width=175, max_lines=2):
    pdf.setFont("Helvetica", size)
    lines = simpleSplit(str(text or ""), "Helvetica", size, max_width)
    for idx, line in enumerate(lines[:max_lines]):
        pdf.drawString(x, y - idx * (size + 2), line)
    return len(lines) > max_lines


def render_fishbone(pdf, method: dict):
    """Produce an editable-source vector PDF page from submitted Ishikawa nodes."""
    nodes = [n for n in method.get("nodes", []) if isinstance(n, dict)]
    if not nodes:
        return False
    width, height = A4
    pdf.showPage()
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(46, height - 50, "Ishikawa / Fishbone - submitted cause map")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(46, height - 67, "Hypotheses are not verified facts; full nested graph and evidence follow in the report.")
    top = height - 100
    groups = {}
    for node in nodes:
        groups.setdefault(str(node.get("category") or "Other"), []).append(node)
    categories = list(groups)
    spine_y = height / 2
    left, right = 70, width - 82
    pdf.setStrokeColorRGB(0.25, 0.33, 0.42)
    pdf.setLineWidth(2)
    pdf.line(left, spine_y, right, spine_y)
    pdf.line(right, spine_y, right-14, spine_y+9)
    pdf.line(right, spine_y, right-14, spine_y-9)
    slot_count = min(len(categories), 8)
    for index, category in enumerate(categories[:slot_count]):
        upper = index % 2 == 0
        pos = index // 2
        end_x = left + 90 + pos * 101
        base_y = spine_y + (145 if upper else -145)
        pdf.setStrokeColorRGB(0.33, 0.43, 0.54)
        pdf.setLineWidth(1.1)
        pdf.line(end_x-40, base_y, end_x, spine_y)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(end_x-67, base_y + (11 if upper else -13), category[:22])
        rows = groups[category]
        for j, node in enumerate(rows[:2]):
            label = str(node.get("statement") or "Undocumented")
            kind = str(node.get("entry_type") or "HYPOTHESIS")
            prefix = "FACT: " if kind == "FACT" else ("CAUSE: " if kind == "CAUSAL_CONCLUSION" else "HYP: ")
            yy = base_y - (12 + j * 28) if upper else base_y + (10 + j * 28)
            pdf.setFillColorRGB(0.18, 0.25, 0.34)
            _text(pdf, prefix + label, end_x-76, yy, size=7, max_width=94, max_lines=2)
        pdf.setFillColorRGB(0, 0, 0)
        if len(rows) > 2:
            pdf.setFont("Helvetica-Oblique", 7)
            pdf.drawString(end_x-67, base_y - 66 if upper else base_y + 66, f"+{len(rows)-2} more causes")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(46, 88, f"{len(nodes)} recorded cause nodes across {len(categories)} categories.")
    if len(categories) > slot_count:
        pdf.drawString(46, 75, "Additional categories are preserved in the complete textual/JSON investigation record.")
    pdf.drawString(46, 58, "Vector overview; not a Quality approval or a substitute for the source graph.")
    return True


def render_pareto(pdf, categories: list[dict], *, source_label: str):
    """Draw descending counts and exact cumulative percentages, without causation claims."""
    valid = []
    for row in categories:
        if not isinstance(row, dict):
            continue
        try:
            n = int(row.get("count", 0))
        except (ValueError, TypeError):
            continue
        if n > 0:
            valid.append((str(row.get("category") or row.get("name") or "Unspecified"), n))
    if not valid:
        return False
    valid.sort(key=lambda row: (-row[1], row[0]))
    total = sum(n for _, n in valid)
    if len(valid) > 8:
        groups = valid[:7] + [("Other recorded categories", sum(n for _, n in valid[7:]))]
    else:
        groups = valid
    width, height = A4
    pdf.showPage()
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(45, height-50, "Pareto - recorded category frequencies")
    pdf.setFont("Helvetica", 9)
    _text(pdf, source_label, 45, height-70, max_width=width-90, max_lines=2)
    pdf.drawString(45, height-100, "Frequency identifies concentration, not proof of a root cause.")
    left, bottom, chart_w, chart_h = 65, 225, width-125, 320
    pdf.setStrokeColorRGB(0.35, 0.42, 0.49)
    pdf.line(left, bottom, left, bottom+chart_h)
    pdf.line(left, bottom, left+chart_w, bottom)
    slot = chart_w / len(groups)
    max_count = max(count for _, count in groups)
    cumulative = 0
    prev = None
    for i, (name, n) in enumerate(groups):
        cumulative += n
        x = left + slot * i + slot * 0.18
        w = slot * 0.64
        bar_h = chart_h * n / max_count
        pdf.setFillColorRGB(0.35, 0.56, 0.70)
        pdf.rect(x, bottom, w, bar_h, stroke=0, fill=1)
        pdf.setFillColorRGB(0.14, 0.21, 0.3)
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawCentredString(x+w/2, bottom+bar_h+7, str(n))
        label_y = bottom-20
        truncated = name[:14] + ("..." if len(name)>14 else "")
        pdf.setFont("Helvetica", 7)
        pdf.drawCentredString(x+w/2, label_y, truncated)
        px = x+w/2
        py = bottom+chart_h*cumulative/total
        pdf.setStrokeColorRGB(0.78, 0.27, 0.25)
        pdf.setLineWidth(2)
        if prev:
            pdf.line(prev[0], prev[1], px, py)
        pdf.setFillColorRGB(0.78, 0.27, 0.25)
        pdf.circle(px, py, 3, fill=1, stroke=0)
        prev = (px, py)
        pdf.setFillColorRGB(0,0,0)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(45, 135, f"Recorded observations: {total}. Total categories: {len(valid)}.")
    pdf.drawString(45, 120, "Bars = frequency; line = cumulative percent (right end = 100%).")
    pdf.drawString(45, 100, "Underlying source references, filters and full frequency table are in the evidence ZIP.")
    return True
