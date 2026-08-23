import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  BriefcaseBusiness,
  Building2,
  Check,
  CircleAlert,
  Download,
  FileCheck2,
  Mail,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  Upload,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button } from "../components/UI/Admin";
import BaseStationEditorDialog, {
  type BaseDraft,
  type BaseEditorState,
} from "./adminSetup/BaseStationEditorDialog";
import DepartmentManager from "./adminSetup/DepartmentManager";
import { getCachedUser, getContext } from "../services/auth";
import {
  listAdminAmos,
  listAdminUsers,
  LS_ACTIVE_AMO_ID,
  setAdminContext,
  type AdminAmoRead,
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
import {
  listSetupDepartments,
  type SetupDepartmentRead,
} from "../services/setupDepartments";
import type {
  BaseStationCreate,
  BaseStationRead,
  PersonnelIdentityHealth,
} from "../types/foundations";
import { getWorkforceHrDashboard } from "../services/workforceHr";
import type { HrDashboard } from "../types/workforceHr";
import { saveDownloadedFile } from "../utils/downloads";

import "../styles/admin-setup-resend.css";

type UrlParams = { amoCode?: string };
type StepKey = "bases" | "departments" | "users" | "workforce" | "assets" | "modules";
type AssetKind = "logo" | "template";
type ToastTone = "danger" | "success" | "info";

type SetupStep = {
  key: StepKey;
  title: string;
  description: string;
  summary: string;
  complete: boolean;
  icon: LucideIcon;
};

const STEP_KEYS: StepKey[] = ["bases", "departments", "users", "workforce", "assets", "modules"];

const EMPTY_BASE: BaseDraft = {
  code: "",
  name: "",
  icao_code: "",
  iata_code: "",
  base_type: "MAIN_BASE",
  time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Africa/Nairobi",
  description: "",
  aliases: "",
  latitude: "",
  longitude: "",
  coordinate_accuracy_m: "",
  location_source: "",
  airport_reference_ident: "",
  geofence_radius_m: "250",
  checkin_prompt_enabled: false,
  checkout_reminder_enabled: false,
  suspicious_location_review_enabled: false,
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

function optionalNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function activeStepFromSearch(search: string): StepKey | null {
  const requested = new URLSearchParams(search).get("section");
  return STEP_KEYS.includes(requested as StepKey) ? requested as StepKey : null;
}

const SetupToast: React.FC<{
  tone: ToastTone;
  title: string;
  message: string;
  onClose: () => void;
}> = ({ tone, title, message, onClose }) => (
  <div
    className={`setup-resend__toast setup-resend__toast--${tone}`}
    role={tone === "danger" ? "alert" : "status"}
    aria-live={tone === "danger" ? "assertive" : "polite"}
    aria-atomic="true"
  >
    <div>
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
    <button type="button" aria-label="Dismiss notification" onClick={onClose}>
      <X size={15} />
    </button>
  </div>
);

const AdminSetupCentreResendPage: React.FC = () => {
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

  const [assets, setAssets] = useState<AmoAssetRead | null>(null);
  const [bases, setBases] = useState<BaseStationRead[]>([]);
  const [departments, setDepartments] = useState<SetupDepartmentRead[]>([]);
  const [users, setUsers] = useState<AdminUserRead[]>([]);
  const [workforce, setWorkforce] = useState<HrDashboard | null>(null);
  const [identityHealth, setIdentityHealth] = useState<PersonnelIdentityHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [baseEditor, setBaseEditor] = useState<BaseEditorState | null>(null);
  const [savingBase, setSavingBase] = useState(false);
  const [uploading, setUploading] = useState<AssetKind | null>(null);
  const [transferProgress, setTransferProgress] = useState<TransferProgress | null>(null);
  const [previewAsset, setPreviewAsset] = useState<{ kind: AssetKind; url: string; name: string } | null>(null);
  const [toast, setToast] = useState<{ tone: ToastTone; title: string; message: string } | null>(null);

  const requestRef = useRef(0);
  const logoInputRef = useRef<HTMLInputElement | null>(null);
  const templateInputRef = useRef<HTMLInputElement | null>(null);

  const clearPreview = useCallback(() => {
    setPreviewAsset((previous) => {
      if (previous?.url) window.URL.revokeObjectURL(previous.url);
      return null;
    });
  }, []);

  useEffect(() => () => {
    requestRef.current += 1;
    clearPreview();
  }, [clearPreview]);

  useEffect(() => {
    if (!currentUser || canAccessAdmin) return;
    if (amoCode && ctx.department) {
      navigate(`/maintenance/${amoCode}/${ctx.department}`, { replace: true });
      return;
    }
    navigate(amoCode ? `/maintenance/${amoCode}/login` : "/login", { replace: true });
  }, [amoCode, canAccessAdmin, ctx.department, currentUser, navigate]);

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
      .catch((cause) => setToast({
        tone: "danger",
        title: "AMO contexts unavailable",
        message: errorText(cause, "Could not load AMO support contexts."),
      }));
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

  const loadSetup = useCallback(async (initial = false) => {
    if (!currentUser || !canAccessAdmin || !effectiveAmoId) return;
    if (isSuperuser && !selectedAmo) return;

    const requestId = ++requestRef.current;
    if (initial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }

    try {
      await syncContext(effectiveAmoId);
      const results = await Promise.allSettled([
        getAmoAssets(isSuperuser ? effectiveAmoId : null),
        listBaseStations({ include_inactive: true }),
        listSetupDepartments(true),
        listAdminUsers({ amo_id: isSuperuser ? effectiveAmoId : undefined, limit: 500 }),
        getWorkforceHrDashboard(500),
        getPersonnelIdentityHealth(),
      ] as const);

      if (requestId !== requestRef.current) return;
      const [assetResult, baseResult, departmentResult, userResult, workforceResult, identityResult] = results;
      const failures: string[] = [];

      if (assetResult.status === "fulfilled") setAssets(assetResult.value);
      else { setAssets(null); failures.push("CRS assets"); }
      if (baseResult.status === "fulfilled") setBases(baseResult.value);
      else { setBases([]); failures.push("bases"); }
      if (departmentResult.status === "fulfilled") setDepartments(departmentResult.value);
      else { setDepartments([]); failures.push("departments"); }
      if (userResult.status === "fulfilled") setUsers(userResult.value);
      else { setUsers([]); failures.push("users"); }
      if (workforceResult.status === "fulfilled") setWorkforce(workforceResult.value);
      else { setWorkforce(null); failures.push("workforce"); }
      if (identityResult.status === "fulfilled") setIdentityHealth(identityResult.value);
      else { setIdentityHealth(null); failures.push("identity health"); }

      if (failures.length) {
        setToast({
          tone: "danger",
          title: "Some setup data did not load",
          message: `${failures.join(", ")}. Those sections were cleared rather than showing stale tenant data.`,
        });
      }
    } catch (cause) {
      if (requestId !== requestRef.current) return;
      setAssets(null);
      setBases([]);
      setDepartments([]);
      setUsers([]);
      setWorkforce(null);
      setIdentityHealth(null);
      setToast({
        tone: "danger",
        title: "Setup centre unavailable",
        message: errorText(cause, "Could not load the AMO setup centre."),
      });
    } finally {
      if (requestId === requestRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [canAccessAdmin, currentUser, effectiveAmoId, isSuperuser, selectedAmo, syncContext]);

  useEffect(() => {
    if (!effectiveAmoId || (isSuperuser && !selectedAmo)) return;
    void loadSetup(true);
    return () => { requestRef.current += 1; };
  }, [effectiveAmoId, isSuperuser, loadSetup, selectedAmo]);

  const activeBases = useMemo(() => bases.filter((base) => base.is_active), [bases]);
  const locatedBases = useMemo(
    () => activeBases.filter((base) => base.latitude != null && base.longitude != null),
    [activeBases],
  );
  const activeDepartments = useMemo(
    () => departments.filter((department) => department.is_active),
    [departments],
  );
  const activeUsers = useMemo(() => users.filter((user) => user.is_active !== false), [users]);
  const identityReady = Boolean(identityHealth)
    && identityHealth!.active_users_without_profile === 0
    && identityHealth!.active_profiles_without_user === 0
    && identityHealth!.issues.length === 0;
  const workforceReady = Boolean(workforce)
    && workforce!.employees_without_contract_count === 0
    && workforce!.employees_without_base_count === 0
    && workforce!.employees_without_pattern_count === 0;
  const hasLogo = Boolean(assets?.crs_logo_filename);
  const hasTemplate = Boolean(assets?.crs_template_filename);

  const steps: SetupStep[] = useMemo(() => [
    {
      key: "bases",
      title: "Operating bases",
      description: "Create approved bases, stations, hangars and workshops. Confirm coordinates before enabling proximity policies.",
      summary: activeBases.length
        ? `${activeBases.length} active · ${locatedBases.length} located`
        : "Required before employment contracts",
      complete: activeBases.length > 0,
      icon: MapPin,
    },
    {
      key: "departments",
      title: "Departments",
      description: "Create the real AMO departments and ownership structure consumed across the portal.",
      summary: activeDepartments.length ? `${activeDepartments.length} active` : "No active department",
      complete: activeDepartments.length > 0,
      icon: Building2,
    },
    {
      key: "users",
      title: "Users and identities",
      description: "Create staff accounts, assign departments and resolve duplicate or missing personnel identities.",
      summary: `${activeUsers.length} active user${activeUsers.length === 1 ? "" : "s"}`,
      complete: activeUsers.length > 0 && identityReady,
      icon: Users,
    },
    {
      key: "workforce",
      title: "Contracts and work patterns",
      description: "Complete effective employment terms, primary bases and work patterns for roster eligibility.",
      summary: workforce
        ? `${workforce.employees_without_contract_count} contracts · ${workforce.employees_without_pattern_count} patterns missing`
        : "Workforce status unavailable",
      complete: workforceReady,
      icon: BriefcaseBusiness,
    },
    {
      key: "assets",
      title: "CRS release assets",
      description: "Upload the approved AMO logo and controlled PDF template used for release output.",
      summary: `${Number(hasLogo) + Number(hasTemplate)}/2 uploaded`,
      complete: hasLogo && hasTemplate,
      icon: FileCheck2,
    },
    {
      key: "modules",
      title: "Module setup",
      description: "Continue into the dedicated settings owned by Document Control, notifications, billing and operations.",
      summary: "Configuration continues by module",
      complete: false,
      icon: ShieldCheck,
    },
  ], [
    activeBases.length,
    activeDepartments.length,
    activeUsers.length,
    hasLogo,
    hasTemplate,
    identityReady,
    locatedBases.length,
    workforce,
    workforceReady,
  ]);

  const requestedStep = activeStepFromSearch(location.search);
  const firstIncomplete = steps.find((step) => !step.complete)?.key || "modules";
  const activeStep = requestedStep || firstIncomplete;
  const activeStepData = steps.find((step) => step.key === activeStep) || steps[0];
  const completedCount = steps.filter((step) => step.complete).length;
  const completionPercent = Math.round((completedCount / (steps.length - 1)) * 100);

  const selectStep = (step: StepKey) => {
    const params = new URLSearchParams(location.search);
    params.set("section", step);
    navigate({ pathname: location.pathname, search: `?${params.toString()}` }, { replace: true });
  };

  const selectSupportAmo = (amoId: string) => {
    if (!amoId || amoId === effectiveAmoId) return;
    requestRef.current += 1;
    setAssets(null);
    setBases([]);
    setDepartments([]);
    setUsers([]);
    setWorkforce(null);
    setIdentityHealth(null);
    setLoading(true);
    localStorage.setItem(LS_ACTIVE_AMO_ID, amoId);
    setActiveAmoId(amoId);
  };

  const startBase = (base?: BaseStationRead) => {
    setToast(null);
    setBaseEditor({
      id: base?.id,
      draft: base ? {
        code: base.code,
        name: base.name,
        icao_code: base.icao_code || "",
        iata_code: base.iata_code || "",
        base_type: base.base_type,
        time_zone: base.time_zone || EMPTY_BASE.time_zone,
        description: base.description || "",
        aliases: base.aliases.map((alias) => alias.alias).join(", "),
        latitude: base.latitude == null ? "" : String(base.latitude),
        longitude: base.longitude == null ? "" : String(base.longitude),
        coordinate_accuracy_m: base.coordinate_accuracy_m == null ? "" : String(base.coordinate_accuracy_m),
        location_source: base.location_source || "",
        airport_reference_ident: base.airport_reference_ident || "",
        geofence_radius_m: String(base.geofence_radius_m || 250),
        checkin_prompt_enabled: base.checkin_prompt_enabled,
        checkout_reminder_enabled: base.checkout_reminder_enabled,
        suspicious_location_review_enabled: base.suspicious_location_review_enabled,
        is_active: base.is_active,
      } : { ...EMPTY_BASE },
    });
  };

  const saveBase = async () => {
    if (!baseEditor || !effectiveAmoId) return;
    const draft = baseEditor.draft;
    if (!draft.code.trim() || !draft.name.trim()) {
      setToast({
        tone: "danger",
        title: "Complete the required fields",
        message: "Base code and base name are required.",
      });
      return;
    }

    const latitude = optionalNumber(draft.latitude);
    const longitude = optionalNumber(draft.longitude);
    if ((latitude == null) !== (longitude == null)) {
      setToast({
        tone: "danger",
        title: "Coordinates are incomplete",
        message: "Latitude and longitude must both be present or both be empty.",
      });
      return;
    }

    const hasCoordinates = latitude != null && longitude != null;
    const payload: BaseStationCreate = {
      code: draft.code.trim().toUpperCase(),
      name: draft.name.trim(),
      icao_code: draft.icao_code.trim().toUpperCase() || null,
      iata_code: draft.iata_code.trim().toUpperCase() || null,
      base_type: draft.base_type,
      time_zone: draft.time_zone.trim() || null,
      description: draft.description.trim() || null,
      aliases: draft.aliases.split(",").map((alias) => alias.trim()).filter(Boolean),
      latitude,
      longitude,
      coordinate_accuracy_m: hasCoordinates ? optionalNumber(draft.coordinate_accuracy_m) : null,
      location_source: hasCoordinates ? draft.location_source || "MANUAL" : null,
      airport_reference_ident: hasCoordinates
        ? draft.airport_reference_ident.trim().toUpperCase() || null
        : null,
      geofence_radius_m: Math.max(50, Math.min(5000, Number(draft.geofence_radius_m || 250))),
      checkin_prompt_enabled: hasCoordinates && draft.checkin_prompt_enabled,
      checkout_reminder_enabled: hasCoordinates && draft.checkout_reminder_enabled,
      suspicious_location_review_enabled: hasCoordinates && draft.suspicious_location_review_enabled,
      is_active: draft.is_active,
    };

    setSavingBase(true);
    setToast(null);
    try {
      await syncContext(effectiveAmoId);
      if (baseEditor.id) await updateBaseStation(baseEditor.id, payload);
      else await createBaseStation(payload);
      setBaseEditor(null);
      setToast({
        tone: "success",
        title: baseEditor.id ? "Base updated" : "Base created",
        message: baseEditor.id
          ? `${payload.code} was updated successfully.`
          : `${payload.code} can now be assigned to contracts and personnel.`,
      });
      await loadSetup(false);
    } catch (cause) {
      setToast({
        tone: "danger",
        title: "Base could not be saved",
        message: errorText(cause, "Review the entered values and try again."),
      });
    } finally {
      setSavingBase(false);
    }
  };

  const toggleBase = async (base: BaseStationRead) => {
    if (!effectiveAmoId) return;
    const nextActive = !base.is_active;
    if (!window.confirm(`${nextActive ? "Reactivate" : "Deactivate"} ${base.code} · ${base.name}?`)) return;
    try {
      await syncContext(effectiveAmoId);
      await updateBaseStation(base.id, { is_active: nextActive });
      setToast({
        tone: "success",
        title: nextActive ? "Base reactivated" : "Base deactivated",
        message: `${base.code} · ${base.name}`,
      });
      await loadSetup(false);
    } catch (cause) {
      setToast({
        tone: "danger",
        title: "Base status was not changed",
        message: errorText(cause, "Could not update the base station."),
      });
    }
  };

  const handleUpload = async (kind: AssetKind, files?: FileList | null) => {
    const file = files?.[0];
    if (!file || !effectiveAmoId) return;
    setUploading(kind);
    setTransferProgress(null);
    try {
      await syncContext(effectiveAmoId);
      const updated = kind === "logo"
        ? await uploadAmoLogo(file, isSuperuser ? effectiveAmoId : null, setTransferProgress)
        : await uploadAmoTemplate(file, isSuperuser ? effectiveAmoId : null, setTransferProgress);
      setAssets(updated);
      setToast({
        tone: "success",
        title: kind === "logo" ? "Logo uploaded" : "CRS template uploaded",
        message: file.name,
      });
    } catch (cause) {
      setToast({
        tone: "danger",
        title: "Upload failed",
        message: errorText(cause, `Could not upload the ${kind}.`),
      });
    } finally {
      setUploading(null);
      setTransferProgress(null);
      if (logoInputRef.current) logoInputRef.current.value = "";
      if (templateInputRef.current) templateInputRef.current.value = "";
    }
  };

  const downloadOrPreview = async (kind: AssetKind, preview: boolean) => {
    if (!effectiveAmoId) return;
    try {
      await syncContext(effectiveAmoId);
      const downloaded = await downloadAmoAsset(
        kind,
        isSuperuser ? effectiveAmoId : null,
        setTransferProgress,
      );
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
          name: kind === "logo"
            ? assets?.crs_logo_filename || "amo-logo"
            : assets?.crs_template_filename || "crs-template.pdf",
        };
      });
    } catch (cause) {
      setToast({
        tone: "danger",
        title: preview ? "Preview unavailable" : "Download failed",
        message: errorText(cause, `Could not ${preview ? "preview" : "download"} the ${kind}.`),
      });
    } finally {
      setTransferProgress(null);
    }
  };

  const activeIndex = steps.findIndex((step) => step.key === activeStep);
  const ActiveStepIcon = activeStepData.icon;

  const renderActiveContent = () => {
    if (loading) {
      return (
        <div className="setup-resend__loading" aria-live="polite">
          <RefreshCw size={17} className="is-spinning" />
          Loading the selected AMO…
        </div>
      );
    }

    if (activeStep === "bases") {
      return (
        <div className="setup-resend__content">
          <div className="setup-resend__content-action">
            <span>Canonical records used by Workforce, Rostering, HR and maintenance.</span>
            <Button type="button" size="sm" onClick={() => startBase()}>
              <Plus size={15} /> Add base
            </Button>
          </div>
          <div className="setup-resend__rows">
            {bases.map((base) => {
              const located = base.latitude != null && base.longitude != null;
              return (
                <article key={base.id} className={!base.is_active ? "is-inactive" : undefined}>
                  <div className="setup-resend__row-icon"><MapPin size={17} /></div>
                  <div className="setup-resend__row-copy">
                    <strong>{base.code} · {base.name}</strong>
                    <span>
                      {base.base_type.replaceAll("_", " ")}
                      {" · "}
                      {located ? `${base.latitude?.toFixed(5)}, ${base.longitude?.toFixed(5)}` : "Location not configured"}
                    </span>
                  </div>
                  <div className="setup-resend__row-actions">
                    <button type="button" onClick={() => startBase(base)}><Pencil size={14} /> Edit</button>
                    <button type="button" onClick={() => void toggleBase(base)}>
                      {base.is_active ? "Deactivate" : "Reactivate"}
                    </button>
                  </div>
                </article>
              );
            })}
            {!bases.length ? (
              <div className="setup-resend__empty">
                <MapPin size={25} />
                <strong>No operating base exists</strong>
                <span>Create the main base before assigning employment contracts.</span>
                <Button type="button" size="sm" onClick={() => startBase()}>
                  <Plus size={15} /> Create main base
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      );
    }

    if (activeStep === "departments") {
      return (
        <div className="setup-resend__content setup-resend__content--embedded">
          <DepartmentManager
            departments={departments}
            loading={loading}
            onChanged={() => loadSetup(false)}
          />
        </div>
      );
    }

    if (activeStep === "users") {
      const issueCount = identityHealth?.issues.length || 0;
      return (
        <div className="setup-resend__content">
          <div className="setup-resend__metrics">
            <div><strong>{activeUsers.length}</strong><span>active users</span></div>
            <div><strong>{identityHealth?.active_users_without_profile || 0}</strong><span>without personnel profile</span></div>
            <div><strong>{issueCount}</strong><span>identity issues</span></div>
          </div>
          <div className="setup-resend__action-stack">
            <p>Use the user workspace to create accounts, assign departments and resolve canonical personnel identities.</p>
            <Button
              type="button"
              onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/admin/users`)}
            >
              Open users and access <ArrowRight size={15} />
            </Button>
          </div>
        </div>
      );
    }

    if (activeStep === "workforce") {
      return (
        <div className="setup-resend__content">
          <div className="setup-resend__metrics">
            <div><strong>{workforce?.employees_without_contract_count ?? "—"}</strong><span>missing contract</span></div>
            <div><strong>{workforce?.employees_without_base_count ?? "—"}</strong><span>missing primary base</span></div>
            <div><strong>{workforce?.employees_without_pattern_count ?? "—"}</strong><span>missing work pattern</span></div>
          </div>
          <div className="setup-resend__action-stack">
            <p>Contracts and work patterns remain effective-dated and are managed from the Workforce settings workspace.</p>
            <Button
              type="button"
              onClick={() => navigate(`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=workforce`)}
            >
              Open Workforce settings <ArrowRight size={15} />
            </Button>
          </div>
        </div>
      );
    }

    if (activeStep === "assets") {
      return (
        <div className="setup-resend__content">
          <div className="setup-resend__asset-list">
            <article>
              <div className="setup-resend__asset-status">
                {hasLogo ? <BadgeCheck size={20} /> : <CircleAlert size={20} />}
              </div>
              <div>
                <strong>AMO logo</strong>
                <span>{assets?.crs_logo_filename || "No approved logo uploaded"}</span>
              </div>
              <div className="setup-resend__asset-actions">
                <input
                  ref={logoInputRef}
                  hidden
                  type="file"
                  accept=".png,.jpg,.jpeg,.svg"
                  onChange={(event) => void handleUpload("logo", event.target.files)}
                />
                <button type="button" onClick={() => logoInputRef.current?.click()} disabled={uploading === "logo"}>
                  <Upload size={14} /> {hasLogo ? "Replace" : "Upload"}
                </button>
                <button type="button" onClick={() => void downloadOrPreview("logo", true)} disabled={!hasLogo}>Preview</button>
              </div>
            </article>
            <article>
              <div className="setup-resend__asset-status">
                {hasTemplate ? <BadgeCheck size={20} /> : <CircleAlert size={20} />}
              </div>
              <div>
                <strong>CRS PDF template</strong>
                <span>{assets?.crs_template_filename || "No controlled template uploaded"}</span>
              </div>
              <div className="setup-resend__asset-actions">
                <input
                  ref={templateInputRef}
                  hidden
                  type="file"
                  accept="application/pdf"
                  onChange={(event) => void handleUpload("template", event.target.files)}
                />
                <button type="button" onClick={() => templateInputRef.current?.click()} disabled={uploading === "template"}>
                  <Upload size={14} /> {hasTemplate ? "Replace" : "Upload"}
                </button>
                <button type="button" onClick={() => void downloadOrPreview("template", true)} disabled={!hasTemplate}>Preview</button>
                <button type="button" onClick={() => void downloadOrPreview("template", false)} disabled={!hasTemplate}>
                  <Download size={14} />
                </button>
              </div>
            </article>
          </div>
          {transferProgress ? (
            <div className="setup-resend__transfer">
              <progress value={transferProgress.percent ?? undefined} max={100} />
              <span>{transferProgress.percent == null ? "Transferring…" : `${Math.round(transferProgress.percent)}%`}</span>
            </div>
          ) : null}
          {previewAsset ? (
            <div className="setup-resend__asset-preview">
              <div>
                <strong>{previewAsset.name}</strong>
                <button type="button" aria-label="Close preview" onClick={clearPreview}><X size={15} /></button>
              </div>
              {previewAsset.kind === "logo"
                ? <img src={previewAsset.url} alt="AMO logo preview" />
                : <iframe src={previewAsset.url} title="CRS template preview" />}
            </div>
          ) : null}
        </div>
      );
    }

    return (
      <div className="setup-resend__content">
        <div className="setup-resend__module-links">
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/users`}>
            <Users size={18} /><span><strong>Users & access</strong><small>People, departments, roles and permissions</small></span><ArrowRight size={15} />
          </Link>
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/rostering/settings?section=workforce`}>
            <BriefcaseBusiness size={18} /><span><strong>Workforce</strong><small>Contracts, bases and work patterns</small></span><ArrowRight size={15} />
          </Link>
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/document-control/administration`}>
            <BookOpenCheck size={18} /><span><strong>Document Control</strong><small>Ownership, workflows and registers</small></span><ArrowRight size={15} />
          </Link>
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/email-settings`}>
            <Mail size={18} /><span><strong>Email delivery</strong><small>Sender and notification readiness</small></span><ArrowRight size={15} />
          </Link>
          <Link to={`/maintenance/${encodeURIComponent(amoCode)}/admin/billing`}>
            <Building2 size={18} /><span><strong>Subscription</strong><small>Plan and enabled modules</small></span><ArrowRight size={15} />
          </Link>
        </div>
      </div>
    );
  };

  if (currentUser && !canAccessAdmin) return null;

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment="admin-assets">
      <main className="setup-resend">
        {toast ? (
          <SetupToast
            tone={toast.tone}
            title={toast.title}
            message={toast.message}
            onClose={() => setToast(null)}
          />
        ) : null}

        <header className="setup-resend__header">
          <div className="setup-resend__header-icon"><ShieldCheck size={25} /></div>
          <div>
            <h1>AMO setup</h1>
            <p>Configure the shared records every enabled portal module relies on.</p>
          </div>
          <div className="setup-resend__header-actions">
            {isSuperuser && amos.length ? (
              <label>
                <span>Support AMO</span>
                <select value={effectiveAmoId || ""} onChange={(event) => selectSupportAmo(event.target.value)}>
                  {amos.map((amo) => (
                    <option key={amo.id} value={amo.id}>
                      {amo.amo_code} — {amo.name}{amo.is_demo ? " [DEMO]" : " [REAL]"}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <Button type="button" size="sm" variant="secondary" disabled={loading || refreshing} onClick={() => void loadSetup(false)}>
              <RefreshCw size={14} className={refreshing ? "is-spinning" : ""} />
              Refresh
            </Button>
          </div>
        </header>

        <section className="setup-resend__workspace">
          <div className="setup-resend__rail" aria-label="AMO setup workflow">
            {steps.map((step, index) => {
              const Icon = step.icon;
              const active = step.key === activeStep;
              return (
                <article
                  key={step.key}
                  className={[
                    "setup-resend__step",
                    active ? "is-active" : "",
                    step.complete ? "is-complete" : "is-pending",
                  ].filter(Boolean).join(" ")}
                >
                  <button
                    className="setup-resend__marker"
                    type="button"
                    aria-label={`Open ${step.title}`}
                    aria-current={active ? "step" : undefined}
                    onClick={() => selectStep(step.key)}
                  >
                    {step.complete ? <Check size={13} /> : <span>{index + 1}</span>}
                  </button>

                  <div className="setup-resend__step-shell">
                    <button
                      className="setup-resend__step-heading"
                      type="button"
                      onClick={() => selectStep(step.key)}
                    >
                      <Icon size={18} />
                      <span>
                        <strong>{step.title}</strong>
                        <small>{step.summary}</small>
                      </span>
                      {!active ? <ArrowRight size={15} /> : null}
                    </button>

                    {active ? (
                      <div className="setup-resend__step-body">
                        <p>{step.description}</p>
                        {renderActiveContent()}
                      </div>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>

          <aside className="setup-resend__context" aria-label="Current setup context">
            <div className="setup-resend__context-progress">
              <span>{completionPercent}% ready</span>
              <progress value={completionPercent} max={100} />
              <small>{completedCount} of {steps.length - 1} core stages complete</small>
            </div>

            <div className="setup-resend__context-card">
              <div className="setup-resend__context-card-head">
                <div><ActiveStepIcon size={18} /></div>
                <span>
                  <strong>{activeStepData.title}</strong>
                  <small>Current stage {activeIndex + 1} of {steps.length}</small>
                </span>
              </div>
              <p>{activeStepData.description}</p>
              <div className="setup-resend__context-lines">
                <span />
                <span />
                <span />
              </div>
            </div>

            <div className="setup-resend__context-note">
              <ShieldCheck size={16} />
              <p>Changes apply only to the selected AMO. Failed data sources are cleared rather than replaced with another tenant's records.</p>
            </div>
          </aside>
        </section>
      </main>

      {baseEditor ? (
        <BaseStationEditorDialog
          editor={baseEditor}
          saving={savingBase}
          onChange={(draft) => setBaseEditor((previous) => previous ? { ...previous, draft } : previous)}
          onClose={() => setBaseEditor(null)}
          onSave={() => void saveBase()}
          onLocationChanged={() => loadSetup(false)}
        />
      ) : null}
    </DepartmentLayout>
  );
};

export default AdminSetupCentreResendPage;
