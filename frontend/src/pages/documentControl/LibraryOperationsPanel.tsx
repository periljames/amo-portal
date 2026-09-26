import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  Barcode,
  BookOpenCheck,
  Camera,
  Database,
  CircleX,
  Download,
  ExternalLink,
  Globe2,
  LibraryBig,
  PackageCheck,
  Plus,
  RefreshCcw,
  Search,
  Undo2,
  Upload,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  cancelLibraryHold,
  closeLibraryInventorySession,
  createLibraryInventorySession,
  getLibraryInventorySession,
  circulateLibraryHolding,
  createLibraryCatalogItem,
  createLibraryHolding,
  downloadLibraryHoldingLabel,
  getMyLibraryAccount,
  importLibraryMarcXml,
  downloadLibraryMarcXml,
  listLibraryCatalog,
  listLibraryHoldings,
  controlLibraryHolding,
  placeLibraryHold,
  scanLibraryHolding,
  scanLibraryInventorySession,
  searchLibraryPatrons,
  searchExternalCatalog,
  searchTenantWarehouse,
  type ExternalCatalogResult,
  type LibraryCatalogItem,
  type LibraryHoldingRegisterResponse,
  type LibraryHoldingScan,
  type LibraryInventorySession,
  type LibraryPatron,
  type MyLibraryAccount,
  type WarehouseSearchResponse,
  type WarehouseSearchScope,
  type WarehouseRevisionException,
} from "../../services/documentLibrary";
import "./libraryOperations.css";

type PanelMode = "warehouse" | "catalog" | "scan" | "inventory" | "internet" | "account";

type Props = {
  tenant: string;
  canControl: boolean;
  initialMode?: PanelMode;
  initialScan?: string | null;
  onClose: () => void;
};

const WAREHOUSE_SCOPES: Array<{ id: WarehouseSearchScope; label: string }> = [
  { id: "everything", label: "Everything" },
  { id: "repository", label: "Repository" },
  { id: "library", label: "Library" },
  { id: "records", label: "Records" },
  { id: "external", label: "External" },
];

type BarcodeDetectorResult = { rawValue: string };
type BarcodeDetectorLike = {
  detect(source: CanvasImageSource): Promise<BarcodeDetectorResult[]>;
};
type BarcodeDetectorConstructor = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

function cleanCatalogueCode(result: ExternalCatalogResult): string {
  const provider = result.provider === "GOOGLE_BOOKS" ? "GB" : "OL";
  const identity = String(
    result.identifiers?.isbn_13
      || result.identifiers?.isbn_10
      || result.provider_id
      || result.title,
  )
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 70);
  return `LIB-${provider}-${identity || "ITEM"}`;
}

function displayAuthors(item: { authors?: string[] }): string {
  return item.authors?.filter(Boolean).join(", ") || "Unknown author";
}

function formatDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function CameraScanner({ onDetected, onClose }: { onDetected: (value: string) => void; onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [engine, setEngine] = useState<"native" | "zxing" | "">("");

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;
    let timer = 0;
    let zxingReader: { reset: () => void } | null = null;
    const detectorCtor = (window as unknown as { BarcodeDetector?: BarcodeDetectorConstructor }).BarcodeDetector;

    const nativeScan = async () => {
      if (!detectorCtor || !videoRef.current) return false;
      const detector = new detectorCtor({
        formats: ["qr_code", "code_128", "code_39", "ean_13", "ean_8", "upc_a", "upc_e", "data_matrix"],
      });
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      if (cancelled || !videoRef.current) return true;
      videoRef.current.srcObject = stream;
      await videoRef.current.play();
      setEngine("native");
      setRunning(true);
      const tick = async () => {
        if (cancelled || !videoRef.current) return;
        try {
          const results = await detector.detect(videoRef.current);
          const value = results.find((row) => row.rawValue)?.rawValue?.trim();
          if (value) {
            onDetected(value);
            return;
          }
        } catch {
          // Camera focus and motion can make an individual frame undecodable.
        }
        timer = window.setTimeout(() => void tick(), 160);
      };
      void tick();
      return true;
    };

    const zxingScan = async () => {
      if (!videoRef.current) return;
      const { BrowserMultiFormatReader } = await import("@zxing/library");
      if (cancelled || !videoRef.current) return;
      const reader = new BrowserMultiFormatReader();
      zxingReader = reader;
      setEngine("zxing");
      setRunning(true);
      try {
        const result = await reader.decodeOnceFromVideoDevice(undefined, videoRef.current);
        if (!cancelled) onDetected(result.getText().trim());
      } finally {
        reader.reset();
      }
    };

    const begin = async () => {
      try {
        const nativeStarted = await nativeScan();
        if (!nativeStarted) await zxingScan();
      } catch (caught) {
        if (cancelled) return;
        // If the native detector exists but its camera pipeline fails for a
        // browser-specific reason, release it before trying ZXing once.
        stream?.getTracks().forEach((track) => track.stop());
        stream = null;
        try {
          await zxingScan();
        } catch (fallbackError) {
          const message = fallbackError instanceof Error
            ? fallbackError.message
            : caught instanceof Error
              ? caught.message
              : "Camera scanning could not be started.";
          setError(`${message} Use a USB/Bluetooth scanner or enter the barcode manually.`);
          setRunning(false);
        }
      }
    };

    void begin();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
      stream?.getTracks().forEach((track) => track.stop());
      zxingReader?.reset();
    };
  }, [onDetected]);

  return <div className="library-camera">
    <div className="library-camera__frame">
      <video ref={videoRef} playsInline muted aria-label="Barcode scanner camera" />
      <span aria-hidden="true" />
    </div>
    {error
      ? <p className="library-ops__error" role="alert">{error}</p>
      : <p>{running ? `Scanning with ${engine === "native" ? "browser barcode detection" : "ZXing fallback"}…` : "Starting camera…"}</p>}
    <button type="button" className="dc-button" onClick={onClose}><CircleX size={14} /> Close camera</button>
  </div>;
}

export default function LibraryOperationsPanel({
  tenant,
  canControl,
  initialMode = "catalog",
  initialScan,
  onClose,
}: Props) {
  const navigate = useNavigate();
  const marcFileRef = useRef<HTMLInputElement | null>(null);
  const [mode, setMode] = useState<PanelMode>(initialScan ? "scan" : initialMode);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [warehouseQuery, setWarehouseQuery] = useState("");
  const [warehouseScope, setWarehouseScope] = useState<WarehouseSearchScope>("everything");
  const [warehouse, setWarehouse] = useState<WarehouseSearchResponse | null>(null);
  const [revisionExceptions, setRevisionExceptions] = useState<WarehouseRevisionException[]>([]);
  const [catalogQuery, setCatalogQuery] = useState("");
  const [catalog, setCatalog] = useState<LibraryCatalogItem[]>([]);
  const [scanCode, setScanCode] = useState(initialScan || "");
  const [scan, setScan] = useState<LibraryHoldingScan | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [internetQuery, setInternetQuery] = useState("");
  const [internetResults, setInternetResults] = useState<ExternalCatalogResult[]>([]);
  const [internetLinks, setInternetLinks] = useState<Record<string, string>>({});
  const [internetPrivacy, setInternetPrivacy] = useState("");
  const [account, setAccount] = useState<MyLibraryAccount | null>(null);
  const [inventory, setInventory] = useState<LibraryHoldingRegisterResponse | null>(null);
  const [inventoryQuery, setInventoryQuery] = useState("");
  const [inventorySession, setInventorySession] = useState<LibraryInventorySession | null>(null);
  const [inventoryLocation, setInventoryLocation] = useState("");
  const [inventoryScanCode, setInventoryScanCode] = useState("");
  const [inventoryCameraOpen, setInventoryCameraOpen] = useState(false);
  const [inventoryReason, setInventoryReason] = useState("");
  const [selectedCatalog, setSelectedCatalog] = useState<LibraryCatalogItem | null>(null);
  const [barcode, setBarcode] = useState("");
  const [callNumber, setCallNumber] = useState("");
  const [location, setLocation] = useState("Document Control library");
  const [acknowledgement, setAcknowledgement] = useState(false);
  const [patronQuery, setPatronQuery] = useState("");
  const [patrons, setPatrons] = useState<LibraryPatron[]>([]);
  const [selectedPatronId, setSelectedPatronId] = useState("");

  const run = useCallback(async <T,>(operation: () => Promise<T>): Promise<T | null> => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      return await operation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The library operation could not be completed.");
      return null;
    } finally {
      setBusy(false);
    }
  }, []);

  const loadInventory = useCallback(async (query = inventoryQuery) => {
    if (!canControl) return;
    const result = await run(() => listLibraryHoldings(tenant, { q: query.trim() || undefined, perPage: 100 }));
    if (result) setInventory(result);
  }, [canControl, inventoryQuery, run, tenant]);

  const loadAccount = useCallback(async () => {
    const result = await run(() => getMyLibraryAccount(tenant));
    if (result) setAccount(result);
  }, [run, tenant]);

  const loadCatalog = useCallback(async (query = catalogQuery) => {
    const result = await run(() => listLibraryCatalog(tenant, { q: query.trim() || undefined, perPage: 50 }));
    if (result) setCatalog(result.items);
  }, [catalogQuery, run, tenant]);

  const performScan = useCallback(async (value = scanCode) => {
    const code = value.trim();
    if (!code) return;
    setCameraOpen(false);
    const result = await run(() => scanLibraryHolding(tenant, code));
    if (result) {
      setScanCode(code);
      setScan(result);
      setNotice(`${result.item.title} · ${result.holding.status.replaceAll("_", " ")} · ${result.holding.current_location}`);
      if (typeof navigator !== "undefined" && "vibrate" in navigator) navigator.vibrate?.(35);
      setMode("scan");
    }
  }, [run, scanCode, tenant]);

  useEffect(() => {
    if (initialScan?.trim()) void performScan(initialScan);
  }, [initialScan, performScan]);

  useEffect(() => {
    if (mode === "account" && !account) void loadAccount();
    if (mode === "catalog" && !catalog.length) void loadCatalog("");
    if (mode === "inventory" && canControl && !inventory) void loadInventory("");
  }, [account, canControl, catalog.length, inventory, loadAccount, loadCatalog, loadInventory, mode]);

  // Hardware barcode scanners commonly behave like a keyboard and terminate with
  // Enter. Keeping a focused plain input means those devices work without drivers.
  const scannerInput = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void performScan();
  };


  const searchWarehouse = async (event: FormEvent) => {
    event.preventDefault();
    const query = warehouseQuery.trim();
    if (!query) return;
    const result = await run(() => searchTenantWarehouse(tenant, query, 12, warehouseScope));
    if (result) setWarehouse(result);
  };

  const reconcileWarehouse = async () => {
    if (!canControl) return;
    const result = await run(() => reconcileTenantWarehouse(tenant));
    if (!result) return;
    const exceptions = await run(() => listWarehouseRevisionExceptions(tenant, 1, 100));
    if (exceptions) setRevisionExceptions(exceptions.items);
    if (warehouseQuery.trim()) {
      const refreshed = await run(() => searchTenantWarehouse(tenant, warehouseQuery.trim(), 12, warehouseScope));
      if (refreshed) setWarehouse(refreshed);
    }
    const indexed = result.counts.controlled_documents + result.counts.library_items + result.counts.retained_records;
    const copies = result.counts.controlled_copies + result.counts.library_holdings;
    setNotice(`Warehouse reconciled: ${indexed} governed resources and ${copies} physical copies synchronized.`);
  };

  const externalSearch = async (event: FormEvent) => {
    event.preventDefault();
    if (!internetQuery.trim()) return;
    const result = await run(() => searchExternalCatalog(tenant, internetQuery.trim(), "all", 8));
    if (!result) return;
    setInternetResults(result.items);
    setInternetLinks(result.links);
    setInternetPrivacy(result.privacy_notice);
  };

  const importExternal = async (result: ExternalCatalogResult) => {
    const yearText = String(result.published_date || "").slice(0, 4);
    const publicationYear = /^\d{4}$/.test(yearText) ? Number(yearText) : null;
    const created = await run(() => createLibraryCatalogItem(tenant, {
      catalogue_code: cleanCatalogueCode(result),
      material_type: result.material_type || "BOOK",
      title: result.title,
      subtitle: result.subtitle,
      authors: result.authors || [],
      publisher: result.publisher,
      publication_year: publicationYear,
      language: result.language,
      identifiers: result.identifiers || {},
      subjects: result.subjects || [],
      description: result.description,
      source_provider: result.provider,
      source_record_id: result.provider_id,
      source_url: result.source_url,
      cover_url: result.cover_url,
      circulation_policy: {
        circulatable: true,
        self_checkout: false,
        loan_period_days: 14,
        max_renewals: 2,
      },
    }));
    if (created) {
      setSelectedCatalog(created);
      setMode("catalog");
      setNotice("Catalogue record added. Register the physical copy below when it arrives.");
      void loadCatalog("");
    }
  };

  const importMarcFile = async (file: File | null) => {
    if (!file || !canControl) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith(".xml") && !lower.endsWith(".marcxml")) {
      setError("Select a MARCXML .xml or .marcxml file.");
      return;
    }
    const xml = await file.text();
    const result = await run(() => importLibraryMarcXml(tenant, xml, {
      circulationPolicy: {
        circulatable: true,
        self_checkout: false,
        loan_period_days: 14,
        max_renewals: 2,
      },
    }));
    if (!result) return;
    setNotice(`MARC 21 import complete: ${result.imported || 0} imported, ${result.skipped} skipped${result.errors?.length ? `, ${result.errors.length} conflict(s)` : ""}.`);
    if (marcFileRef.current) marcFileRef.current.value = "";
    await loadCatalog("");
  };

  const exportMarc = async () => {
    const result = await run(async () => {
      await downloadLibraryMarcXml(tenant, `${tenant.toLowerCase()}-library-marc21.xml`);
      return true;
    });
    if (result) setNotice("MARC 21 catalogue export generated.");
  };

  const registerHolding = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedCatalog || !barcode.trim() || !location.trim()) return;
    const holding = await run(() => createLibraryHolding(tenant, selectedCatalog.id, {
      barcode: barcode.trim(),
      call_number: callNumber.trim() || null,
      home_location: location.trim(),
    }));
    if (holding) {
      setNotice(`${selectedCatalog.title} · physical item ${holding.barcode} registered.`);
      setBarcode("");
      setCallNumber("");
      await loadCatalog(catalogQuery);
    }
  };


  const loadPatrons = async () => {
    if (!canControl) return;
    const result = await run(() => searchLibraryPatrons(tenant, patronQuery.trim() || undefined, 30));
    if (result) setPatrons(result.items);
  };

  const circulation = async (action: "CHECK_OUT" | "CHECK_IN" | "RENEW" | "VERIFY_LOCATION") => {
    if (!scan) return;
    if (action === "CHECK_OUT" && scan.capabilities.control && !selectedPatronId) {
      setError("Select the borrower before librarian checkout.");
      return;
    }
    const result = await run(() => circulateLibraryHolding(tenant, scan.holding.id, {
      action,
      patron_user_id: action === "CHECK_OUT" && scan.capabilities.control ? selectedPatronId : undefined,
      acknowledgement: action === "CHECK_OUT" ? acknowledgement : undefined,
      location: action === "VERIFY_LOCATION" || action === "CHECK_IN" ? scan.holding.home_location : undefined,
    }));
    if (result) {
      setAcknowledgement(false);
      if (action === "CHECK_OUT") { setSelectedPatronId(""); setPatronQuery(""); setPatrons([]); }
      setNotice(action === "CHECK_OUT" ? "Custody accepted and item checked out." : action === "CHECK_IN" ? "Item checked in." : action === "RENEW" ? "Loan renewed." : "Location verified.");
      await performScan(scan.holding.barcode);
      await loadAccount();
    }
  };

  const controlHolding = async (
    holdingId: string,
    action: "MARK_LOST" | "MARK_DAMAGED" | "SEND_REPAIR" | "RETURN_TO_SHELF" | "WITHDRAW",
  ) => {
    const reason = inventoryReason.trim();
    if (!reason) {
      setError("Record the physical-control reason before changing item status.");
      return;
    }
    const result = await run(() => controlLibraryHolding(tenant, holdingId, { action, reason }));
    if (result) {
      setInventoryReason("");
      setNotice(`Physical item updated to ${result.holding.status.replaceAll("_", " ")}.`);
      await loadInventory();
    }
  };


  const startInventorySession = async () => {
    const location = inventoryLocation.trim();
    if (!location) {
      setError("Enter the shelf, room or controlled location to inventory.");
      return;
    }
    const result = await run(() => createLibraryInventorySession(tenant, { location_prefix: location }));
    if (result) {
      setInventorySession(result);
      setNotice(`Inventory started for ${result.location_prefix}. Scan each physical item once.`);
    }
  };

  const inventoryScan = async (value = inventoryScanCode) => {
    if (!inventorySession) return;
    const code = value.trim();
    if (!code) return;
    const result = await run(() => scanLibraryInventorySession(tenant, inventorySession.id, {
      code,
      observed_location: inventoryLocation.trim() || inventorySession.location_prefix,
    }));
    if (!result) return;
    setInventoryScanCode("");
    setInventoryCameraOpen(false);
    setNotice(`${result.title} · ${result.outcome.replaceAll("_", " ")}`);
    const refreshed = await run(() => getLibraryInventorySession(tenant, inventorySession.id));
    if (refreshed) setInventorySession(refreshed);
    await loadInventory();
  };

  const closeInventory = async () => {
    if (!inventorySession) return;
    const result = await run(() => closeLibraryInventorySession(tenant, inventorySession.id));
    if (result) {
      setInventorySession(result);
      setNotice(`Inventory closed: ${result.observed_count}/${result.expected_count} observed, ${result.missing_count} missing, ${result.misplaced_count} misplaced.`);
      await loadInventory();
    }
  };

  const placeHold = async (item: LibraryCatalogItem) => {
    const result = await run(() => placeLibraryHold(tenant, item.id));
    if (result) {
      setNotice(result.already_exists ? "You already have an active hold on this title." : "Hold placed.");
      await loadAccount();
    }
  };

  const cancelHold = async (holdId: string) => {
    const result = await run(() => cancelLibraryHold(tenant, holdId));
    if (result) {
      setNotice("Hold cancelled.");
      await loadAccount();
    }
  };

  const availableForCheckout = Boolean(scan?.holding.status === "AVAILABLE" && (scan?.capabilities.control || scan?.capabilities.self_checkout));
  const canCheckIn = Boolean(scan?.capabilities.check_in && scan?.holding.status === "CHECKED_OUT");
  const canRenew = Boolean(scan?.capabilities.renew && scan?.holding.status === "CHECKED_OUT");
  const canPlaceHold = Boolean(scan?.capabilities.place_hold && scan?.holding.status !== "AVAILABLE");

  const modes = useMemo(() => [
    ["warehouse", "Search everything", Database],
    ["catalog", "Library catalogue", LibraryBig],
    ["scan", "Scan / circulate", Barcode],
    ...(canControl ? [["inventory", "Inventory & custody", PackageCheck] as const] : []),
    ["internet", "Internet catalogue", Globe2],
    ["account", "My loans & holds", BookOpenCheck],
  ] as const, [canControl]);

  return <aside className="library-ops" role="dialog" aria-modal="true" aria-label="Library services">
    <header className="library-ops__header">
      <div><LibraryBig size={19} /><span><strong>Knowledge warehouse & library</strong><small>Controlled content, records, physical custody and external discovery</small></span></div>
      <button type="button" className="dc-button" onClick={onClose}><CircleX size={15} /> Close</button>
    </header>
    <nav className="library-ops__tabs" aria-label="Library service">
      {modes.map(([id, label, Icon]) => <button key={id} type="button" className={mode === id ? "active" : ""} onClick={() => setMode(id)}><Icon size={15} /> {label}</button>)}
    </nav>
    {error ? <div className="library-ops__error" role="alert">{error}</div> : null}
    {notice ? <div className="library-ops__notice" role="status">{notice}</div> : null}

    <div className="library-ops__body">
      {mode === "warehouse" ? <>
        <div className="library-warehouse-toolbar">
          <div className="library-warehouse-scopes" role="group" aria-label="Warehouse search scope">
            {WAREHOUSE_SCOPES.map((scope) => <button key={scope.id} type="button" className={warehouseScope === scope.id ? "active" : ""} onClick={() => setWarehouseScope(scope.id)}>{scope.label}</button>)}
          </div>
          {canControl ? <button type="button" className="dc-button" disabled={busy} onClick={() => void reconcileWarehouse()}><RefreshCcw size={14} /> Reconcile warehouse</button> : null}
        </div>
        <form className="library-ops__search" onSubmit={searchWarehouse}>
          <Database size={16} /><input value={warehouseQuery} onChange={(event) => setWarehouseQuery(event.target.value)} placeholder={warehouseScope === "external" ? "Enter public search terms" : "Document number, title, ISBN, record number, clause or text"} autoFocus /><button className="dc-button dc-button--primary" disabled={busy}>Search</button>
        </form>
        <p className="library-ops__privacy">Internal results are permission-filtered before return. External scope sends only the words you enter; approved tenant content is never appended to the public query.</p>
        {canControl && revisionExceptions.length ? <section className="library-revision-exceptions">
          <header><span><strong>{revisionExceptions.length} physical cop{revisionExceptions.length === 1 ? "y" : "ies"} require revision</strong><small>Installed revision does not match the required current revision.</small></span></header>
          {revisionExceptions.slice(0, 6).map((exception) => <button type="button" key={exception.copy.id} onClick={() => exception.resource.target_path && navigate(exception.resource.target_path)}>
            <span><strong>{exception.resource.canonical_code} · {exception.copy.copy_number || exception.copy.barcode}</strong><small>{exception.copy.location || "Location not recorded"}</small></span>
            <em>{exception.copy.installed_version || "?"} → {exception.copy.required_version || "?"}</em>
          </button>)}
        </section> : null}
        {warehouse ? <div className="library-warehouse-results">
          {([
            ["Governed resources", warehouse.groups.governed_resources],
            ["Controlled document hits", warehouse.groups.controlled_documents],
            ["Library holdings", warehouse.groups.library_items],
            ["Retained records", warehouse.groups.retained_records],
          ] as const).map(([label, items]) => <section key={label}>
            <header><strong>{label}</strong><small>{items.length} match{items.length === 1 ? "" : "es"}</small></header>
            {items.map((item) => <button type="button" key={`${item.kind}:${item.id}:${item.heading || item.record_number || ""}`} className="library-warehouse-result" onClick={() => item.target_path && navigate(item.target_path)}>
              <span>
                <small>{item.code || item.series_code || item.catalogue_code || item.resource_type || item.kind.replaceAll("_", " ")}</small>
                <strong>{item.title}</strong>
                {item.heading ? <em>{item.heading}{item.page_number ? ` · page ${item.page_number}` : ""}</em> : null}
                {item.copies?.total ? <em>{item.copies.total} physical cop{item.copies.total === 1 ? "y" : "ies"}{item.copies.revision_required ? ` · ${item.copies.revision_required} revision required` : ""}</em> : null}
                {item.snippet ? <p>{item.snippet}</p> : null}
              </span>
            </button>)}
            {!items.length ? <p className="library-ops__hint">No authorized matches in this scope.</p> : null}
          </section>)}
          {warehouse.internet.enabled ? <section className="library-warehouse-results__internet"><header><strong>Search the public web</strong><small>Explicit external navigation</small></header><div className="library-external-links">{Object.entries(warehouse.internet.links).map(([label, href]) => <a key={label} href={href} target="_blank" rel="noreferrer"><ExternalLink size={13} /> {label.replaceAll("_", " ")}</a>)}</div></section> : null}
        </div> : <p className="library-ops__hint">Search one governed warehouse for controlled documents, exact identifiers, books, physical copies and retained records. Deep document hits still open at the matching section/page where available.</p>}
      </> : null}
      {mode === "catalog" ? <>
        {canControl ? <div className="library-catalog-tools">
          <input ref={marcFileRef} type="file" accept=".xml,.marcxml,application/xml,text/xml" hidden onChange={(event) => void importMarcFile(event.target.files?.[0] || null)} />
          <button type="button" className="dc-button" disabled={busy} onClick={() => marcFileRef.current?.click()}><Upload size={14} /> Import MARCXML</button>
          <button type="button" className="dc-button" disabled={busy} onClick={() => void exportMarc()}><Download size={14} /> Export MARCXML</button>
          <span>MARC 21 bibliographic interchange; imported identifiers remain searchable across the warehouse.</span>
        </div> : null}
        <form className="library-ops__search" onSubmit={(event) => { event.preventDefault(); void loadCatalog(); }}>
          <Search size={16} /><input value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="Search tenant books, journals, ISBN, author, subject…" autoFocus /><button className="dc-button" disabled={busy}>Search</button>
        </form>
        <div className="library-catalog-list">
          {catalog.map((item) => <article key={item.id}>
            <div className="library-catalog-list__cover">{item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : <LibraryBig size={24} />}</div>
            <div><small>{item.catalogue_code} · {item.material_type.replaceAll("_", " ")}</small><strong>{item.title}</strong><span>{displayAuthors(item)}</span><span>{item.publisher || "Publisher not recorded"}{item.publication_year ? ` · ${item.publication_year}` : ""}</span><span>{item.holdings ? `${item.holdings.available} available · ${item.holdings.checked_out} checked out · ${item.holdings.on_hold} on hold` : "No physical holdings"}</span></div>
            <div className="library-catalog-list__actions">
              {canControl ? <button type="button" className="dc-button" onClick={() => setSelectedCatalog(item)}><Plus size={14} /> Add copy</button> : null}
              {item.holdings && item.holdings.available === 0 && item.circulation_policy.circulatable ? <button type="button" className="dc-button" onClick={() => void placeHold(item)}>Place hold</button> : null}
              {item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Source</a> : null}
            </div>
          </article>)}
          {!busy && !catalog.length ? <p>No catalogue item matches this search.</p> : null}
        </div>
        {canControl && selectedCatalog ? <form className="library-holding-form" onSubmit={registerHolding}>
          <header><strong>Register physical holding</strong><span>{selectedCatalog.title}</span></header>
          <label><span>Barcode</span><input value={barcode} onChange={(event) => setBarcode(event.target.value)} required placeholder="Scan or enter barcode" /></label>
          <label><span>Call number</span><input value={callNumber} onChange={(event) => setCallNumber(event.target.value)} placeholder="Shelf/classification call number" /></label>
          <label className="wide"><span>Home location</span><input value={location} onChange={(event) => setLocation(event.target.value)} required /></label>
          <div className="library-holding-form__actions"><button type="button" className="dc-button" onClick={() => setSelectedCatalog(null)}>Cancel</button><button type="submit" className="dc-button dc-button--primary" disabled={busy}><PackageCheck size={14} /> Register copy</button></div>
        </form> : null}
      </> : null}

      {mode === "scan" ? <>
        <form className="library-ops__search" onSubmit={scannerInput}>
          <Barcode size={16} /><input value={scanCode} onChange={(event) => setScanCode(event.target.value)} placeholder="Scan barcode / QR or type item code" autoFocus /><button className="dc-button dc-button--primary" disabled={busy}>Resolve</button><button type="button" className="dc-button" onClick={() => setCameraOpen((value) => !value)}><Camera size={14} /> Camera</button>
        </form>
        {cameraOpen ? <CameraScanner onDetected={(value) => void performScan(value)} onClose={() => setCameraOpen(false)} /> : null}
        {scan ? <article className="library-scan-card">
          <header><div><small>{scan.item.catalogue_code}</small><h2>{scan.item.title}</h2><p>{displayAuthors(scan.item)}</p></div><strong className={scan.holding.overdue ? "overdue" : ""}>{scan.holding.status.replaceAll("_", " ")}</strong></header>
          <dl>
            <div><dt>Barcode</dt><dd>{scan.holding.barcode}</dd></div>
            <div><dt>Call no.</dt><dd>{scan.holding.call_number || "—"}</dd></div>
            <div><dt>Location</dt><dd>{scan.holding.current_location}</dd></div>
            <div><dt>Home</dt><dd>{scan.holding.home_location}</dd></div>
            <div><dt>Due</dt><dd>{formatDate(scan.holding.due_at)}</dd></div>
            <div><dt>Renewals</dt><dd>{scan.holding.renewal_count ?? "—"}</dd></div>
          </dl>
          {availableForCheckout && scan.capabilities.control ? <div className="library-patron-picker">
            <label><span>Borrower</span><div><input value={patronQuery} onChange={(event) => setPatronQuery(event.target.value)} placeholder="Search name, staff code or email" /><button type="button" className="dc-button" disabled={busy} onClick={() => void loadPatrons()}>Find</button></div></label>
            {patrons.length ? <select value={selectedPatronId} onChange={(event) => setSelectedPatronId(event.target.value)}><option value="">Select borrower</option>{patrons.map((patron) => <option key={patron.id} value={patron.id}>{patron.name} · {patron.staff_code || patron.email}{patron.department ? ` · ${patron.department}` : ""}</option>)}</select> : null}
          </div> : null}
          {availableForCheckout ? <label className="library-ack"><input type="checkbox" checked={acknowledgement} onChange={(event) => setAcknowledgement(event.target.checked)} /><span>{scan.capabilities.control ? "Borrower custody and return obligation have been acknowledged." : "I accept custody of this physical item and responsibility to return it by the assigned due date."}</span></label> : null}
          <div className="library-scan-card__actions">
            {availableForCheckout ? <button type="button" className="dc-button dc-button--primary" disabled={!acknowledgement || busy || (scan.capabilities.control && !selectedPatronId)} onClick={() => void circulation("CHECK_OUT")}><PackageCheck size={14} /> {scan.capabilities.control ? "Check out to borrower" : "Check out"}</button> : null}
            {canCheckIn ? <button type="button" className="dc-button dc-button--primary" disabled={busy} onClick={() => void circulation("CHECK_IN")}><Undo2 size={14} /> Check in</button> : null}
            {canRenew ? <button type="button" className="dc-button" disabled={busy} onClick={() => void circulation("RENEW")}><RefreshCcw size={14} /> Renew</button> : null}
            {canPlaceHold ? <button type="button" className="dc-button" disabled={busy} onClick={() => void placeHold(scan.item)}>Place hold</button> : null}
            {scan.capabilities.control ? <button type="button" className="dc-button" disabled={busy} onClick={() => void circulation("VERIFY_LOCATION")}>Verify location</button> : null}
          </div>
        </article> : <p className="library-ops__hint">USB/Bluetooth scanners work as keyboard input: focus the field and scan. Camera scanning is used where the browser supports it.</p>}
      </> : null}

      {mode === "inventory" && canControl ? <>
        <section className="library-stocktake">
          <header><div><PackageCheck size={17} /><span><strong>Physical inventory / shelf audit</strong><small>Scan the actual item at the actual location. Missing and misplaced holdings are reconciled when the session closes.</small></span></div></header>
          {!inventorySession || inventorySession.status !== "OPEN" ? <div className="library-stocktake__start">
            <label><span>Location / shelf</span><input value={inventoryLocation} onChange={(event) => setInventoryLocation(event.target.value)} placeholder="e.g. Technical Library / Shelf A3" /></label>
            <button type="button" className="dc-button dc-button--primary" disabled={busy || !inventoryLocation.trim()} onClick={() => void startInventorySession()}>Start inventory</button>
          </div> : <div className="library-stocktake__active">
            <div className="library-inventory-summary">
              <span><strong>{inventorySession.expected_count}</strong> expected</span>
              <span><strong>{inventorySession.observed_count}</strong> observed</span>
              <span><strong>{inventorySession.misplaced_count}</strong> misplaced</span>
              <span><strong>{inventorySession.missing_count}</strong> missing</span>
            </div>
            <form className="library-ops__search" onSubmit={(event) => { event.preventDefault(); void inventoryScan(); }}>
              <Barcode size={16} /><input value={inventoryScanCode} onChange={(event) => setInventoryScanCode(event.target.value)} placeholder="Scan barcode / QR" autoFocus /><button className="dc-button dc-button--primary" disabled={busy}>Record scan</button><button type="button" className="dc-button" onClick={() => setInventoryCameraOpen((value) => !value)}><Camera size={14} /> Camera</button>
            </form>
            {inventoryCameraOpen ? <CameraScanner onDetected={(value) => void inventoryScan(value)} onClose={() => setInventoryCameraOpen(false)} /> : null}
            {inventorySession.observations?.length ? <div className="library-stocktake__observations">{inventorySession.observations.slice(0, 8).map((row) => <div key={row.id}><span><strong>{row.title}</strong><small>{row.barcode}</small></span><em className={row.outcome === "MATCH" ? "ok" : "exception"}>{row.outcome.replaceAll("_", " ")}</em></div>)}</div> : null}
            <div className="library-scan-card__actions"><button type="button" className="dc-button dc-button--primary" disabled={busy} onClick={() => void closeInventory()}>Close & reconcile inventory</button></div>
          </div>}
        </section>
        <form className="library-ops__search" onSubmit={(event) => { event.preventDefault(); void loadInventory(); }}>
          <Search size={16} /><input value={inventoryQuery} onChange={(event) => setInventoryQuery(event.target.value)} placeholder="Barcode, call number, title, shelf or accession…" autoFocus /><button className="dc-button" disabled={busy}>Search inventory</button>
        </form>
        {inventory ? <div className="library-inventory-summary">
          <span><strong>{inventory.pagination.total}</strong> items in result</span>
          <span><strong>{inventory.summary.available}</strong> available</span>
          <span><strong>{inventory.summary.checked_out}</strong> checked out</span>
          <span><strong>{inventory.summary.overdue}</strong> overdue</span>
          <span><strong>{inventory.summary.exceptions}</strong> exceptions</span>
        </div> : null}
        <label className="library-inventory-reason"><span>Reason for loss, damage, repair, return-to-shelf or withdrawal</span><input value={inventoryReason} onChange={(event) => setInventoryReason(event.target.value)} placeholder="Required before a physical-control status change" /></label>
        <div className="library-inventory-list">
          {inventory?.items.map(({ item, holding }) => <article key={holding.id}>
            <div><small>{holding.barcode} · {holding.call_number || "No call number"}</small><strong>{item.title}</strong><span>{holding.status.replaceAll("_", " ")} · {holding.current_location}</span><span>{holding.due_at ? `Due ${formatDate(holding.due_at)}` : "No return due"}{holding.overdue ? " · OVERDUE" : ""}</span></div>
            <div className="library-inventory-list__actions">
              <button type="button" className="dc-button" onClick={() => { setScanCode(holding.barcode); void performScan(holding.barcode); }}>Open</button>
              <button type="button" className="dc-button" onClick={() => void downloadLibraryHoldingLabel(tenant, holding.id, `${item.catalogue_code}-${holding.barcode}.pdf`)}>Label</button>
              {holding.status !== "LOST" ? <button type="button" className="dc-button" disabled={busy} onClick={() => void controlHolding(holding.id, "MARK_LOST")}>Lost</button> : null}
              {holding.status === "AVAILABLE" ? <button type="button" className="dc-button" disabled={busy} onClick={() => void controlHolding(holding.id, "MARK_DAMAGED")}>Damaged</button> : null}
              {holding.status === "DAMAGED" ? <button type="button" className="dc-button" disabled={busy} onClick={() => void controlHolding(holding.id, "SEND_REPAIR")}>Repair</button> : null}
              {["LOST", "DAMAGED", "IN_REPAIR", "ON_HOLD"].includes(holding.status) ? <button type="button" className="dc-button" disabled={busy} onClick={() => void controlHolding(holding.id, "RETURN_TO_SHELF")}>Return to shelf</button> : null}
              {holding.status !== "WITHDRAWN" ? <button type="button" className="dc-button" disabled={busy} onClick={() => void controlHolding(holding.id, "WITHDRAW")}>Withdraw</button> : null}
            </div>
          </article>)}
          {inventory && !inventory.items.length ? <p>No physical holding matches this inventory search.</p> : null}
        </div>
      </> : null}

      {mode === "internet" ? <>
        <form className="library-ops__search" onSubmit={externalSearch}>
          <Globe2 size={16} /><input value={internetQuery} onChange={(event) => setInternetQuery(event.target.value)} placeholder="Search books by title, author, ISBN or subject" autoFocus /><button className="dc-button dc-button--primary" disabled={busy}>Search internet</button>
        </form>
        {internetPrivacy ? <p className="library-ops__privacy">{internetPrivacy}</p> : <p className="library-ops__privacy">External lookup runs only when you submit this search. Tenant document content is not sent.</p>}
        {Object.keys(internetLinks).length ? <div className="library-external-links">
          {Object.entries(internetLinks).map(([label, href]) => <a key={label} href={href} target="_blank" rel="noreferrer"><ExternalLink size={13} /> {label.replaceAll("_", " ")}</a>)}
        </div> : null}
        <div className="library-catalog-list">
          {internetResults.map((item) => <article key={`${item.provider}:${item.provider_id || item.title}`}>
            <div className="library-catalog-list__cover">{item.cover_url ? <img src={item.cover_url} alt="" loading="lazy" /> : <Globe2 size={24} />}</div>
            <div><small>{item.provider.replaceAll("_", " ")}</small><strong>{item.title}</strong><span>{displayAuthors(item)}</span><span>{item.publisher || "Publisher not listed"}{item.published_date ? ` · ${item.published_date}` : ""}</span><span>{Object.values(item.identifiers || {}).filter(Boolean).slice(0, 2).join(" · ") || "No ISBN supplied"}</span></div>
            <div className="library-catalog-list__actions">
              {canControl ? <button type="button" className="dc-button dc-button--primary" disabled={busy || Boolean(item.existing_catalog_item_id)} onClick={() => void importExternal(item)}><Plus size={14} /> {item.existing_catalog_item_id ? "Already catalogued" : "Add to tenant library"}</button> : null}
              {item.source_url ? <a href={item.source_url} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Open source</a> : null}
            </div>
          </article>)}
        </div>
      </> : null}

      {mode === "account" ? <>
        <div className="library-account-header"><div><BookOpenCheck size={18} /><span><strong>My library account</strong><small>Loans and reservations visible only to you and authorized library staff.</small></span></div><button type="button" className="dc-button" disabled={busy} onClick={() => void loadAccount()}><RefreshCcw size={14} /> Refresh</button></div>
        <section className="library-account-section"><h3>Checked out</h3>
          {account?.loans.map(({ item, holding }) => <article key={holding.id}><div><strong>{item.title}</strong><span>{displayAuthors(item)}</span><small>{holding.barcode} · due {formatDate(holding.due_at)}{holding.overdue ? " · OVERDUE" : ""}</small></div><div><button type="button" className="dc-button" disabled={busy} onClick={() => { setScanCode(holding.barcode); void performScan(holding.barcode); }}>Open item</button></div></article>)}
          {account && !account.loans.length ? <p>No items currently checked out.</p> : null}
        </section>
        <section className="library-account-section"><h3>Holds</h3>
          {account?.holds.map((hold) => <article key={hold.id}><div><strong>{hold.item.title}</strong><span>{hold.status.replaceAll("_", " ")}</span><small>{hold.pickup_location || "Pickup location not assigned"}</small></div><button type="button" className="dc-button" disabled={busy} onClick={() => void cancelHold(hold.id)}>Cancel hold</button></article>)}
          {account && !account.holds.length ? <p>No active holds.</p> : null}
        </section>
      </> : null}
    </div>
  </aside>;
}
