from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
READER_CORE = REPOSITORY_ROOT / "frontend/src/pages/manuals/PdfReaderCore.tsx"
READER_ENGINE = REPOSITORY_ROOT / "frontend/src/pages/manuals/pdfReaderEngine.ts"
READER_LAYOUT = REPOSITORY_ROOT / "frontend/src/pages/manuals/publicationReaderZoom.css"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_reader_registers_internal_destinations_and_routes_pdf_link_clicks() -> None:
    source = _source(READER_CORE)

    assert "onItemClick={({ pageIndex, pageNumber }" in source
    assert "jumpToPage(targetPage)" in source
    assert 'renderMode="none"' in source
    assert "renderAnnotationLayer={false}" in source


def test_fit_modes_measure_the_visible_viewport_and_persist_per_revision() -> None:
    source = _source(READER_CORE)

    assert "scroller?.clientHeight || window.innerHeight" in source
    assert "pdf-reader-fit-mode:v1" in source
    assert 'setFitMode("PAGE")' in source
    assert "observer.observe(scroller)" in source


def test_acroform_widgets_are_editable_only_in_controlled_fill_mode() -> None:
    source = _source(READER_CORE)
    stylesheet = _source(READER_LAYOUT)

    assert "loaded.annotationStorage.onSetModified = scheduleAutosave" in source
    assert "renderForms={fillMode && canFill}" in source
    assert "if (canFill) setFillMode(true)" in source
    assert ".pdf-engine-reader.is-fill-mode" in stylesheet
    assert "pointer-events: auto !important" in stylesheet
    assert ".pdf-engine-reader:not(.is-fill-mode)" in stylesheet


def test_pdf_layout_resizes_with_navigation_without_breaking_sticky_controls() -> None:
    stylesheet = _source(READER_LAYOUT)

    assert "--portal-sticky-offset: 44px" in stylesheet
    assert ".publication-native-pdf .pdf-engine-viewport" in stylesheet
    assert "overflow-x: auto" in stylesheet
    assert "grid-template-columns: clamp(230px, 20vw, 320px) minmax(0, 1fr)" in stylesheet
    assert ".publication-reader-width--focus .publication-linked-layout" in stylesheet
    assert ".publication-reader-width--wide .publication-linked-layout" in stylesheet


def test_working_copy_dirty_custody_survives_failed_or_stale_persistence() -> None:
    source = _source(READER_CORE)
    engine = _source(READER_ENGINE)
    persistence = source.split("const persistDraft", 1)[1].split("const scheduleAutosave", 1)[0]
    failure_branch = persistence.split("} catch {", 1)[1].split("} finally {", 1)[0]

    assert "draftSaveInFlightRef" in source
    assert "editGenerationRef.current += 1" in source
    assert "isPdfWorkingCopyGenerationCurrent(savingGeneration, editGenerationRef.current)" in source
    assert "loaded.annotationStorage.onResetModified = undefined" in source
    assert "setWorkingDirty(false)" not in failure_branch
    assert "persistedGeneration === currentGeneration" in engine


def test_reader_scrolling_and_draft_finalization_are_instance_scoped() -> None:
    source = _source(READER_CORE)
    engine = _source(READER_ENGINE)

    assert 'querySelector<HTMLElement>(":scope > .pdf-engine-viewport")' in engine
    assert 'closest<HTMLElement>(".app-shell__scroll")' in engine
    assert "resolvePdfReaderScrollRoot(readerRoot)" in source
    assert "draftLifecycleGenerationRef.current += 1" in source
    assert "await deletePdfWorkingCopy(identity).catch(() => undefined);\n        return;" in source
