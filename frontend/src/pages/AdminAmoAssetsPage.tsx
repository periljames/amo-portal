// src/pages/AdminAmoAssetsPage.tsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel } from "../components/UI/Admin";
import { getCachedUser, getContext } from "../services/auth";
import { listAdminAmos, listAdminAssets, LS_ACTIVE_AMO_ID } from "../services/adminUsers";
import type { AdminAmoRead, AdminAssetRead } from "../services/adminUsers";
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
  const location = useLocation();

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
  const [previewAsset, setPreviewAsset] = useState<{
    kind: "logo" | "template";
    url: string;
    name: string;
  } | null>(null);
  const [inactiveAssets, setInactiveAssets] = useState<AdminAssetRead[]>([]);
  const [inactiveAssetsError, setInactiveAssetsError] = useState<string | null>(
    null
  );

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

  const activeFilter = useMemo(() => {
    const params = new URLSearchParams(location.search);
    return params.get("filter");
  }, [location.search]);

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

  useEffect(() => {
    return () => {
      if (previewAsset?.url) {
        window.URL.revokeObjectURL(previewAsset.url);
      }
    };
  }, [previewAsset]);

  useEffect(() => {
    const loadInactiveAssets = async () => {
      if (activeFilter !== "inactive") {
        setInactiveAssets([]);
        setInactiveAssetsError(null);
        return;
      }
      if (!effectiveAmoId) return;
      try {
        const data = await listAdminAssets({
          amo_id: effectiveAmoId,
          only_active: false,
        });
        setInactiveAssets(data.filter((asset) => !asset.is_active));
        setInactiveAssetsError(null);
      } catch (err: any) {
        console.error("Failed to load inactive assets", err);
        setInactiveAssetsError(err?.message || "Could not load inactive assets.");
      }
    };

    loadInactiveAssets();
  }, [activeFilter, effectiveAmoId]);

  const handleAmoChange = (nextAmoId: string) => {
    const v = (nextAmoId || "").trim();
    if (!v) return;
    setActiveAmoId(v);
    localStorage.setItem(LS_ACTIVE_AMO_ID, v);
  };

  const clearFilter = () => {
    if (!amoCode) return;
    navigate(`/maintenance/${amoCode}/admin/amo-assets`, { replace: true });
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

  const handlePreview = async (kind: "logo" | "template") => {
    setError(null);
    setDownloadProgress(null);
    try {
      const blob = await downloadAmoAsset(
        kind,
        isSuperuser ? effectiveAmoId : null,
        (progress) => setDownloadProgress({ kind, progress })
      );
      const url = window.URL.createObjectURL(blob);
      const name =
        kind === "logo"
          ? assets?.crs_logo_filename || "amo-logo"
          : assets?.crs_template_filename || "crs-template.pdf";
      setPreviewAsset((prev) => {
        if (prev?.url) window.URL.revokeObjectURL(prev.url);
        return { kind, url, name };
      });
    } catch (e: any) {
      console.error("Failed to preview asset", e);
      setError(e?.message || "Could not preview asset.");
    }
  };

  const clearPreview = () => {
    if (previewAsset?.url) {
      window.URL.revokeObjectURL(previewAsset.url);
    }
    setPreviewAsset(null);
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
  const userDisplayName = currentUser?.full_name || currentUser?.email;

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-assets"
    >
      <div className="admin-page admin-amo-assets">
        <PageHeader
          title="CRS Assets Setup"
          subtitle={
            userDisplayName
              ? `Upload AMO-specific branding and CRS templates. Signed in as ${userDisplayName}.`
              : "Upload AMO-specific branding and CRS templates."
          }
        />

        <div className="admin-page__grid">
          <div className="admin-page__main">
            <Panel title="Current configuration">
              {loading && <p>Loading assets…</p>}
              {error && (
                <InlineAlert tone="danger" title="Error">
                  <span>{error}</span>
                </InlineAlert>
              )}

              {!loading && (
                <>
                  <div className="asset-row">
                    <div className="asset-info">
                      <strong>CRS Logo</strong>
                      <p>{logoStatus}</p>
                      {assets?.crs_logo_uploaded_at && (
                        <p className="asset-meta">
                          Uploaded at {new Date(assets.crs_logo_uploaded_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <div className="asset-actions">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={!assets?.crs_logo_filename}
                        onClick={() => handlePreview("logo")}
                      >
                        View logo
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={!assets?.crs_logo_filename}
                        onClick={() => handleDownload("logo")}
                      >
                        Download logo
                      </Button>
                    </div>
                  </div>
                  {downloadProgress?.kind === "logo" && (
                    <div className="asset-progress">
                      <div>
                        <strong>Logo download</strong>
                        {downloadProgress.progress.percent !== undefined && (
                          <progress
                            value={downloadProgress.progress.percent}
                            max={100}
                            className="asset-progress__bar"
                          />
                        )}
                        <p className="asset-meta">{formatSpeed(downloadProgress.progress)}</p>
                      </div>
                    </div>
                  )}
                  <div className="asset-row">
                    <div className="asset-info">
                      <strong>CRS Template</strong>
                      <p>{templateStatus}</p>
                      {assets?.crs_template_uploaded_at && (
                        <p className="asset-meta">
                          Uploaded at {new Date(assets.crs_template_uploaded_at).toLocaleString()}
                        </p>
                      )}
                    </div>
                    <div className="asset-actions">
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={!assets?.crs_template_filename}
                        onClick={() => handlePreview("template")}
                      >
                        View template
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        disabled={!assets?.crs_template_filename}
                        onClick={() => handleDownload("template")}
                      >
                        Download template
                      </Button>
                    </div>
                  </div>
                  {downloadProgress?.kind === "template" && (
                    <div className="asset-progress">
                      <div>
                        <strong>Template download</strong>
                        {downloadProgress.progress.percent !== undefined && (
                          <progress
                            value={downloadProgress.progress.percent}
                            max={100}
                            className="asset-progress__bar"
                          />
                        )}
                        <p className="asset-meta">{formatSpeed(downloadProgress.progress)}</p>
                      </div>
                    </div>
                  )}
                  {previewAsset && (
                    <div className="asset-preview">
                      <div className="asset-preview__body">
                        <strong className="asset-preview__title">
                          Previewing {previewAsset.kind === "logo" ? "Logo" : "Template"}:{" "}
                          {previewAsset.name}
                        </strong>
                        <div className="asset-preview__frame">
                          {previewAsset.kind === "logo" ? (
                            <img
                              src={previewAsset.url}
                              alt="CRS logo preview"
                              className="asset-preview__image"
                            />
                          ) : (
                            <iframe
                              src={previewAsset.url}
                              title="CRS template preview"
                              className="asset-preview__document"
                            />
                          )}
                        </div>
                      </div>
                      <div className="asset-preview__actions">
                        <Button type="button" size="sm" variant="secondary" onClick={clearPreview}>
                          Close preview
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </Panel>

            <Panel title="Upload assets">
              <div className="form-row asset-upload-row">
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
                  <p className="form-hint asset-hint">
                    Selected {selectedLogoFiles.length} file
                    {selectedLogoFiles.length === 1 ? "" : "s"}:{" "}
                    {selectedLogoFiles.map((file) => file.name).join(", ")}. Only
                    the most recent upload is kept.
                  </p>
                )}
              </div>
              {uploadingLogo && logoUploadProgress && (
                <div className="asset-progress">
                  <div>
                    <strong>Logo upload</strong>
                    {logoUploadProgress.percent !== undefined && (
                      <progress
                        value={logoUploadProgress.percent}
                        max={100}
                        className="asset-progress__bar"
                      />
                    )}
                    <p className="asset-meta">{formatSpeed(logoUploadProgress)}</p>
                  </div>
                </div>
              )}

              <div className="form-row asset-upload-row">
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
                  <p className="form-hint asset-hint">
                    Selected {selectedTemplateFiles.length} file
                    {selectedTemplateFiles.length === 1 ? "" : "s"}:{" "}
                    {selectedTemplateFiles.map((file) => file.name).join(", ")}. Only
                    the most recent upload is kept.
                  </p>
                )}
              </div>
              {uploadingTemplate && templateUploadProgress && (
                <div className="asset-progress">
                  <div>
                    <strong>Template upload</strong>
                    {templateUploadProgress.percent !== undefined && (
                      <progress
                        value={templateUploadProgress.percent}
                        max={100}
                        className="asset-progress__bar"
                      />
                    )}
                    <p className="asset-meta">{formatSpeed(templateUploadProgress)}</p>
                  </div>
                </div>
              )}
            </Panel>
          </div>

          <div className="admin-page__side">
            {activeFilter === "inactive" && (
              <Panel
                title="Filtered assets"
                subtitle="Inactive assets for this AMO."
                actions={(
                  <Button type="button" size="sm" variant="secondary" onClick={clearFilter}>
                    Clear filter
                  </Button>
                )}
              >
                {inactiveAssetsError && (
                  <InlineAlert tone="danger" title="Error">
                    <span>{inactiveAssetsError}</span>
                  </InlineAlert>
                )}
                {!inactiveAssetsError && inactiveAssets.length === 0 && (
                  <p className="admin-muted">No inactive assets found.</p>
                )}
                {!inactiveAssetsError && inactiveAssets.length > 0 && (
                  <ul className="admin-list">
                    {inactiveAssets.map((asset) => (
                      <li key={asset.id}>
                        <div className="admin-list__row admin-overview__activity-row">
                          <div>
                            <strong>{asset.name || asset.kind}</strong>
                            <div className="admin-muted">
                              {asset.original_filename || "Unnamed asset"}
                            </div>
                          </div>
                          <span className="admin-muted">
                            {asset.updated_at
                              ? new Date(asset.updated_at).toLocaleString()
                              : "—"}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            )}

            {isSuperuser && (
              <Panel title="Support mode (SUPERUSER)">
                {amoLoading && <p>Loading AMOs…</p>}
                {amoError && (
                  <InlineAlert tone="danger" title="Error">
                    <span>{amoError}</span>
                  </InlineAlert>
                )}

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
              </Panel>
            )}
          </div>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminAmoAssetsPage;
