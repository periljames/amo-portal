"""Reject visual overlays that obscure immutable controlled-template anchors."""
from __future__ import annotations

from typing import Any

from .pdfium_service import PdfEngineError, PdfInspection


def _bbox(value: Any) -> list[float]:
    return [float(component) for component in list(value or [])[:4]]


def _intersects(left: list[float], right: list[float], tolerance: float = 1.0) -> bool:
    if len(left) != 4 or len(right) != 4:
        return False
    return not (
        left[2] <= right[0] - tolerance
        or left[0] >= right[2] + tolerance
        or left[3] <= right[1] - tolerance
        or left[1] >= right[3] + tolerance
    )


def _same_anchor(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_bbox = _bbox(left.get("bbox"))
    right_bbox = _bbox(right.get("bbox"))
    return (
        left.get("signature") == right.get("signature")
        and len(left_bbox) == len(right_bbox) == 4
        and all(abs(left_bbox[index] - right_bbox[index]) <= 3.0 for index in range(4))
    )


def reject_visual_overlays(expected: PdfInspection, candidate: PdfInspection) -> None:
    expected_pages = list((expected.template_fingerprint or {}).get("pages") or [])
    candidate_pages = list((candidate.template_fingerprint or {}).get("pages") or [])
    if len(expected_pages) != len(candidate_pages):
        return

    for page_number, (source_page, completed_page) in enumerate(zip(expected_pages, candidate_pages), start=1):
        source_anchor_boxes = [
            _bbox(anchor.get("bbox"))
            for key in ("words", "images", "drawings")
            for anchor in list(source_page.get(key) or [])
            if len(_bbox(anchor.get("bbox"))) == 4
        ]
        source_drawings = list(source_page.get("drawings") or [])
        source_images = list(source_page.get("images") or [])
        excluded = [_bbox(value) for value in list(source_page.get("excluded_rects") or [])]

        for drawing in list(completed_page.get("drawings") or []):
            box = _bbox(drawing.get("bbox"))
            if any(_intersects(box, field_box) for field_box in excluded):
                continue
            if any(_same_anchor(drawing, source) for source in source_drawings):
                continue
            if any(_intersects(box, anchor_box) for anchor_box in source_anchor_boxes):
                raise PdfEngineError(
                    "PDF_TEMPLATE_VISUAL_OVERLAY",
                    f"Completed PDF page {page_number} contains added vector content over controlled template content",
                    status_code=409,
                )

        for image in list(completed_page.get("images") or []):
            box = _bbox(image.get("bbox"))
            if any(_intersects(box, field_box) for field_box in excluded):
                continue
            if any(
                image.get("digest") == source.get("digest")
                and all(abs(box[index] - _bbox(source.get("bbox"))[index]) <= 3.0 for index in range(4))
                for source in source_images
                if len(_bbox(source.get("bbox"))) == 4
            ):
                continue
            if any(_intersects(box, anchor_box) for anchor_box in source_anchor_boxes):
                raise PdfEngineError(
                    "PDF_TEMPLATE_VISUAL_OVERLAY",
                    f"Completed PDF page {page_number} contains an added image over controlled template content",
                    status_code=409,
                )


__all__ = ["reject_visual_overlays"]
