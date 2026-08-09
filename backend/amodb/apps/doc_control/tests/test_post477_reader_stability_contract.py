from __future__ import annotations

from pathlib import Path


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _frontend(path: str) -> str:
    return (_repository_root() / path).read_text(encoding="utf-8")


def test_post477_reader_releases_stale_programmatic_navigation() -> None:
    core = _frontend("frontend/src/pages/manuals/PdfReaderCoreV5.tsx")

    assert "releaseProgrammaticNavigation" in core
    assert "releasedExternalToken" in core
    assert "clearReaderHash" in core
    assert "onWheelCapture" in core
    assert "onTouchStartCapture" in core
    assert "onPointerDownCapture" in core
    assert "scheduleScaleStabilization" in core
    assert "SCALE_SETTLE_MS" in core
    assert "window.history.replaceState(window.history.state" in core
    assert "window.history.replaceState(null" not in core


def test_assisted_navigation_understands_the_virtual_reader_scroll_owner() -> None:
    bridge = _frontend("frontend/src/pages/manuals/PublicationAssistedNavigationBridge.tsx")

    assert '.pdfv3-page[data-page-number=' in bridge
    assert 'closest<HTMLElement>(".pdfv3-viewport")' in bridge
    assert 'behavior: "auto"' in bridge


def test_reader_stability_layer_preserves_react_owned_chrome() -> None:
    manual_page = _frontend("frontend/src/pages/manuals/ManualReaderPage.tsx")
    styles = _frontend("frontend/src/pages/manuals/publicationReaderPost477Stability.css")
    brittle_bridge = _repository_root() / "frontend/src/pages/manuals/PublicationReaderChromeBridge.tsx"

    assert 'publicationReaderPost477Stability.css' in manual_page
    assert "PublicationReaderChromeBridge" not in manual_page
    assert not brittle_bridge.exists()
    assert "overflow-anchor: none" in styles
    assert "container-type: inline-size" in styles
    assert "8cqw" in styles
    assert "display: none !important" not in styles
    assert "tenant-shell__topbar-actions" not in styles


def test_consolidation_does_not_use_dom_clicks_to_change_reader_mode() -> None:
    manual_page = _frontend("frontend/src/pages/manuals/ManualReaderPage.tsx")

    assert "createPortal" not in manual_page
    assert "enforceOriginalLayout" not in manual_page
    assert ".click()" not in manual_page
