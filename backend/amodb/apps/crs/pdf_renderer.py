from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import re

import importlib.util
from pdfrw import PdfReader, PdfWriter, PdfDict, PdfName
from pdfrw.objects.pdfstring import PdfString
from pdfrw.pagemerge import PageMerge

from ...database import SessionLocal
from . import models as crs_models

if TYPE_CHECKING:
    from reportlab.lib.utils import ImageReader

BASE_DIR = Path(__file__).resolve().parents[2]

# Directories where we look for the current CRS template.
TEMPLATE_SEARCH_DIRS = [
    BASE_DIR / "templates" / "crs",
    BASE_DIR / "templates",
]

# Pattern for your CRS template files, e.g.
# "Form Template CRS Form Rev 6.pdf"
TEMPLATE_GLOB = "Form Template CRS Form Rev *.pdf"

OUTPUT_DIR = BASE_DIR / "generated" / "crs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_OUTPUT_DIR = OUTPUT_DIR / "templates"
TEMPLATE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Keys for checkboxes and radios in the PDF
CHECKBOX_FIELDS = {"AMP", "AMM", "Mtx Data"}
AIRFRAME_UNIT_FIELDS = {"Hours", "Cycles"}  # radio buttons under Airframe unit

RELEASING_AUTH_RADIO = {
    "KCAA": "KCAA",
    "ECAA": "ECAA",
    "GCAA": "GCAA",
}

FIELD_NAME_ALIASES = {
    "7b RH Engine SNo": "RH_Engine_SNo",
}


@dataclass(frozen=True)
class BarcodePlacement:
    page_index: int
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class CopyFooterPlacement:
    x: float
    y: float
    font_size: int


BARCODE_PLACEMENT_BY_REV = {
    6: BarcodePlacement(
        page_index=0,
        x=17.0183,
        y=748.574,
        width=150.6547,
        height=22.0,
    ),
}

COPY_FOOTER_PLACEMENT_BY_REV = {
    6: CopyFooterPlacement(x=36.0, y=18.0, font_size=8),
}


def _parse_revision_number(path: Path) -> int:
    """
    Extracts the numeric revision from filenames like:
        'Form Template CRS Form Rev 6.pdf' -> 6
    Falls back to 0 if no match.
    """
    m = re.search(r"Rev\s*(\d+)", path.stem, re.IGNORECASE)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except ValueError:
        return 0


def get_latest_crs_template() -> Path:
    """
    Locate the latest CRS PDF template file.

    It searches:
      - backend/amodb/templates/crs/Form Template CRS Form Rev X.pdf
      - backend/amodb/templates/Form Template CRS Form Rev X.pdf

    and picks the highest revision number; if no such file exists, it
    falls back to the legacy fixed path 'templates/crs/crs_form_rev6.pdf'.
    """
    candidates: List[Path] = []
    for d in TEMPLATE_SEARCH_DIRS:
        if d.exists():
            candidates.extend(d.glob(TEMPLATE_GLOB))

    if not candidates:
        fallback = BASE_DIR / "templates" / "crs" / "crs_form_rev6.pdf"
        if fallback.exists():
            return fallback
        raise FileNotFoundError(
            "No CRS template PDF found. Expected a file matching "
            f"'{TEMPLATE_GLOB}' in {', '.join(str(d) for d in TEMPLATE_SEARCH_DIRS)} "
            "or 'templates/crs/crs_form_rev6.pdf'."
        )

    # Sort by (revision, mtime) and take the last one
    candidates.sort(
        key=lambda p: (_parse_revision_number(p), p.stat().st_mtime)
    )
    return candidates[-1]


def _decode_pdf_field_name(field_name_obj: Any) -> str:
    if isinstance(field_name_obj, PdfString):
        return field_name_obj.to_unicode()

    field_name = str(field_name_obj)
    if field_name.startswith("(") and field_name.endswith(")"):
        return field_name[1:-1]
    return field_name


def _normalize_field_name(field_name: str) -> str:
    cleaned = (
        field_name.replace("\ufeff", "")
        .replace("\u00ad", "")
        .replace("\x00", "")
        .strip()
    )
    return FIELD_NAME_ALIASES.get(cleaned, cleaned)


def _build_field_values(crs: crs_models.CRS) -> Dict[str, Any]:
    """
    Map CRS ORM model -> PDF field names.

    NOTE:
    - Field names must match the AcroForm field names in the PDF exactly.
    - If any name is off, just adjust here.
    """

    values: Dict[str, Any] = {
        # Identity / barcode
        "CRS Serial Number": crs.crs_serial,
        "Barcode": "",

        # Releasing Authority (radio handled separately)
        "Operator_Contractor": crs.operator_contractor,
        "Job_No": crs.job_no or "",
        "WO#": crs.wo_no or "",
        "Location": crs.location or "",

        # Aircraft / engines
        "Aircraft_Type": crs.aircraft_type,
        "Aircraft_Registration": crs.aircraft_reg,
        "Msn": crs.msn or "",
        "LH_Engine_Type": crs.lh_engine_type or "",
        "RH_Engine_Type": crs.rh_engine_type or "",
        "LH_Engine_SNo": crs.lh_engine_sno or "",
        "RH_Engine_SNo": crs.rh_engine_sno or "",
        "Aircraft_TAT": crs.aircraft_tat or 0,
        "Aircraft_TAC": crs.aircraft_tac or 0,
        "LH_Hrs": crs.lh_hrs or 0,
        "LH_Cyc": crs.lh_cyc or 0,
        "RH_Hrs": crs.rh_hrs or 0,
        "RH_Cyc": crs.rh_cyc or 0,

        # Work / deferred maintenance
        "Maintenance Carried out": crs.maintenance_carried_out or "",
        "Deferred_Maintenance": crs.deferred_maintenance or "",
        "Date_of_Completion": (
            crs.date_of_completion.strftime("%d-%b-%Y")
            if crs.date_of_completion
            else ""
        ),

        # Maintenance data check boxes
        "AMP": crs.amp_used,
        "AMM": crs.amm_used,
        "Mtx Data": crs.mtx_data_used,

        "AMP_Reference": crs.amp_reference or "",
        "AMP_Revision": crs.amp_revision or "",
        "AMP_Issue_Date": (
            crs.amp_issue_date.strftime("%d-%b-%Y")
            if crs.amp_issue_date
            else ""
        ),
        "AMM_Reference": crs.amm_reference or "",
        "AMM_Revision": crs.amm_revision or "",
        "AMM_Issue_Date": (
            crs.amm_issue_date.strftime("%d-%b-%Y")
            if crs.amm_issue_date
            else ""
        ),
        "Add_Mtx_Data": crs.add_mtx_data or "",
        "Work_Order_No": crs.work_order_no or "",

        # Expiry & next maintenance
        "Expiry Date": (
            crs.expiry_date.strftime("%d-%b-%Y")
            if crs.expiry_date
            else ""
        ),
        "Hrs to Expiry": crs.hrs_to_expiry or 0,
        "SUM (Aircraft TAT, Hrs to Expi": crs.sum_airframe_tat_expiry or 0,
        "Next Maintenance Due": crs.next_maintenance_due or "",

        # Certificate issued by
        "Full Name and Signature": crs.issuer_full_name or "",
        "Internal Certification Authorization Ref": crs.issuer_auth_ref or "",
        "CategoryAC License": crs.issuer_license or "",
        "CRS Issue Date": (
            crs.crs_issue_date.strftime("%d-%b-%Y")
            if crs.crs_issue_date
            else ""
        ),
        "CRS Issuing Stamp": crs.crs_issuing_stamp or "",
    }

    # Airframe unit – radio buttons
    values["Hours"] = crs.airframe_limit_unit.upper() == "HOURS"
    values["Cycles"] = crs.airframe_limit_unit.upper() == "CYCLES"

    # Releasing authority – radio group (KCAA/ECAA/GCAA)
    for key in RELEASING_AUTH_RADIO.values():
        values[key] = (crs.releasing_authority.upper() == key)

    # Category signoffs (A – Aeroplanes etc.)
    suffix_map = {
        "AEROPLANES": "A Aeroplanes",
        "ENGINES": "C Engines",
        "RADIO": "R Radio",
        "COMPASS": "X Compass",
        "ELECTRICAL POWER": "X Electrical Power",
        "INSTRUMENTS": "X Instruments",
        "AUTOMATIC AUTOPILOT": "X Automatic Autopilot",
    }

    for s in crs.signoffs:
        key = s.category.upper()
        if key not in suffix_map:
            continue
        suf = suffix_map[key]  # e.g. "A Aeroplanes"
        values[f"Date{suf}"] = (
            s.sign_date.strftime("%d-%b-%Y") if s.sign_date else ""
        )
        values[f"Full Name and Signature{suf}"] = (
            s.full_name_and_signature or ""
        )
        values[f"Internal Certification Authorization Ref{suf}"] = (
            s.internal_auth_ref or ""
        )
        values[f"Stamp{suf}"] = s.stamp or ""

    return values


def _get_page_size(page: PdfDict) -> tuple[float, float]:
    mb = getattr(page, "MediaBox", None)
    if mb and len(mb) == 4:
        x0, y0, x1, y1 = [float(v) for v in mb]
        return x1 - x0, y1 - y0
    return 0.0, 0.0


def _find_field_rect(
    template: Path,
    field_name: str,
) -> Optional[BarcodePlacement]:
    pdf = PdfReader(str(template))
    for page_index, page in enumerate(pdf.pages):
        annots = getattr(page, "Annots", None)
        if not annots:
            continue
        for annot in annots:
            field_name_obj = annot.get("/T")
            if not field_name_obj:
                continue
            raw_name = _decode_pdf_field_name(field_name_obj)
            normalized_name = _normalize_field_name(raw_name)
            if normalized_name != field_name:
                continue
            rect = annot.get("/Rect")
            if not rect or len(rect) != 4:
                continue
            x0, y0, x1, y1 = [float(v) for v in rect]
            return BarcodePlacement(
                page_index=page_index,
                x=x0,
                y=y0,
                width=x1 - x0,
                height=y1 - y0,
            )
    return None


def _get_barcode_placement(template: Path) -> BarcodePlacement:
    placement = _find_field_rect(template, "Barcode")
    if placement:
        return placement

    revision = _parse_revision_number(template)
    if revision in BARCODE_PLACEMENT_BY_REV:
        return BARCODE_PLACEMENT_BY_REV[revision]
    raise ValueError(
        "Barcode placement not configured for CRS template revision "
        f"{revision}. Update BARCODE_PLACEMENT_BY_REV or add a 'Barcode' "
        "field to the template."
    )


def _get_copy_footer_placement(template: Path) -> CopyFooterPlacement:
    revision = _parse_revision_number(template)
    if revision in COPY_FOOTER_PLACEMENT_BY_REV:
        return COPY_FOOTER_PLACEMENT_BY_REV[revision]
    return CopyFooterPlacement(x=36.0, y=18.0, font_size=8)


def _generate_barcode_reader(barcode_value: str) -> ImageReader:
    if importlib.util.find_spec("barcode") is None:
        raise RuntimeError(
            "Missing dependency 'python-barcode'. Install it with "
            "'pip install -r backend/requirements.txt'."
        )
    if importlib.util.find_spec("reportlab") is None:
        raise RuntimeError(
            "Missing dependency 'reportlab'. Install it with "
            "'pip install -r backend/requirements.txt'."
        )
    from barcode import Code128  # type: ignore[import-not-found]
    from barcode.writer import ImageWriter  # type: ignore[import-not-found]
    from reportlab.lib.utils import ImageReader  # type: ignore[import-not-found]

    barcode = Code128(barcode_value, writer=ImageWriter())
    buffer = BytesIO()
    barcode.write(
        buffer,
        options={
            "module_width": 0.2,
            "module_height": 10.0,
            "quiet_zone": 1.0,
            "font_size": 0,
            "text_distance": 1.0,
        },
    )
    buffer.seek(0)
    return ImageReader(buffer)


def _build_overlay_pdf(
    page_size: tuple[float, float],
    footer_text: str,
    footer_placement: CopyFooterPlacement,
    barcode_reader: Optional[ImageReader],
    barcode_placement: Optional[BarcodePlacement],
) -> PdfDict:
    if importlib.util.find_spec("reportlab") is None:
        raise RuntimeError(
            "Missing dependency 'reportlab'. Install it with "
            "'pip install -r backend/requirements.txt'."
        )
    from reportlab.pdfgen import canvas  # type: ignore[import-not-found]
    
    buffer = BytesIO()
    overlay = canvas.Canvas(buffer, pagesize=page_size)
    overlay.setFont("Helvetica", footer_placement.font_size)
    overlay.drawString(footer_placement.x, footer_placement.y, footer_text)

    if barcode_reader and barcode_placement:
        overlay.drawImage(
            barcode_reader,
            barcode_placement.x,
            barcode_placement.y,
            width=barcode_placement.width,
            height=barcode_placement.height,
            preserveAspectRatio=True,
            mask="auto",
        )

    overlay.save()
    buffer.seek(0)
    return PdfReader(fdata=buffer.read()).pages[0]


def _render_multi_copy_pdf(
    filled_template: Path,
    output: Path,
    barcode_value: str,
    template_path: Path,
    copy_labels: List[str],
) -> None:
    pdf = PdfReader(str(filled_template))
    barcode_placement = _get_barcode_placement(template_path)
    footer_placement = _get_copy_footer_placement(template_path)
    barcode_reader = _generate_barcode_reader(barcode_value)

    output_writer = PdfWriter()

    for copy_index, copy_label in enumerate(copy_labels, start=1):
        footer_text = f"Copy {copy_index}: {copy_label}"
        for page_index, page in enumerate(pdf.pages):
            stamped_page = deepcopy(page)
            page_size = _get_page_size(stamped_page)
            overlay_page = _build_overlay_pdf(
                page_size=page_size,
                footer_text=footer_text,
                footer_placement=footer_placement,
                barcode_reader=(
                    barcode_reader
                    if page_index == barcode_placement.page_index
                    else None
                ),
                barcode_placement=(
                    barcode_placement
                    if page_index == barcode_placement.page_index
                    else None
                ),
            )
            PageMerge(stamped_page).add(overlay_page).render()
            output_writer.addpage(stamped_page)

    output_writer.write(str(output))


def _set_field_readonly(annot: PdfDict):
    """Mark a widget as read-only via the /Ff flag."""
    ff = int(annot.get("/Ff", 0))
    annot["/Ff"] = ff | 1  # bit 1 = ReadOnly


def _fill_pdf(template: Path, output: Path, data: Dict[str, Any]) -> None:
    pdf = PdfReader(str(template))
    for page in pdf.pages:
        annots = page.Annots
        if not annots:
            continue

        for annot in annots:
            field_name_obj = annot.get("/T")
            if not field_name_obj:
                continue

            raw_name = _decode_pdf_field_name(field_name_obj)
            normalized_name = _normalize_field_name(raw_name)
            if normalized_name not in data:
                continue

            value = data[normalized_name]

            # Checkboxes
            if normalized_name in CHECKBOX_FIELDS:
                on = bool(value)
                annot.update(
                    PdfDict(
                        V=PdfName("Yes" if on else "Off"),
                        AS=PdfName("Yes" if on else "Off"),
                    )
                )
                _set_field_readonly(annot)
                continue

            # Airframe unit radios
            if normalized_name in AIRFRAME_UNIT_FIELDS:
                selected = bool(value)
                annot.update(
                    PdfDict(
                        V=PdfName("Yes" if selected else "Off"),
                        AS=PdfName("Yes" if selected else "Off"),
                    )
                )
                _set_field_readonly(annot)
                continue

            # Releasing Authority radios (KCAA/ECAA/GCAA)
            if normalized_name in RELEASING_AUTH_RADIO.values():
                selected = bool(value)
                annot.update(
                    PdfDict(
                        V=PdfName("Yes" if selected else "Off"),
                        AS=PdfName("Yes" if selected else "Off"),
                    )
                )
                _set_field_readonly(annot)
                continue

            # Normal text / numeric fields
            annot.update(PdfDict(V=PdfString.encode(str(value))))
            _set_field_readonly(annot)

    writer = PdfWriter()
    writer.trailer = pdf
    # Some viewers need this to render appearances
    if writer.trailer.Root:
        writer.trailer.Root.NeedAppearances = PdfName("true")

    writer.write(str(output))


def get_fillable_crs_template() -> Path:
    """
    Return a CRS template path that has form appearance metadata enabled.

    Some viewers (Adobe/Google) need NeedAppearances set to render empty
    AcroForm fields correctly. We generate a cached copy to avoid mutating
    the original template.
    """
    template_path = get_latest_crs_template()
    cache_name = (
        f"{template_path.stem}-fillable-"
        f"{int(template_path.stat().st_mtime)}{template_path.suffix}"
    )
    output_path = TEMPLATE_OUTPUT_DIR / cache_name
    if output_path.exists():
        return output_path

    pdf = PdfReader(str(template_path))
    if not pdf.Root:
        pdf.Root = PdfDict()
    if not pdf.Root.AcroForm:
        pdf.Root.AcroForm = PdfDict()
    pdf.Root.AcroForm.NeedAppearances = PdfName("true")

    writer = PdfWriter()
    writer.trailer = pdf
    writer.write(str(output_path))
    return output_path


def create_crs_pdf(crs_id: int) -> Path:
    """
    Create a filled, read-only CRS PDF for the given CRS id.

    Uses the latest available CRS template.
    """
    db = SessionLocal()
    try:
        crs = db.query(crs_models.CRS).filter(crs_models.CRS.id == crs_id).first()
        if not crs:
            raise ValueError(f"CRS id {crs_id} not found")

        data = _build_field_values(crs)
        template_path = get_latest_crs_template()

        filename = f"{crs.crs_serial or f'CRS-{crs_id:06d}'}.pdf"
        output_path = OUTPUT_DIR / filename
        filled_output_path = OUTPUT_DIR / f"{output_path.stem}-filled.pdf"
        _fill_pdf(template_path, filled_output_path, data)

        copy_labels = ["Original", "Duplicate", "Triplicate"]
        _render_multi_copy_pdf(
            filled_template=filled_output_path,
            output=output_path,
            barcode_value=crs.barcode_value,
            template_path=template_path,
            copy_labels=copy_labels,
        )
        return output_path
    finally:
        db.close()


def get_crs_form_template_metadata() -> Dict[str, Any]:
    """
    Introspect the current CRS PDF template and return:

      - page sizes
      - all AcroForm fields with coordinates and inferred type.

    This is generic enough to be reused for other AMOs / forms by just
    changing the template path/pattern.
    """
    template = get_latest_crs_template()
    pdf = PdfReader(str(template))

    pages: List[Dict[str, Any]] = []
    fields: List[Dict[str, Any]] = []

    for page_index, page in enumerate(pdf.pages):
        # Page size from MediaBox
        width = height = 0.0
        mb = getattr(page, "MediaBox", None)
        if mb and len(mb) == 4:
            try:
                x0, y0, x1, y1 = [float(v) for v in mb]
                width = x1 - x0
                height = y1 - y0
            except Exception:
                width = height = 0.0

        pages.append(
            {
                "index": page_index,
                "width": width,
                "height": height,
            }
        )

        annots = getattr(page, "Annots", None)
        if not annots:
            continue

        for annot in annots:
            field_name_obj = annot.get("/T")
            if not field_name_obj:
                continue

            name = _normalize_field_name(_decode_pdf_field_name(field_name_obj))

            # Field rectangle
            x = y = w = h = 0.0
            rect = annot.get("/Rect")
            if rect and len(rect) == 4:
                try:
                    x0, y0, x1, y1 = [float(v) for v in rect]
                    x = x0
                    y = y0
                    w = x1 - x0
                    h = y1 - y0
                except Exception:
                    x = y = w = h = 0.0

            # Field type based on /FT
            ft = annot.get("/FT")
            if not ft and annot.get("/Parent"):
                ft = annot["/Parent"].get("/FT")
            ft_str = str(ft) if ft else ""

            if "/Btn" in ft_str:
                field_type = "button"      # check/radio
            elif "/Tx" in ft_str:
                field_type = "text"
            elif "/Ch" in ft_str:
                field_type = "choice"      # dropdown/list
            else:
                field_type = "unknown"

            fields.append(
                {
                    "name": name,
                    "page_index": page_index,
                    "x": x,
                    "y": y,
                    "width": w,
                    "height": h,
                    "field_type": field_type,
                }
            )

    return {
        "template_filename": template.name,
        "page_count": len(pages),
        "pages": pages,
        "fields": fields,
    }
