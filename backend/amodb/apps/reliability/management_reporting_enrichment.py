from __future__ import annotations

import html
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

NUMERIC_TYPES = {"decimal", "integer"}
CATEGORY_TYPES = {"select", "boolean"}
MAX_SUMMARY_FIELDS = 18
MAX_KEY_FIELDS = 5


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _display_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return f"{normalized:,.0f}"
    return f"{normalized:,.3f}".rstrip("0").rstrip(".")


def _choose_key_fields(definition) -> list[Any]:
    ordered = sorted(
        definition.fields,
        key=lambda field: (
            0 if field.required else 1,
            0 if field.data_type in NUMERIC_TYPES | CATEGORY_TYPES else 1,
            1 if field.data_type == "textarea" else 0,
        ),
    )
    return [field for field in ordered if field.data_type != "textarea"][:MAX_KEY_FIELDS]


def _field_summaries(definition, records) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for field in definition.fields:
        values = [(record.payload or {}).get(field.key) for record in records]
        nonempty = [value for value in values if value not in (None, "")]
        if not nonempty:
            continue
        if field.data_type in NUMERIC_TYPES:
            numbers = [number for number in (_decimal(value) for value in nonempty) if number is not None]
            if not numbers:
                continue
            total = sum(numbers, Decimal("0"))
            summaries.append({
                "key": field.key,
                "label": field.label,
                "kind": "numeric",
                "unit": field.unit,
                "count": len(numbers),
                "sum": format(total, "f"),
                "average": format(total / Decimal(len(numbers)), "f"),
                "min": format(min(numbers), "f"),
                "max": format(max(numbers), "f"),
            })
            continue
        distinct = Counter(str(value) for value in nonempty)
        if field.data_type in CATEGORY_TYPES or (len(distinct) <= 10 and max(len(value) for value in distinct) <= 64):
            summaries.append({
                "key": field.key,
                "label": field.label,
                "kind": "categorical",
                "count": len(nonempty),
                "top_values": [{"label": label, "count": count} for label, count in distinct.most_common(8)],
            })
        if len(summaries) >= MAX_SUMMARY_FIELDS:
            break
    return summaries


def _derived_summaries(records) -> list[dict[str, Any]]:
    keys = sorted({key for record in records for key in (record.derived_values or {}) if not key.endswith("_note") and "withheld_reason" not in key})
    output: list[dict[str, Any]] = []
    for key in keys:
        numbers = [number for record in records if (number := _decimal((record.derived_values or {}).get(key))) is not None]
        if not numbers:
            continue
        total = sum(numbers, Decimal("0"))
        output.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "kind": "numeric",
            "unit": None,
            "count": len(numbers),
            "sum": format(total, "f"),
            "average": format(total / Decimal(len(numbers)), "f"),
            "min": format(min(numbers), "f"),
            "max": format(max(numbers), "f"),
            "derived": True,
        })
        if len(output) >= 8:
            break
    return output


def _field_summary_html(module, domain: dict[str, Any]) -> str:
    summaries = domain.get("field_summaries") or []
    if not summaries:
        return ""
    numeric_rows: list[list[Any]] = []
    categorical_blocks: list[str] = []
    for item in summaries:
        if item.get("kind") == "numeric":
            numeric_rows.append([
                item.get("label"),
                item.get("count"),
                _display_decimal(_decimal(item.get("sum"))),
                _display_decimal(_decimal(item.get("average"))),
                _display_decimal(_decimal(item.get("min"))),
                _display_decimal(_decimal(item.get("max"))),
                item.get("unit") or "",
            ])
        elif item.get("top_values"):
            categorical_blocks.append(module._svg_bar(
                item["top_values"], "label", "count", f"{domain['code']} — {item['label']}"
            ))
    body = [
        f"<section class='domain field-analysis'><div class='section-heading'><div><p class='eyebrow'>{html.escape(domain['code'])} field analysis</p><h2>{html.escape(domain['name'])} — key values</h2></div></div>"
    ]
    if numeric_rows:
        body.append(module._table(["Field", "N", "Sum", "Average", "Min", "Max", "Unit"], numeric_rows))
    if categorical_blocks:
        body.append("<div class='charts'>" + "".join(categorical_blocks[:6]) + "</div>")
    body.append("</section>")
    return "".join(body)


def apply(module) -> None:
    original_domain_summary = module._domain_summary
    original_render_html = module._render_html

    def domain_summary(code, records):
        result = original_domain_summary(code, records)
        definition = module.wp.DATASET_CATALOG[code]
        key_fields = _choose_key_fields(definition)
        result["key_fields"] = [{"key": field.key, "label": field.label, "unit": field.unit} for field in key_fields]
        for record in result["records"]:
            payload = record.get("payload") or {}
            record["key_values"] = {field.key: payload.get(field.key) for field in key_fields}
        result["field_summaries"] = [*_field_summaries(definition, records), *_derived_summaries(records)]
        return result

    def render_html(data, snapshot_id=None, sha=None):
        rendered = original_render_html(data, snapshot_id, sha)
        enrichment = "".join(_field_summary_html(module, domain) for domain in data.get("domains", []) if domain.get("count"))
        if not enrichment:
            return rendered
        marker = "<div class='control'>"
        if marker not in rendered:
            return rendered.replace("</body>", enrichment + "</body>")
        return rendered.replace(marker, enrichment + marker, 1)

    module._domain_summary = domain_summary
    module._render_html = render_html
