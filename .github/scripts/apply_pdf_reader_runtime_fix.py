from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"Expected source block not found in {path}: {old[:120]!r}")
    target.write_text(source.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, payload: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    if marker in source:
        return
    target.write_text(source.rstrip() + "\n\n" + payload.lstrip(), encoding="utf-8")


replace(
    "frontend/src/services/publications.ts",
    'import type { ManualReadPayload } from "./manuals";\n',
    'import type { ManualReadPayload } from "./manuals";\nimport { getPdfReaderPerformanceProfile } from "./pdfPerformance";\n',
)
replace(
    "frontend/src/services/publications.ts",
    '''  const partitionedPath = userId ? `${path}${separator}reader_user=${encodeURIComponent(userId)}` : path;\n  return {\n    url: `${getApiBaseUrl()}${partitionedPath}`,\n    httpHeaders: Object.fromEntries(headers),\n    withCredentials: true,\n    rangeChunkSize: 512 * 1024,\n    disableAutoFetch: false,\n    disableRange: false,\n    disableStream: false,\n  };\n''',
    '''  const partitionedPath = userId ? `${path}${separator}reader_user=${encodeURIComponent(userId)}` : path;\n  const performance = getPdfReaderPerformanceProfile();\n  return {\n    url: `${getApiBaseUrl()}${partitionedPath}`,\n    httpHeaders: Object.fromEntries(headers),\n    withCredentials: true,\n    rangeChunkSize: performance.rangeChunkSize,\n    disableAutoFetch: false,\n    disableRange: false,\n    disableStream: false,\n  };\n''',
)

replace(
    "frontend/src/pages/manuals/PdfReaderCoreV2.tsx",
    'import { PDF_DOCUMENT_OPTIONS, pdfDevicePixelRatio } from "./pdfReaderConfig";\n',
    'import { PDF_DOCUMENT_OPTIONS, getPdfReaderPerformanceProfile, pdfDevicePixelRatio } from "./pdfReaderConfig";\n',
)
replace(
    "frontend/src/pages/manuals/PdfReaderCoreV2.tsx",
    '''const nearbyPages = (page: number, count: number, radius = RENDER_RADIUS) => new Set(\n  Array.from({ length: radius * 2 + 1 }, (_, index) => page - radius + index)\n    .filter((value) => value >= 1 && value <= count),\n);\n\nfunction samePages(left: Set<number>, right: Set<number>): boolean {\n''',
    '''const nearbyPages = (page: number, count: number, radius = RENDER_RADIUS) => new Set(\n  Array.from({ length: radius * 2 + 1 }, (_, index) => page - radius + index)\n    .filter((value) => value >= 1 && value <= count),\n);\n\nfunction hotPageWindow(\n  current: Set<number>,\n  page: number,\n  count: number,\n  radius: number,\n  limit: number,\n): Set<number> {\n  const immediate = nearbyPages(page, count, radius);\n  const candidates = [...new Set([...immediate, ...current])]\n    .filter((value) => value >= 1 && value <= count)\n    .sort((left, right) => {\n      const immediatePriority = Number(!immediate.has(left)) - Number(!immediate.has(right));\n      if (immediatePriority) return immediatePriority;\n      const distance = Math.abs(left - page) - Math.abs(right - page);\n      return distance || left - right;\n    });\n  return new Set(candidates.slice(0, Math.max(immediate.size, limit)));\n}\n\nfunction samePages(left: Set<number>, right: Set<number>): boolean {\n''',
)
replace(
    "frontend/src/pages/manuals/PdfReaderCoreV2.tsx",
    '''  const [searchIndex, setSearchIndex] = useState(-1);\n  const [searchBusy, setSearchBusy] = useState(false);\n\n  const source = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);\n''',
    '''  const [searchIndex, setSearchIndex] = useState(-1);\n  const [searchBusy, setSearchBusy] = useState(false);\n\n  const performanceProfile = useMemo(() => getPdfReaderPerformanceProfile(), []);\n  const source = useMemo(() => publicationPdfSource(fileUrl), [fileUrl]);\n''',
)
replace(
    "frontend/src/pages/manuals/PdfReaderCoreV2.tsx",
    '''  const setRenderWindow = useCallback((page: number, count: number) => {\n    const next = nearbyPages(page, count);\n    setRendered((current) => samePages(current, next) ? current : next);\n  }, []);\n''',
    '''  const setRenderWindow = useCallback((page: number, count: number) => {\n    setRendered((current) => {\n      const next = hotPageWindow(\n        current,\n        page,\n        count,\n        performanceProfile.renderRadius,\n        performanceProfile.hotPageLimit,\n      );\n      return samePages(current, next) ? current : next;\n    });\n  }, [performanceProfile.hotPageLimit, performanceProfile.renderRadius]);\n''',
)
replace(
    "frontend/src/pages/manuals/PdfReaderCoreV2.tsx",
    '    }, { root, rootMargin: "1200px 0px", threshold: [0.01, 0.2, 0.6] });\n',
    '    }, { root, rootMargin: `${performanceProfile.prefetchMarginPx}px 0px`, threshold: [0.01, 0.2, 0.6] });\n',
)
replace(
    "frontend/src/pages/manuals/PdfReaderCoreV2.tsx",
    '  }, [clearNavigationTimer, pageCount, pageWidth, publishPage, setRenderWindow]);\n\n  const loadDocument',
    '  }, [clearNavigationTimer, pageCount, pageWidth, performanceProfile.prefetchMarginPx, publishPage, setRenderWindow]);\n\n  const loadDocument',
)
replace(
    "frontend/src/pages/manuals/PdfReaderCoreV2.tsx",
    '                devicePixelRatio={pdfDevicePixelRatio()}\n',
    '                devicePixelRatio={pdfDevicePixelRatio(performanceProfile.maxDevicePixelRatio)}\n',
)

replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '''type NavigationItem = {\n  key: string;\n  title: string;\n''',
    '''type NavigationItem = {\n  key: string;\n  renderKey: string;\n  title: string;\n''',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '''  const navigationItems = useMemo<NavigationItem[]>(() => {\n    if (viewMode === "layout" && nativeOutline.length) {\n      return nativeOutline.map((item) => ({ key: item.id, title: item.title, level: item.level, page: item.page }));\n    }\n    return sections.map((section) => ({\n      key: section.anchor_slug,\n      title: section.heading,\n      level: section.level || 1,\n      page: section.page_start,\n      section,\n    }));\n  }, [nativeOutline, sections, viewMode]);\n\n  const activeNavigationKey = viewMode === "layout" && nativeOutline.length ? activeOutlineKey : activeSection;\n\n  const expandAncestors = useCallback((key: string) => {\n    const index = navigationItems.findIndex((item) => item.key === key);\n''',
    '''  const navigationItems = useMemo<NavigationItem[]>(() => {\n    if (viewMode === "layout" && nativeOutline.length) {\n      return nativeOutline.map((item) => ({\n        key: item.id,\n        renderKey: `outline:${item.id}`,\n        title: item.title,\n        level: item.level,\n        page: item.page,\n      }));\n    }\n    return sections.map((section, index) => ({\n      key: section.anchor_slug,\n      renderKey: `section:${section.id}:${index}`,\n      title: section.heading,\n      level: section.level || 1,\n      page: section.page_start,\n      section,\n    }));\n  }, [nativeOutline, sections, viewMode]);\n\n  const activeNavigationKey = viewMode === "layout" && nativeOutline.length ? activeOutlineKey : activeSection;\n  const activeNavigationRenderKey = navigationItems.find((item) => item.key === activeNavigationKey)?.renderKey\n    || navigationItems.find((item) => safeAnchor(item.key) === safeAnchor(activeNavigationKey))?.renderKey\n    || "";\n\n  const expandAncestors = useCallback((renderKey: string) => {\n    const index = navigationItems.findIndex((item) => item.renderKey === renderKey);\n''',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '        ancestors.push(item.key);\n',
    '        ancestors.push(item.renderKey);\n',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '''  useEffect(() => {\n    if (!activeNavigationKey) return;\n    expandAncestors(activeNavigationKey);\n    const row = navRowRefs.current[activeNavigationKey];\n''',
    '''  useEffect(() => {\n    if (!activeNavigationRenderKey) return;\n    expandAncestors(activeNavigationRenderKey);\n    const row = navRowRefs.current[activeNavigationRenderKey];\n''',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '  }, [activeNavigationKey, expandAncestors]);\n',
    '  }, [activeNavigationRenderKey, expandAncestors]);\n',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '        if (collapsed.has(candidate.key)) return true;\n',
    '        if (collapsed.has(candidate.renderKey)) return true;\n',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '    setCollapsed(new Set(navigationItems.filter((item, index) => navigationItems[index + 1] && navigationItems[index + 1].level > item.level).map((item) => item.key)));\n',
    '    setCollapsed(new Set(navigationItems.filter((item, index) => navigationItems[index + 1] && navigationItems[index + 1].level > item.level).map((item) => item.renderKey)));\n',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    '''              const isCollapsed = collapsed.has(item.key);\n              const isActive = activeNavigationKey === item.key || safeAnchor(activeNavigationKey) === safeAnchor(item.key);\n              return (\n                <div\n                  key={item.key}\n                  ref={(element) => { navRowRefs.current[item.key] = element; }}\n''',
    '''              const isCollapsed = collapsed.has(item.renderKey);\n              const isActive = activeNavigationKey === item.key || safeAnchor(activeNavigationKey) === safeAnchor(item.key);\n              return (\n                <div\n                  key={item.renderKey}\n                  ref={(element) => { navRowRefs.current[item.renderKey] = element; }}\n''',
)
replace(
    "frontend/src/pages/manuals/PublicationsReaderPage.tsx",
    'onClick={() => toggleCollapsed(item.key)} aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${item.title}`}',
    'onClick={() => toggleCollapsed(item.renderKey)} aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${item.title}`}',
)

replace(
    "backend/amodb/apps/doc_control/tests/test_pdf_reader_interaction_contract.py",
    '    assert \'rootMargin: "1200px 0px"\' in source\n',
    '    assert "performanceProfile.prefetchMarginPx" in source\n    assert "hotPageWindow" in source\n',
)
replace(
    "backend/amodb/apps/doc_control/tests/test_pdf_reader_interaction_contract.py",
    '''def test_jpx_images_use_secure_pdfjs_decoder_fallback() -> None:\n    config = _source(READER_CONFIG)\n\n    assert "useWasm: false" in config\n    assert "JavaScript OpenJPEG fallback" in config\n    assert "isEvalSupported: false" in config\n    assert "enableScripting: false" in config\n''',
    '''def test_jpx_images_use_packaged_pdfjs_decoders() -> None:\n    config = _source(READER_CONFIG)\n    vite = _source(REPOSITORY_ROOT / "frontend/vite.config.ts")\n\n    assert "useWasm: true" in config\n    assert "wasmUrl:" in config\n    assert "cMapUrl:" in config\n    assert "standardFontDataUrl:" in config\n    assert "__PDFJS_ASSET_VERSION__" in config\n    assert "viteStaticCopy" in vite\n    for directory in ("wasm", "cmaps", "standard_fonts"):\n        assert directory in vite\n    assert "isEvalSupported: false" in config\n    assert "enableScripting: false" in config\n''',
)

append_once(
    "backend/amodb/apps/doc_control/tests/test_pdf_reader_source_contract.py",
    "def test_reader_network_profile_bursts_on_capable_clients",
    '''def test_reader_network_profile_bursts_on_capable_clients() -> None:\n    performance = _read("frontend/src/services/pdfPerformance.ts")\n    publications = _read("frontend/src/services/publications.ts")\n    core = _reader_core()\n\n    assert "rangeChunkSize: 4 * MIB" in performance\n    assert "rangeChunkSize: 128 * KIB" in performance\n    assert 'mode: "burst"' in performance\n    assert "performance.rangeChunkSize" in publications\n    assert "disableAutoFetch: false" in publications\n    assert "disableRange: false" in publications\n    assert "disableStream: false" in publications\n    assert "performanceProfile.renderRadius" in core\n    assert "performanceProfile.hotPageLimit" in core\n    assert "performanceProfile.prefetchMarginPx" in core\n\n\ndef test_publication_navigation_uses_unique_render_identity() -> None:\n    reader = _read("frontend/src/pages/manuals/PublicationsReaderPage.tsx")\n\n    assert "renderKey: string" in reader\n    assert "renderKey: `section:${section.id}:${index}`" in reader\n    assert "key={item.renderKey}" in reader\n    assert "navRowRefs.current[item.renderKey]" in reader\n    assert "collapsed.has(item.renderKey)" in reader\n''',
)

print("Applied PDF reader decoder, performance, cache-window and TOC identity patch.")
