from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any, Iterable

MARC_NS = "http://www.loc.gov/MARC21/slim"
NS = {"marc": MARC_NS}
ET.register_namespace("", MARC_NS)

_MAX_XML_CHARS = 5_000_000
_MAX_RECORDS = 500


def _clean(value: str | None) -> str | None:
    text = " ".join(str(value or "").split()).strip(" /:;,")
    return text or None


def _subfields(record: ET.Element, tag: str, codes: set[str] | None = None) -> list[str]:
    values: list[str] = []
    for field in record.findall(f"marc:datafield[@tag='{tag}']", NS):
        for subfield in field.findall("marc:subfield", NS):
            code = str(subfield.attrib.get("code") or "")
            if codes is None or code in codes:
                value = _clean(subfield.text)
                if value:
                    values.append(value)
    return values


def _first(record: ET.Element, tag: str, codes: set[str] | None = None) -> str | None:
    values = _subfields(record, tag, codes)
    return values[0] if values else None


def _control(record: ET.Element, tag: str) -> str | None:
    node = record.find(f"marc:controlfield[@tag='{tag}']", NS)
    return _clean(node.text) if node is not None else None


def _year(*values: str | None) -> int | None:
    for value in values:
        match = re.search(r"(?<!\d)(1\d{3}|2\d{3})(?!\d)", str(value or ""))
        if match:
            parsed = int(match.group(1))
            if 1000 <= parsed <= 3000:
                return parsed
    return None


def _identifier_value(value: str | None) -> str | None:
    if not value:
        return None
    # MARC identifiers commonly append qualifiers such as "(pbk.)".
    text = re.sub(r"\s+\([^)]*\)\s*$", "", value).strip()
    return text or None


def _fallback_code(record_id: str | None, title: str, index: int) -> str:
    if record_id:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "-", record_id).strip("-")
        if safe:
            return f"MARC-{safe}"[:128]
    digest = hashlib.sha256(f"{title}:{index}".encode("utf-8")).hexdigest()[:12].upper()
    return f"MARC-{digest}"


def parse_marcxml(xml_text: str, *, max_records: int = _MAX_RECORDS) -> list[dict[str, Any]]:
    if len(xml_text) > _MAX_XML_CHARS:
        raise ValueError("MARCXML payload exceeds the 5 MB import limit")
    upper_head = xml_text[:4096].upper()
    if "<!DOCTYPE" in upper_head or "<!ENTITY" in upper_head:
        raise ValueError("MARCXML imports may not contain DTD or entity declarations")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid MARCXML: {exc}") from exc

    if root.tag == f"{{{MARC_NS}}}record":
        records = [root]
    else:
        records = list(root.findall(".//marc:record", NS))
    if not records:
        raise ValueError("No MARC 21 bibliographic records were found")
    if len(records) > max_records:
        raise ValueError(f"MARCXML import contains {len(records)} records; maximum is {max_records}")

    parsed: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        title = _first(record, "245", {"a"}) or _first(record, "246", {"a"})
        if not title:
            raise ValueError(f"MARC record {index} has no usable title in field 245$a or 246$a")
        subtitle = _first(record, "245", {"b"})
        authors = []
        for candidate in (
            *_subfields(record, "100", {"a"}),
            *_subfields(record, "110", {"a"}),
            *_subfields(record, "111", {"a"}),
            *_subfields(record, "700", {"a"}),
            *_subfields(record, "710", {"a"}),
        ):
            if candidate not in authors:
                authors.append(candidate)

        identifiers: dict[str, str] = {}
        isbn = _identifier_value(_first(record, "020", {"a"}))
        issn = _identifier_value(_first(record, "022", {"a"}))
        doi = None
        for field in record.findall("marc:datafield[@tag='024']", NS):
            ind1 = str(field.attrib.get("ind1") or "")
            value = None
            for subfield in field.findall("marc:subfield", NS):
                if subfield.attrib.get("code") == "a":
                    value = _clean(subfield.text)
                    break
            if value and ind1 == "7":
                scheme = None
                for subfield in field.findall("marc:subfield", NS):
                    if subfield.attrib.get("code") == "2":
                        scheme = _clean(subfield.text)
                        break
                if str(scheme or "").lower() == "doi":
                    doi = value
                    break
        control_001 = _control(record, "001")
        oclc = _first(record, "035", {"a"})
        if isbn:
            identifiers["isbn"] = isbn
        if issn:
            identifiers["issn"] = issn
        if doi:
            identifiers["doi"] = doi
        if oclc:
            identifiers["oclc"] = oclc
        if control_001:
            identifiers["marc_001"] = control_001

        publisher = _first(record, "264", {"b"}) or _first(record, "260", {"b"})
        publication_text = _first(record, "264", {"c"}) or _first(record, "260", {"c"})
        edition = _first(record, "250", {"a"})
        language = _first(record, "041", {"a"}) or (_control(record, "008")[35:38].strip() if _control(record, "008") and len(_control(record, "008") or "") >= 38 else None)
        subjects = []
        for tag in ("600", "610", "611", "630", "648", "650", "651", "653"):
            for subject in _subfields(record, tag, {"a", "x", "y", "z"}):
                if subject not in subjects:
                    subjects.append(subject)
        description = _first(record, "520", {"a"})
        source_url = _first(record, "856", {"u"})
        call_number = _first(record, "050", {"a"}) or _first(record, "082", {"a"}) or _first(record, "090", {"a"})

        parsed.append({
            "catalogue_code": _fallback_code(control_001, title, index),
            "material_type": "BOOK",
            "title": title,
            "subtitle": subtitle,
            "authors": authors[:50],
            "publisher": publisher,
            "publication_year": _year(publication_text, _control(record, "008")),
            "edition": edition,
            "language": language,
            "identifiers": identifiers,
            "subjects": subjects[:100],
            "description": description,
            "source_provider": "MARC21",
            "source_record_id": control_001,
            "source_url": source_url,
            "metadata": {
                "marc_format": "MARCXML",
                "call_number": call_number,
                "leader": _clean(record.findtext("marc:leader", default="", namespaces=NS)),
            },
        })
    return parsed


def _datafield(parent: ET.Element, tag: str, values: Iterable[tuple[str, str]], *, ind1: str = " ", ind2: str = " ") -> None:
    values = [(code, value) for code, value in values if value]
    if not values:
        return
    field = ET.SubElement(parent, f"{{{MARC_NS}}}datafield", {"tag": tag, "ind1": ind1[:1] or " ", "ind2": ind2[:1] or " "})
    for code, value in values:
        node = ET.SubElement(field, f"{{{MARC_NS}}}subfield", {"code": code[:1]})
        node.text = str(value)


def build_marcxml(items: Iterable[Any], identifiers_by_item: dict[str, list[Any]]) -> str:
    collection = ET.Element(f"{{{MARC_NS}}}collection")
    for item in items:
        record = ET.SubElement(collection, f"{{{MARC_NS}}}record")
        leader = ET.SubElement(record, f"{{{MARC_NS}}}leader")
        leader.text = "00000nam a2200000 i 4500"
        control = ET.SubElement(record, f"{{{MARC_NS}}}controlfield", {"tag": "001"})
        control.text = str(item.source_record_id or item.catalogue_code)

        _datafield(record, "245", [
            ("a", str(item.title)),
            ("b", str(item.subtitle or "")),
        ], ind1="0", ind2="0")
        authors = list(item.authors_json or [])
        if authors:
            _datafield(record, "100", [("a", str(authors[0]))], ind1="1", ind2=" ")
            for author in authors[1:]:
                _datafield(record, "700", [("a", str(author))], ind1="1", ind2=" ")
        if item.edition:
            _datafield(record, "250", [("a", str(item.edition))])
        if item.publisher or item.publication_year:
            _datafield(record, "264", [
                ("b", str(item.publisher or "")),
                ("c", str(item.publication_year or "")),
            ], ind1=" ", ind2="1")
        if item.language:
            _datafield(record, "041", [("a", str(item.language))])

        identifiers = identifiers_by_item.get(str(item.id), [])
        for identifier in identifiers:
            scheme = str(identifier.scheme or "").lower()
            value = str(identifier.display_value or "")
            if scheme.startswith("isbn"):
                _datafield(record, "020", [("a", value)])
            elif scheme == "issn":
                _datafield(record, "022", [("a", value)])
            elif scheme == "doi":
                _datafield(record, "024", [("a", value), ("2", "doi")], ind1="7", ind2=" ")
            elif scheme == "oclc":
                _datafield(record, "035", [("a", value)])

        for subject in list(item.subjects_json or []):
            _datafield(record, "650", [("a", str(subject))], ind1=" ", ind2="0")
        if item.description:
            _datafield(record, "520", [("a", str(item.description))])
        if item.source_url:
            _datafield(record, "856", [("u", str(item.source_url))], ind1="4", ind2="0")
        call_number = str((item.metadata_json or {}).get("call_number") or "")
        if call_number:
            _datafield(record, "090", [("a", call_number)])

    return ET.tostring(collection, encoding="unicode", xml_declaration=True)
