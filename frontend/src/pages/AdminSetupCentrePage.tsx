import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  CircleAlert,
  Download,
  FileCheck2,
  Mail,
  MapPin,
  Pencil,
  PlayCircle,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Upload,
  Users,
  X,
} from "lucide-react";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel } from "../components/UI/Admin";
import { getCachedUser, getContext } from "../services/auth";
import {
  listAdminAmos,
  listAdminAssets,
  listAdminDepartments,
  listAdminUsers,
  LS_ACTIVE_AMO_ID,
  setAdminContext,
  type AdminAmoRead,
  type AdminAssetRead,
  type AdminDepartmentRead,
  type AdminUserRead,
} from "../services/adminUsers";
import {
  downloadAmoAsset,
  getAmoAssets,
  uploadAmoLogo,
  uploadAmoTemplate,
  type AmoAssetRead,
  type TransferProgress,
} from "../services/amoAssets";
import {
  createBaseStation,
  getPersonnelIdentityHealth,
  listBaseStations,
  updateBaseStation,
} from "../services/foundations";
import type {
  BaseStationCreate,
  BaseStationRead,
  BaseStationType,
  PersonnelIdentityHealth,
} from "../types/foundations";
import { getWorkforceHrDashboard } from "../services/workforceHr";
import type { HrDashboard } from "../types/workforceHr";
import { saveDownloadedFile } from "../utils/downloads";

import "../styles/admin-setup-centre.css";

type UrlParams = { amoCode?: string };
type SetupSection = "readiness" | "bases" | "assets" | "next";
type AssetKind = "logo" | "template";
type LoadMode = "initial" | "refresh";

type BaseDraft = {
  code: string;
  name: string;
  icao_code: string;
  iata_code: string;
  base_type: BaseStationType;
  time_zone: string;
  description: string;
  aliases: string;
  is_active: boolean;
};

type BaseEditor = {
  id?: string;
  draft: BaseDraft;
};

type ReadinessStep = {
  key: string;
  title: string;
  detail: string;
  complete: boolean;
  countLabel: string;
  actionLabel: string;
  action: () => void;
};

const BASE_TYPES: BaseStationType[] = [
  "MAIN_BASE",
  "LINE_STATION",
  "OUTSTATION",
  "WORKSHOP",
  "HANGAR",
  "TRAINING_SITE",
  "OTHER",
];

const EMPTY_BASE: BaseDraft = {
  code: "",
  name: "",
  icao_code: "",
  iata_code: "",
  base_type: "MAIN_BASE",
  time_zone: "Africa/Nairobi",
  description: "",
  aliases: "",
  is_active: true,
};

function errorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === "string" && error.trim()) return error;
  if (error && typeof error === "object") {
    const detail = (error as { detail?: unknown; message?: unknown }).detail
      ?? (error as { message?: unknown }).message;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function setupStorageKey(amoId: string | null): string {
  return `amoportal:admin-setup-tour:${amoId || "unknown"}:v1`;
}

const AdminSetupCentrePage: React.FC = () => {
  const { amoCode = "system" } = useParams<UrlParams>();
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = useMemo(() => getCachedUser(), []);
  const ctx = getContext();
  const isSuperuser = Boolean(currentUser?.is_superuser);
  const isAmoAdmin = Boolean(currentUser?.is_amo_admin);
  const canAccessAdmin = isSuperuser || isAmoAdmin;

  const [activeAmoId, setActiveAmoId] = useState<string | null>(() => {
    const stored = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return stored?.trim() || null;
  });
  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const effectiveAmoId = useMemo(() => {
    if (isSuperuser) return activeAmoId || currentUser?.amo_id || null;
    return currentUser?.amo_id || null;
  }, [activeAmoId, currentUser?.amo_id, isSuperuser]);
  const selectedAmo = useMemo(
    () => amos.find((amo) => amo.id === effectiveAmoId) || null,
    [amos, effectiveAmoId],
  );

  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const activeFilter = searchParams.get("filter");
  const showInactiveAssets = activeFilter === "inactive";

  const [assets, setAssets] = useState<AmoAssetRead | null>(null);
  const [bases, setBases] = useState<BaseStationRead[]>([]);
  const [departments, setDepartments] = useState<AdminDepartmentRead[]>([]);
  const [users, setUsers] = useState<AdminUserRead[]>([]);
  const [workforce, setWorkforce] = useState<HrDashboard | null>(null);
  const [identityHealth, setIdentityHealth] = useState<PersonnelIdentityHealth | null>(null);
  const [inactiveAssets, setInactiveAssets] = useState<AdminAssetRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [baseEditor, setBaseEditor] = useState<BaseEditor | null>(null);
  const [savingBase, setSavingBase] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const [uploading, setUploading] = useState<AssetKind | null>(null);
  const [transferProgress, setTransferProgress] = useState<TransferProgress | null>(null);
  const [previewAsset, setPreviewAsset] = useState<{ kind: AssetKind; url: string; name: string } | null>(null);

  const loadRequestRef = useRef(0);
  const logoInputRef = useRef<HTMLInputElement | null>(null);
  const templateInputRef = useRef<HTMLInputElement | null>(null);
  const readinessRef = useRef<HTMLElement | null>(null);
  const basesRef = useRef<HTMLElement | null>(null);
  const assetsRef = useRef<HTMLElement | null>(null);
  const nextRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!currentUser || canAccessAdmin) return;
    if (amoCode && ctx.department) {
      navigate(`/maintenance/${amoCode}/${ctx.department}`, { replace: true });
      return;
    }
    navigate(amoCode ? `/maintenance/${amoCode}/login` : "/login", { replace: true });
  }, [amoCode, canAccessAdmin, ctx.department, currentUser, navigate]);

  const clearPreview = useCallback(() => {
    setPreviewAsset((previous) => {
      if (previous?.url) window.URL.revokeObjectURL(previous.url);
      return null;
    });
  }, []);

  const clearTenantState = useCallback(() => {
    setAssets(null);
    setBases([]);
    setDepartments([]);
    setUsers([]);
    setWorkforce(null);
    setIdentityHealth(null);
    setInactiveAssets([]);
    setBaseEditor(null);
    setNotice(null);
    clearPreview();
  }, [clearPreview]);

  useEffect(() => () => {
    loadRequestRef.current += 1;
    clearPreview();
  }, [clearPreview]);

  useEffect(() => {
    if (!isSuperuser) return;
    let cancelled = false;
    void listAdminAmos()
      .then((items) => {
        if (cancelled) return;
        setAmos(items);
        const selected = activeAmoId && items.some((item) => item.id === activeAmoId)
          ? activeAmoId
          : currentUser?.amo_id && items.some((item) => item.id === currentUser.amo_id)
            ? currentUser.amo_id
            : items[0]?.id || null;
        if (selected && selected !== activeAmoId) {
          localStorage.setItem(LS_ACTIVE_AMO_ID, selected);
          setActiveAmoId(selected);
        }
      })
      .catch((cause) => setError(errorText(cause, "Could not load AMO support contexts.")));
    return () => { cancelled = true; };
  }, [activeAmoId, currentUser?.amo_id, isSuperuser]);

  const syncContext = useCallback(async (amoId: string) => {
    if (!isSuperuser) return;
    const selected = amos.find((amo) => amo.id === amoId);
    if (!selected) throw new Error("The selected support AMO is no longer available.");
    await setAdminContext({
      active_amo_id: selected.id,
      data_mode: selected.is_demo ? "DEMO" : "REAL",
    });
  }, [amos, isSuperuser]);

  const loadSetup = useCallback(async (mode: LoadMode = "refresh") => {
    if (!currentUser || !canAccessAdmin || !effectiveAmoId) return;
    if (isSuperuser && !selectedAmo) return;

    const requestId = ++loadRequestRef.current;
    const requestedAmoId = effectiveAmoId;
    mode === "initial" ? setLoading(true) : setRefreshing(true);
    setError(null);

    try {
      await syncContext(requestedAmoId);
      if (requestId !== loadRequestRef.current || requestedAmoId !== effectiveAmoId) return;

      const results = await Promise.allSettled([
        getAmoAssets(isSuperuser ? requestedAmoId : null),
        listBaseStations({ include_inactive: true }),
        listAdminDepartments(isSuperuser ? requestedAmoId : undefined),
        listAdminUsers({ amo_id: isSuperuser ? requestedAmoId : undefined, limit: 500 }),
        getWorkforceHrDashboard(500),
        getPersonnelIdentityHealth(),
        showInactiveAssets
          ? listAdminAssets({ amo_id: requestedAmoId, only_active: false })
          : Promise.resolve<AdminAssetRead[]>([]),
      ] as const);

      if (requestId !== loadRequestRef.current || requestedAmoId !== effectiveAmoId) return;

      const [assetResult, baseResult, departmentResult, userResult, workforceResult, identityResult, inactiveResult] = results;
      const failures: string[] = [];

      if (assetResult.status === "fulfilled") setAssets(assetResult.value);
      else { setAssets(null); failures.push("branding assets"); }

      if (baseResult.status === "fulfilled") setBases(baseResult.value);
      else { setBases([]); failures.push("operating bases"); }

      if (departmentResult.status === "fulfilled") setDepartments(departmentResult.value);
      else { setDepartments([]); failures.push("departments"); }

      if (userResult.status === "fulfilled") setUsers(userResult.value);
      else { setUsers([]); failures.push("users"); }

      if (workforceResult.status === "fulfilled") setWorkforce(workforceResult.value);
      else { setWorkforce(null); failures.push("workforce readiness"); }

      if (identityResult.status === "fulfilled") setIdentityHealth(identityResult.value);
      else { setIdentityHealth(null); failures.push("personnel identity health"); }

      if (inactiveResult.status === "fulfilled") {
        setInactiveAssets(inactiveResult.value.filter((asset) => !asset.is_active));
      } else {
        setInactiveAssets([]);
        if (showInactiveAssets) failures.push("inactive assets");
      }

      if (failures.length) {
        setError(`Some setup data could not be loaded: ${failures.join(", ")}. Failed sections were cleared instead of showing another tenant's data.`);
      }
    } catch (cause) {
      if (requestId !== loadRequestRef.current) return;
      clearTenantState();
      setError(errorText(cause, "Could not load the AMO setup centre."));
    } finally {
      if (requestId === loadRequestRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [canAccessAdmin, clearTenantState, currentUser, effectiveAmoId, isSuperuser, selectedAmo, showInactiveAssets, syncContext]);

  useEffect(() => {
    if (!effectiveAmoId || (isSuperuser && !selectedAmo)) return;
    loadRequestRef.current += 1;
    clearTenantState();
    void loadSetup("initial");
    return () => { loadRequestRef.current += 1; };
  }, [clearTenantState, effectiveAmoId, isSuperuser, loadSetup, selectedAmo]);

  useEffect(() => {
    const requestedTour = searchParams.get("tour") === "1";
    const seen = localStorage.getItem(setupStorageKey(effectiveAmoId)) === "complete";
    if (requestedTour || !seen) setTourOpen(true);
  }, [effectiveAmoId, searchParams]);

  useEffect(() => {
    const section = (searchParams.get("section") || "") as SetupSection;
    const target = showInactiveAssets || section === "assets" ? assetsRef.current
      : section === "bases" ? basesRef.current
        : section === "next" ? nextRef.current
          : readinessRef.current;
    if (target) window.setTimeout(() => target.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }, [loading, searchParams, showInactiveAssets]);

  const activeBases = useMemo(() => bases.filter((base) => base.is_active), [bases]);
  const activeDepartments = useMemo(() => departments.filter((department) => department.is_active), [departments]);
  const activeUsers = useMemo(() => users.filter((user) => user.is_active !== false), [users]);
  const hasLogo = Boolean(assets?.crs_logo_filename);
  const hasTemplate = Boolean(assets?.crs_template_filename);
  const identityReady = Boolean(identityHealth)
    && identityHealth!.active_users_without_profile === 0
    && identityHealth!.active_profiles_without_user === 0
    && identityHealth!.issues.length === 0;

  const openSection = (section: SetupSection) => {
    const params = new URLSearchParams(location.search);
    params.set("section", section);
    params.delete("tour");
    navigate({ pathname: location.pathname, search: `?${params.toString()}` });
  };

  const clearInactiveFilter = () => {
    const params = new URLSearchParams(location.search);
    params.delete("filter");
    params.set("section", "assets");
    navigate({ pathname: location.pathname, search: `?${params.toString()}` }, { replace: true });
  };

  const readinessSteps: ReadinessStep[] = [
    {
      key: "bases",
      title: "Operating bases and stations",
      detail: "Create the main base, line stations, hangars, workshops and outstations used by contracts, rostering and maintenance.",
      complete: activeBases.length > 0,
      countLabel: activeBases.length ? `${activeBases.length} active` : "Required",
      actionLabel: activeBases.length ? "Manage bases" : "Create first base",
      action: () => openSection("bases"),
    },
    {
      key: "departments",
      title: "Departments and ownership",
      detail: "Define accountable operational departments before assigning users and permissions.",
      complete: activeDepartments.length > 0,
      countLabel: activeDepartments.length ? `${activeDepartments.length} active` : "Required",
      actionLabel: "Open users & departments",
      action: () => navigate(`/maintenance/${encodeURIComponent(amoCode)}/admin/users`),
    },
    {
      key: "users",
      title: "Users and personnel identities",
      detail: "Create staff accounts, link personnel records and confirm each person has one canonical portal identity.",
      complete: activeUsers.length > 0 && identityReady,
      countLabel: `${activeUsers.length} active user${activeUsers.length === 1 ? "" : "s"}`,
      actionLabel: "Manage users",
      action: () => navigate(`/maintenance/${encodeURIComponent(amoCode)}/admin/users`),
    },
    {
      key: "contracts",
      title: "Employment contracts and primary bases",
      detail: "Record effective-dated employment terms so staff become eligible for workforce and rostering workflows.",
      complete: Boolean(workforce) && workforce!.employees_without_contract_count === 0 && workforce!.employees_without_base_count === 0,
      countLabel: workforce ? `${workforce.employees_without_contract_count} missing contract` : "Check Workforce",
      actionLabel: "Open contracts",
      action: () => navigate(`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=workforce`),
    },
    {
      key: "patterns",
      title: "Work patterns",
      detail: "Assign effective work patterns or apply the controlled default-day baseline before roster planning.",
      complete: Boolean(workforce) && workforce!.employees_without_pattern_count === 0,
      countLabel: workforce ? `${workforce.employees_without_pattern_count} unassigned` : "Check Workforce",
      actionLabel: "Open work patterns",
      action: () => navigate(`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=workforce`),
    },
    {
      key: "assets",
      title: "CRS branding and release template",
      detail: "Upload the approved AMO logo and CRS PDF template used for controlled release output.",
      complete: hasLogo && hasTemplate,
      countLabel: `${Number(hasLogo) + Number(hasTemplate)}/2 uploaded`,
      actionLabel: "Manage assets",
      action: () => openSection("assets"),
    },
  ];

  const completedSteps = readinessSteps.filter((step) => step.complete).length;
  const completionPercent = Math.round((completedSteps / readinessSteps.length) * 100);

  const closeTour = () => {
    localStorage.setItem(setupStorageKey(effectiveAmoId), "complete");
    setTourOpen(false);
    const params = new URLSearchParams(location.search);
    params.delete("tour");
    navigate({ pathname: location.pathname, search: params.toString() ? `?${params.toString()}` : "" }, { replace: true });
  };

  const startBase = (base?: BaseStationRead) => {
    setNotice(null);
    setBaseEditor({
      id: base?.id,
      draft: base ? {
        code: base.code,
        name: base.name,
        icao_code: base.icao_code || "",
        iata_code: base.iata_code || "",
        base_type: base.base_type,
        time_zone: base.time_zone || "Africa/Nairobi",
        description: base.description || "",
        aliases: base.aliases.map((alias) => alias.alias).join(", "),
        is_active: base.is_active,
      } : { ...EMPTY_BASE },
    });
  };

  const saveBase = async () => {
    if (!baseEditor || !effectiveAmoId) return;
    const draft = baseEditor.draft;
    if (!draft.code.trim() || !draft.name.trim()) {
      setError("Base code and base name are required.");
      return;
    }
    const payload: BaseStationCreate = {
      code: draft.code.trim().toUpperCase(),
      name: draft.name.trim(),
      icao_code: draft.icao_code.trim().toUpperCase() || null,
      iata_code: draft.iata_code.trim().toUpperCase() || null,
      base_type: draft.base_type,
      time_zone: draft.time_zone.trim() || null,
      description: draft.description.trim() || null,
      aliases: draft.aliases.split(",").map((alias) => alias.trim()).filter(Boolean),
      is_active: draft.is_active,
    };
    setSavingBase(true);
    setError(null);
    try {
      await syncContext(effectiveAmoId);
      if (baseEditor.id) await updateBaseStation(baseEditor.id, payload);
      else await createBaseStation(payload);
      setNotice(baseEditor.id ? "Base station updated." : "Base station created. Contracts can now use it as a primary base.");
      setBaseEditor(null);
      await loadSetup("refresh");
    } catch (cause) {
      setError(errorText(cause, "Could not save the base station."));
    } finally {
      setSavingBase(false);
    }
  };

  const toggleBase = async (base: BaseStationRead) => {
    if (!effectiveAmoId) return;
    const nextActive = !base.is_active;
    if (!window.confirm(`${nextActive ? "Reactivate" : "Deactivate"} ${base.code} · ${base.name}?`)) return;
    setError(null);
    try {
      await syncContext(effectiveAmoId);
      await updateBaseStation(base.id, { is_active: nextActive });
      setNotice(`${base.code} ${nextActive ? "reactivated" : "deactivated"}.`);
      await loadSetup("refresh");
    } catch (cause) {
      setError(errorText(cause, "Could not update the base station."));
    }
  };

  const handleUpload = async (kind: AssetKind, files?: FileList | null) => {
    const file = files?.[0];
    if (!file || !effectiveAmoId) return;
    setUploading(kind);
    setTransferProgress(null);
    setError(null);
    try {
      await syncContext(effectiveAmoId);
      const updated = kind === "logo"
        ? await uploadAmoLogo(file, isSuperuser ? effectiveAmoId : null, setTransferProgress)
        : await uploadAmoTemplate(file, isSuperuser ? effectiveAmoId : null, setTransferProgress);
      setAssets(updated);
      setNotice(`${kind === "logo" ? "Logo" : "CRS template"} uploaded successfully.`);
    } catch (cause) {
      setError(errorText(cause, `Could not upload the ${kind}.`));
    } finally {
      setUploading(null);
      setTransferProgress(null);
      if (logoInputRef.current) logoInputRef.current.value = "";
      if (templateInputRef.current) templateInputRef.current.value = "";
    }
  };

  const downloadOrPreview = async (kind: AssetKind, preview: boolean) => {
    if (!effectiveAmoId) return;
    setError(null);
    try {
      await syncContext(effectiveAmoId);
      const downloaded = await downloadAmoAsset(kind, isSuperuser ? effectiveAmoId : null, setTransferProgress);
      if (!preview) {
        saveDownloadedFile(downloaded);
        return;
      }
      const url = window.URL.createObjectURL(downloaded.blob);
      setPreviewAsset((previous) => {
        if (previous?.url) window.URL.revokeObjectURL(previous.url);
        return {
          kind,
          url,
          name: kind === "logo" ? assets?.crs_logo_filename || "amo-logo" : assets?.crs_template_filename || "crs-template.pdf",
        };
      });
    } catch (cause) {
      setError(errorText(cause, `Could not ${preview ? "preview" : "download"} the ${kind}.`));
    } finally {
      setTransferProgress(null);
    }
  };

  const selectSupportAmo = (amoId: string) => {
    if (!amoId || amoId === effectiveAmoId) return;
    loadRequestRef.current += 1;
    clearTenantState();
    setLoading(true);
    setError(null);
    localStorage.setItem(LS_ACTIVE_AMO_ID, amoId);
    setActiveAmoId(amoId);
  };

  if (currentUser && !canAccessAdmin) return null;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="admin-assets">
      <div className="admin-page admin-amo-assets setup-centre">
        <PageHeader
          title="AMO Setup Centre"
          subtitle="Complete the operating structure, people, Workforce readiness and controlled release assets required before daily portal use."
        />

        <div className="setup-centre__toolbar">
          <div className="setup-centre__progress" aria-label={`${completionPercent}% setup complete`}>
            <div><strong>{completionPercent}%</strong><span>{completedSteps} of {readinessSteps.length} core setup steps complete</span></div>
            <progress value={completionPercent} max={100} />
          </div>
          <div className="setup-centre__toolbar-actions">
            <Button type="button" variant="secondary" onClick={() => setTourOpen(true)}><PlayCircle size={16} /> Guided setup</Button>
            <Button type="button" variant="secondary" disabled={refreshing || loading} onClick={() => void loadSetup("refresh")}><RefreshCw size={16} className={refreshing ? "is-spinning" : ""} /> Refresh</Button>
          </div>
        </div>

        {isSuperuser && amos.length > 0 ? (
          <div className="setup-centre__support-context">
            <ShieldCheck size={17} />
            <label htmlFor="setupAmoContext">Support AMO</label>
            <select id="setupAmoContext" value={effectiveAmoId || ""} onChange={(event) => selectSupportAmo(event.target.value)}>
              {amos.map((amo) => (
                <option key={amo.id} value={amo.id}>{amo.amo_code} — {amo.name}{amo.is_demo ? " [DEMO]" : " [REAL]"}</option>
              ))}
            </select>
          </div>
        ) : null}

        {error ? <InlineAlert tone="danger" title="Setup action needs attention"><span>{error}</span></InlineAlert> : null}
        {notice ? <InlineAlert tone="success" title="Saved"><span>{notice}</span></InlineAlert> : null}

        <nav className="setup-centre__section-nav" aria-label="AMO setup sections">
          <button type="button" onClick={() => openSection("readiness")}>Readiness</button>
          <button type="button" onClick={() => openSection("bases")}>Bases & stations</button>
          <button type="button" onClick={() => openSection("assets")}>CRS assets</button>
          <button type="button" onClick={() => openSection("next")}>Module setup</button>
        </nav>

        <section ref={readinessRef} className="setup-centre__section" id="setup-readiness">
          <div className="setup-centre__section-heading">
            <div><span>Live readiness</span><h2>What must be configured</h2><p>Every status below is calculated from the selected AMO. Failed sources are cleared and never replaced with another tenant's records.</p></div>
          </div>
          {loading ? <div className="setup-centre__loading">Loading AMO setup data…</div> : (
            <div className="setup-centre__checklist">
              {readinessSteps.map((step, index) => (
                <article key={step.key} className={step.complete ? "is-complete" : "is-required"}>
                  <div className="setup-centre__step-number">{step.complete ? <CheckCircle2 size={19} /> : index + 1}</div>
                  <div><strong>{step.title}</strong><p>{step.detail}</p></div>
                  <span className="setup-centre__status">{step.countLabel}</span>
                  <button type="button" onClick={step.action}>{step.actionLabel}<ArrowRight size={15} /></button>
                </article>
              ))}
            </div>
          )}
        </section>

        <section ref={basesRef} className="setup-centre__section" id="setup-bases">
          <div className="setup-centre__section-heading">
            <div><span>Operating structure</span><h2>Bases, stations and facilities</h2><p>These canonical records feed Workforce contracts, user assignments, rostering, planning and maintenance execution.</p></div>
            <button type="button" className="setup-centre__primary-action" onClick={() => startBase()}><Plus size={16} /> Add base or station</button>
          </div>
          <div className="setup-centre__base-grid">
            {bases.map((base) => (
              <article key={base.id} className={base.is_active ? "" : "is-inactive"}>
                <div className="setup-centre__base-icon"><MapPin size={19} /></div>
                <div className="setup-centre__base-copy">
                  <div><strong>{base.code} · {base.name}</strong><span>{base.is_active ? "Active" : "Inactive"}</span></div>
                  <p>{base.base_type.replaceAll("_", " ")} · {base.icao_code || base.iata_code || "No airport code"} · {base.time_zone || "No time zone"}</p>
                  {base.description ? <small>{base.description}</small> : null}
                </div>
                <div className="setup-centre__row-actions">
                  <button type="button" onClick={() => startBase(base)}><Pencil size={15} /> Edit</button>
                  <button type="button" onClick={() => void toggleBase(base)}>{base.is_active ? "Deactivate" : "Reactivate"}</button>
                </div>
              </article>
            ))}
            {!loading && !bases.length ? (
              <div className="setup-centre__empty"><MapPin size={28} /><strong>No operating base exists</strong><p>Create the main base first. Employment contracts cannot be completed without a canonical primary base.</p><button type="button" onClick={() => startBase()}><Plus size={16} /> Create main base</button></div>
            ) : null}
          </div>
        </section>

        <section ref={assetsRef} className="setup-centre__section" id="setup-assets">
          <div className="setup-centre__section-heading">
            <div><span>Controlled release output</span><h2>CRS branding and template</h2><p>Upload the approved logo and PDF template used by the certificate-of-release workflow.</p></div>
          </div>
          <div className="setup-centre__asset-grid">
            <Panel title="AMO logo" subtitle={hasLogo ? assets?.crs_logo_filename || "Uploaded" : "Required for branded output"}>
              <div className="setup-centre__asset-state">{hasLogo ? <BadgeCheck size={22} /> : <CircleAlert size={22} />}<strong>{hasLogo ? "Ready" : "Missing"}</strong></div>
              <input ref={logoInputRef} hidden type="file" accept=".png,.jpg,.jpeg,.svg" onChange={(event) => void handleUpload("logo", event.target.files)} />
              <div className="setup-centre__asset-actions">
                <Button type="button" onClick={() => logoInputRef.current?.click()} disabled={uploading === "logo"}><Upload size={15} /> {hasLogo ? "Replace logo" : "Upload logo"}</Button>
                <Button type="button" variant="secondary" disabled={!hasLogo} onClick={() => void downloadOrPreview("logo", true)}>Preview</Button>
                <Button type="button" variant="secondary" disabled={!hasLogo} onClick={() => void downloadOrPreview("logo", false)}><Download size={15} /> Download</Button>
              </div>
            </Panel>
            <Panel title="CRS PDF template" subtitle={hasTemplate ? assets?.crs_template_filename || "Uploaded" : "Required for release output"}>
              <div className="setup-centre__asset-state">{hasTemplate ? <FileCheck2 size={22} /> : <CircleAlert size={22} />}<strong>{hasTemplate ? "Ready" : "Missing"}</strong></div>
              <input ref={templateInputRef} hidden type="file" accept="application/pdf" onChange={(event) => void handleUpload("template", event.target.files)} />
              <div className="setup-centre__asset-actions">
                <Button type="button" onClick={() => templateInputRef.current?.click()} disabled={uploading === "template"}><Upload size={15} /> {hasTemplate ? "Replace template" : "Upload template"}</Button>
                <Button type="button" variant="secondary" disabled={!hasTemplate} onClick={() => void downloadOrPreview("template", true)}>Preview</Button>
                <Button type="button" variant="secondary" disabled={!hasTemplate} onClick={() => void downloadOrPreview("template", false)}><Download size={15} /> Download</Button>
              </div>
            </Panel>
          </div>

          {showInactiveAssets ? (
            <Panel
              title="Inactive assets"
              subtitle="Records reported by the Admin Overview for the selected AMO."
              actions={<Button type="button" size="sm" variant="secondary" onClick={clearInactiveFilter}>Clear filter</Button>}
            >
              {loading ? <p className="admin-muted">Loading inactive assets…</p> : inactiveAssets.length ? (
                <ul className="admin-list">
                  {inactiveAssets.map((asset) => (
                    <li key={asset.id}>
                      <div className="admin-list__row admin-overview__activity-row">
                        <div><strong>{asset.name || asset.kind}</strong><div className="admin-muted">{asset.original_filename || "Unnamed asset"}</div></div>
                        <span className="admin-muted">{asset.updated_at ? new Date(asset.updated_at).toLocaleString() : "—"}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <p className="admin-muted">No inactive assets found.</p>}
            </Panel>
          ) : null}

          {transferProgress ? <div className="setup-centre__transfer"><progress value={transferProgress.percent ?? undefined} max={100} /><span>{transferProgress.percent == null ? "Transferring…" : `${Math.round(transferProgress.percent)}%`}</span></div> : null}
          {previewAsset ? (
            <div className="setup-centre__preview">
              <div><strong>{previewAsset.name}</strong><button type="button" aria-label="Close preview" onClick={clearPreview}><X size={17} /></button></div>
              {previewAsset.kind === "logo" ? <img src={previewAsset.url} alt="AMO logo preview" /> : <iframe src={previewAsset.url} title="CRS template preview" />}
            </div>
          ) : null}
        </section>

        <section ref={nextRef} className="setup-centre__section" id="setup-next">
          <div className="setup-centre__section-heading">
            <div><span>Continue configuration</span><h2>Module-specific setup pages</h2><p>Use these admin-only destinations after the core operating structure is ready.</p></div>
          </div>
          <div className="setup-centre__module-grid">
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/users`}><Users size={21} /><div><strong>Users & departments</strong><span>Create staff, assign roles and manage departments.</span></div><ArrowRight size={17} /></Link>
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=workforce`}><BriefcaseBusiness size={21} /><div><strong>Workforce & contracts</strong><span>Create contracts, assign primary bases and work patterns.</span></div><ArrowRight size={17} /></Link>
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/document-control/settings`}><BookOpenCheck size={21} /><div><strong>Document Control</strong><span>Configure controlled-document ownership, workflows and registers.</span></div><ArrowRight size={17} /></Link>
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/email-settings`}><Mail size={21} /><div><strong>Email delivery</strong><span>Review tenant notification delivery and sender readiness.</span></div><ArrowRight size={17} /></Link>
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/billing`}><Building2 size={21} /><div><strong>Subscription & modules</strong><span>Review the active plan and enabled portal modules.</span></div><ArrowRight size={17} /></Link>
            <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/overview`}><ShieldCheck size={21} /><div><strong>Admin overview</strong><span>Return to tenant administration and live operational status.</span></div><ArrowRight size={17} /></Link>
          </div>
        </section>
      </div>

      {baseEditor ? (
        <div className="setup-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setBaseEditor(null); }}>
          <section className="setup-dialog" role="dialog" aria-modal="true" aria-labelledby="baseEditorTitle">
            <div className="setup-dialog__header"><div><span>Canonical operating structure</span><h2 id="baseEditorTitle">{baseEditor.id ? "Edit base or station" : "Add base or station"}</h2></div><button type="button" aria-label="Close base editor" onClick={() => setBaseEditor(null)}><X size={18} /></button></div>
            <div className="setup-dialog__grid">
              <label><span>Base code *</span><input value={baseEditor.draft.code} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, code: event.target.value } })} placeholder="NBO-HQ" /></label>
              <label><span>Name *</span><input value={baseEditor.draft.name} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, name: event.target.value } })} placeholder="Nairobi Main Base" /></label>
              <label><span>Facility type</span><select value={baseEditor.draft.base_type} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, base_type: event.target.value as BaseStationType } })}>{BASE_TYPES.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></label>
              <label><span>Time zone</span><input value={baseEditor.draft.time_zone} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, time_zone: event.target.value } })} placeholder="Africa/Nairobi" /></label>
              <label><span>ICAO code</span><input value={baseEditor.draft.icao_code} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, icao_code: event.target.value } })} maxLength={4} placeholder="HKJK" /></label>
              <label><span>IATA code</span><input value={baseEditor.draft.iata_code} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, iata_code: event.target.value } })} maxLength={3} placeholder="NBO" /></label>
              <label className="is-wide"><span>Aliases</span><input value={baseEditor.draft.aliases} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, aliases: event.target.value } })} placeholder="HQ, Nairobi Hangar (comma separated)" /></label>
              <label className="is-wide"><span>Description</span><textarea rows={3} value={baseEditor.draft.description} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, description: event.target.value } })} placeholder="Scope, location notes or operating limitations" /></label>
              <label className="setup-dialog__check"><input type="checkbox" checked={baseEditor.draft.is_active} onChange={(event) => setBaseEditor({ ...baseEditor, draft: { ...baseEditor.draft, is_active: event.target.checked } })} /><span>Active and available to portal modules</span></label>
            </div>
            <div className="setup-dialog__actions"><Button type="button" variant="secondary" onClick={() => setBaseEditor(null)}>Cancel</Button><Button type="button" disabled={savingBase} onClick={() => void saveBase()}><Save size={16} /> {savingBase ? "Saving…" : baseEditor.id ? "Save changes" : "Create base"}</Button></div>
          </section>
        </div>
      ) : null}

      {tourOpen ? (
        <div className="setup-dialog-backdrop setup-tour-backdrop" role="presentation">
          <section className="setup-dialog setup-tour" role="dialog" aria-modal="true" aria-labelledby="setupTourTitle">
            <div className="setup-dialog__header"><div><span>Administrator guide</span><h2 id="setupTourTitle">Set up the AMO in the correct order</h2></div><button type="button" aria-label="Close setup guide" onClick={closeTour}><X size={18} /></button></div>
            <p className="setup-tour__intro">Start with shared records once. Workforce, rostering, planning and maintenance then consume the same bases, people and controlled assets.</p>
            <ol className="setup-tour__steps">
              <li><MapPin size={18} /><div><strong>Create the operating structure</strong><span>Add the main base and every station, hangar or workshop that users and contracts may reference.</span></div></li>
              <li><Users size={18} /><div><strong>Add departments and users</strong><span>Create accountable departments, staff accounts and personnel identities.</span></div></li>
              <li><BriefcaseBusiness size={18} /><div><strong>Complete Workforce records</strong><span>Create each employment contract, select the canonical primary base and assign a work pattern.</span></div></li>
              <li><FileCheck2 size={18} /><div><strong>Upload controlled release assets</strong><span>Add the approved logo and CRS PDF template used by the release workflow.</span></div></li>
              <li><BookOpenCheck size={18} /><div><strong>Configure enabled modules</strong><span>Finish Document Control, notifications, quality and maintenance settings from their dedicated setup pages.</span></div></li>
            </ol>
            <div className="setup-dialog__actions"><Button type="button" variant="secondary" onClick={closeTour}>Close guide</Button><Button type="button" onClick={() => { closeTour(); openSection(readinessSteps.find((step) => !step.complete)?.key === "bases" ? "bases" : "readiness"); }}><PlayCircle size={16} /> Start setup</Button></div>
          </section>
        </div>
      ) : null}
    </DepartmentLayout>
  );
};

export default AdminSetupCentrePage;
