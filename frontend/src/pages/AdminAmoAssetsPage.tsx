// src/pages/AdminAmoAssetsPage.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../services/auth";
import { listAdminAmos, LS_ACTIVE_AMO_ID } from "../services/adminUsers";
import type { AdminAmoRead } from "../services/adminUsers";
import {
  downloadAmoAsset,
  getAmoAssets,
  uploadAmoLogo,
  uploadAmoTemplate,
} from "../services/amoAssets.ts";

import type { AmoAssetRead, TransferProgress } from "../services/amoAssets.ts";

type UrlParams = {
  amoCode?: string;
};

const AdminAmoAssetsPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const ctx = getContext();

  const isSuperuser = !!currentUser?.is_superuser;
  const isAmoAdmin = !!currentUser?.is_amo_admin;
  const canAccessAdmin = isSuperuser || isAmoAdmin;

  const [assets, setAssets] = useState<AmoAssetRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [uploadingTemplate, setUploadingTemplate] = useState(false);
  const [selectedLogoFiles, setSelectedLogoFiles] = useState<File[]>([]);
  const [selectedTemplateFiles, setSelectedTemplateFiles] = useState<File[]>([]);
  const [logoUploadProgress, setLogoUploadProgress] = useState<TransferProgress | null>(null);
  const [templateUploadProgress, setTemplateUploadProgress] = useState<TransferProgress | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<{
    kind: "logo" | "template";
    progress: TransferProgress;
  } | null>(null);

  const logoInputRef = useRef<HTMLInputElement | null>(null);
  const templateInputRef = useRef<HTMLInputElement | null>(null);

  const [amos, setAmos] = useState<AdminAmoRead[]>([]);
  const [amoLoading, setAmoLoading] = useState(false);
  const [amoError, setAmoError] = useState<string | null>(null);

  const [activeAmoId, setActiveAmoId] = useState<string | null>(() => {
    const v = localStorage.getItem(LS_ACTIVE_AMO_ID);
    return v && v.trim() ? v.trim() : null;
  });

  const effectiveAmoId = useMemo(() => {
    if (!currentUser?.amo_id) return null;
    if (isSuperuser) return activeAmoId || currentUser.amo_id;
    return currentUser.amo_id;
  }, [currentUser?.amo_id, isSuperuser, activeAmoId]);

  useEffect(() => {
    if (!currentUser) return;
    if (canAccessAdmin) return;

    const dept = ctx.department;
    if (amoCode && dept) {
      navigate(`/maintenance/${amoCode}/${dept}`, { replace: true });
      return;
    }

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/login`, { replace: true });
      return;
    }

    navigate("/login", { replace: true });
  }, [currentUser, canAccessAdmin, amoCode, ctx.department, navigate]);

  useEffect(() => {
    if (!isSuperuser) return;

    const loadAmos = async () => {
      setAmoError(null);
      setAmoLoading(true);
      try {
        const data = await listAdminAmos();
        setAmos(data);

        const stored = localStorage.getItem(LS_ACTIVE_AMO_ID);
        const storedTrimmed = stored && stored.trim() ? stored.trim() : null;
        const storedValid =
          !!storedTrimmed && data.some((a) => a.id === storedTrimmed);

        if (!storedValid) {
          const preferred =
            currentUser?.amo_id && data.some((a) => a.id === currentUser.amo_id)
              ? currentUser.amo_id
              : null;

          const fallback = preferred || data[0]?.id || null;

          if (fallback) {
            localStorage.setItem(LS_ACTIVE_AMO_ID, fallback);
            setActiveAmoId(fallback);
          }
        }
      } catch (e: any) {
        console.error("Failed to load AMOs", e);
        setAmoError(e?.message || "Could not load AMOs.");
      } finally {
        setAmoLoading(false);
      }
    };

    loadAmos();
  }, [isSuperuser, currentUser?.amo_id]);

  useEffect(() => {
    const loadAssets = async () => {
      if (!currentUser) return;
      if (!canAccessAdmin) return;
      if (!effectiveAmoId) {
        setError("Could not determine AMO context.");
        return;
      }

      setError(null);
      setLoading(true);
      try {
        const data = await getAmoAssets(isSuperuser ? effectiveAmoId : null);
        setAssets(data);
      } catch (e: any) {
        console.error("Failed to load AMO assets", e);
        setError(e?.message || "Could not load AMO assets.");
      } finally {
        setLoading(false);
      }
    };

    loadAssets();
  }, [currentUser, canAccessAdmin, effectiveAmoId, isSuperuser]);

  const handleAmoChange = (nextAmoId: string) => {
    const v = (nextAmoId || "").trim();
    if (!v) return;
    setActiveAmoId(v);
    localStorage.setItem(LS_ACTIVE_AMO_ID, v);
  };

  const handleUploadLogo = async (files?: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploadingLogo(true);
    setLogoUploadProgress(null);
    setError(null);
    const uploads = Array.from(files);
    setSelectedLogoFiles(uploads);
    try {
      let latest = assets;
      for (const file of uploads) {
        latest = await uploadAmoLogo(
          file,
          isSuperuser ? effectiveAmoId : null,
          (progress) => setLogoUploadProgress(progress)
        );
      }
      if (latest) setAssets(latest);
      setSelectedLogoFiles([]);
      if (logoInputRef.current) logoInputRef.current.value = "";
    } catch (e: any) {
      console.error("Failed to upload logo", e);
      setError(e?.message || "Could not upload logo.");
    } finally {
      setUploadingLogo(false);
      setLogoUploadProgress(null);
    }
  };

  const handleUploadTemplate = async (files?: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploadingTemplate(true);
    setTemplateUploadProgress(null);
    setError(null);
    const uploads = Array.from(files);
    setSelectedTemplateFiles(uploads);
    try {
      let latest = assets;
      for (const file of uploads) {
        latest = await uploadAmoTemplate(
          file,
          isSuperuser ? effectiveAmoId : null,
          (progress) => setTemplateUploadProgress(progress)
        );
      }
      if (latest) setAssets(latest);
      setSelectedTemplateFiles([]);
      if (templateInputRef.current) templateInputRef.current.value = "";
    } catch (e: any) {
      console.error("Failed to upload template", e);
      setError(e?.message || "Could not upload template.");
    } finally {
      setUploadingTemplate(false);
      setTemplateUploadProgress(null);
    }
  };

  const handleDownload = async (kind: "logo" | "template") => {
    setError(null);
    setDownloadProgress(null);
    try {
      const blob = await downloadAmoAsset(
        kind,
        isSuperuser ? effectiveAmoId : null,
        (progress) => setDownloadProgress({ kind, progress })
      );
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      const filename =
        kind === "logo"
          ? assets?.crs_logo_filename || "amo-logo"
          : assets?.crs_template_filename || "crs-template.pdf";

      link.href = url;
      link.download = filename;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      console.error("Failed to download asset", e);
      setError(e?.message || "Could not download asset.");
    } finally {
      setDownloadProgress(null);
    }
  };

  const formatSpeed = (progress: TransferProgress) => {
    const mbps = progress.megaBytesPerSecond;
    const mbits = progress.megaBitsPerSecond;
    const mbpsLabel = Number.isFinite(mbps) ? mbps.toFixed(2) : "0.00";
    const mbitsLabel = Number.isFinite(mbits) ? mbits.toFixed(2) : "0.00";
    return `${mbpsLabel} MB/s • ${mbitsLabel} Mb/s`;
  };

  if (currentUser && !canAccessAdmin) {
    return null;
  }

  const logoStatus = assets?.crs_logo_filename
    ? `Uploaded: ${assets.crs_logo_filename}`
    : "No logo uploaded";
  const templateStatus = assets?.crs_template_filename
    ? `Uploaded: ${assets.crs_template_filename}`
    : "No template uploaded";

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-assets"
    >
      <header className="page-header">
        <h1 className="page-header__title">CRS Assets Setup</h1>
        <p className="page-header__subtitle">
          Upload AMO-specific branding and CRS templates.
          {currentUser && (
            <>
              {" "}Signed in as <strong>{currentUser.full_name}</strong>.
            </>
          )}
        </p>
      </header>

      {isSuperuser && (
        <section className="page-section">
          <div className="card card--form" style={{ padding: 16 }}>
            <h3 style={{ marginTop: 0, marginBottom: 8 }}>
              Support mode (SUPERUSER)
            </h3>

            {amoLoading && <p>Loading AMOs…</p>}
            {amoError && <div className="alert alert-error">{amoError}</div>}

            {!amoLoading && !amoError && (
              <div className="form-row">
                <label htmlFor="amoSelect">Active AMO</label>
                <select
                  id="amoSelect"
                  value={effectiveAmoId ?? ""}
                  onChange={(e) => handleAmoChange(e.target.value)}
                  disabled={amos.length === 0}
                >
                  {amos.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.amo_code} — {a.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="page-section">
        {loading && <p>Loading assets…</p>}
        {error && <div className="alert alert-error">{error}</div>}

        {!loading && (
          <div className="card card--form" style={{ padding: 16 }}>
            <h2 style={{ marginTop: 0 }}>Current configuration</h2>
            <div className="form-row" style={{ marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <strong>CRS Logo</strong>
                <p style={{ marginTop: 6 }}>{logoStatus}</p>
                {assets?.crs_logo_uploaded_at && (
                  <p style={{ marginTop: 4, opacity: 0.75 }}>
                    Uploaded at {new Date(assets.crs_logo_uploaded_at).toLocaleString()}
                  </p>
                )}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={!assets?.crs_logo_filename}
                  onClick={() => handleDownload("logo")}
                >
                  Download logo
                </button>
              </div>
            </div>
            {downloadProgress?.kind === "logo" && (
              <div className="form-row" style={{ marginBottom: 12 }}>
                <div style={{ flex: 1 }}>
                  <strong>Logo download</strong>
                  {downloadProgress.progress.percent !== undefined && (
                    <progress
                      value={downloadProgress.progress.percent}
                      max={100}
                      style={{ width: "100%", height: 10, marginTop: 6 }}
                    />
                  )}
                  <p style={{ marginTop: 6, opacity: 0.8 }}>
                    {formatSpeed(downloadProgress.progress)}
                  </p>
                </div>
              </div>
            )}
            <div className="form-row" style={{ marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <strong>CRS Template</strong>
                <p style={{ marginTop: 6 }}>{templateStatus}</p>
                {assets?.crs_template_uploaded_at && (
                  <p style={{ marginTop: 4, opacity: 0.75 }}>
                    Uploaded at {new Date(assets.crs_template_uploaded_at).toLocaleString()}
                  </p>
                )}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={!assets?.crs_template_filename}
                  onClick={() => handleDownload("template")}
                >
                  Download template
                </button>
              </div>
            </div>
            {downloadProgress?.kind === "template" && (
              <div className="form-row" style={{ marginBottom: 12 }}>
                <div style={{ flex: 1 }}>
                  <strong>Template download</strong>
                  {downloadProgress.progress.percent !== undefined && (
                    <progress
                      value={downloadProgress.progress.percent}
                      max={100}
                      style={{ width: "100%", height: 10, marginTop: 6 }}
                    />
                  )}
                  <p style={{ marginTop: 6, opacity: 0.8 }}>
                    {formatSpeed(downloadProgress.progress)}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="page-section">
        <div className="card card--form" style={{ padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Upload assets</h2>

          <div className="form-row" style={{ alignItems: "center" }}>
            <label htmlFor="logoUpload">CRS Logo (.png, .jpg, .svg)</label>
            <input
              id="logoUpload"
              type="file"
              multiple
              accept=".png,.jpg,.jpeg,.svg"
              onChange={(e) => handleUploadLogo(e.target.files)}
              disabled={uploadingLogo}
              ref={logoInputRef}
            />
            {uploadingLogo && <span>Uploading…</span>}
            {selectedLogoFiles.length > 0 && !uploadingLogo && (
              <p className="form-hint">
                Selected {selectedLogoFiles.length} file
                {selectedLogoFiles.length === 1 ? "" : "s"}:{" "}
                {selectedLogoFiles.map((file) => file.name).join(", ")}. Only
                the most recent upload is kept.
              </p>
            )}
          </div>
          {uploadingLogo && logoUploadProgress && (
            <div className="form-row" style={{ marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <strong>Logo upload</strong>
                {logoUploadProgress.percent !== undefined && (
                  <progress
                    value={logoUploadProgress.percent}
                    max={100}
                    style={{ width: "100%", height: 10, marginTop: 6 }}
                  />
                )}
                <p style={{ marginTop: 6, opacity: 0.8 }}>
                  {formatSpeed(logoUploadProgress)}
                </p>
              </div>
            </div>
          )}

          <div className="form-row" style={{ alignItems: "center" }}>
            <label htmlFor="templateUpload">CRS Template (.pdf)</label>
            <input
              id="templateUpload"
              type="file"
              multiple
              accept="application/pdf"
              onChange={(e) => handleUploadTemplate(e.target.files)}
              disabled={uploadingTemplate}
              ref={templateInputRef}
            />
            {uploadingTemplate && <span>Uploading…</span>}
            {selectedTemplateFiles.length > 0 && !uploadingTemplate && (
              <p className="form-hint">
                Selected {selectedTemplateFiles.length} file
                {selectedTemplateFiles.length === 1 ? "" : "s"}:{" "}
                {selectedTemplateFiles.map((file) => file.name).join(", ")}. Only
                the most recent upload is kept.
              </p>
            )}
          </div>
          {uploadingTemplate && templateUploadProgress && (
            <div className="form-row" style={{ marginBottom: 12 }}>
              <div style={{ flex: 1 }}>
                <strong>Template upload</strong>
                {templateUploadProgress.percent !== undefined && (
                  <progress
                    value={templateUploadProgress.percent}
                    max={100}
                    style={{ width: "100%", height: 10, marginTop: 6 }}
                  />
                )}
                <p style={{ marginTop: 6, opacity: 0.8 }}>
                  {formatSpeed(templateUploadProgress)}
                </p>
              </div>
            </div>
          )}
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default AdminAmoAssetsPage;
