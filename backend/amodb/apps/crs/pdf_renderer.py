# backend/amodb/apps/crs/pdf_renderer.py

from pathlib import Path
from typing import Any, Dict

from pdfrw import PdfReader, PdfWriter, PdfDict, PdfName

from ...database import SessionLocal
from . import models as crs_models

BASE_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = BASE_DIR / "templates" / "crs" / "crs_form_rev6.pdf"
OUTPUT_DIR = BASE_DIR / "generated" / "crs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Keys for checkboxes and radios in the PDF
CHECKBOX_FIELDS = {"AMP", "AMM", "Mtx Data"}
AIRFRAME_UNIT_FIELDS = {"Hours", "Cycles"}  # radio buttons under "12. Airframe Hour/Cycles"

RELEASING_AUTH_RADIO = {
    "KCAA": "KCAA",
    "ECAA": "ECAA",
    "GCAA": "GCAA",
}


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
        "Barcode": crs.barcode_value,

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
    # Expect crs.signoffs categories like: 'AEROPLANES', 'ENGINES', 'RADIO', ...
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

            raw_name = str(field_name_obj)[1:-1]  # strip parentheses
            if raw_name not in data:
                continue

            value = data[raw_name]

            # Checkboxes
            if raw_name in CHECKBOX_FIELDS:
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
            if raw_name in AIRFRAME_UNIT_FIELDS:
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
            if raw_name in RELEASING_AUTH_RADIO.values():
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
            annot.update(PdfDict(V=str(value)))
            _set_field_readonly(annot)

    writer = PdfWriter()
    writer.trailer = pdf
    # Some viewers need this to render appearances
    if writer.trailer.Root:
        writer.trailer.Root.NeedAppearances = PdfName("true")

    writer.write(str(output))


def create_crs_pdf(crs_id: int) -> Path:
    """
    Create a filled, read-only CRS PDF for the given CRS id.

    Returns the path to the generated file.
    """
    db = SessionLocal()
    try:
        crs = db.query(crs_models.CRS).filter(crs_models.CRS.id == crs_id).first()
        if not crs:
            raise ValueError(f"CRS id {crs_id} not found")

        data = _build_field_values(crs)

        filename = f"{crs.crs_serial or f'CRS-{crs_id:06d}'}.pdf"
        output_path = OUTPUT_DIR / filename
        _fill_pdf(TEMPLATE_PATH, output_path, data)
        return output_path
    finally:
        db.close()
