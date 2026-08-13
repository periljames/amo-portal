import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FileCheck2, Loader2, Paperclip, RefreshCw, Trash2, Upload } from "lucide-react";

import {
  downloadDocumentEvidenceAsset,
  evidenceReference,
  listDocumentEvidenceAssets,
  uploadDocumentEvidenceAsset,
  type DocumentEvidenceAsset,
  type DocumentEvidenceCategory,
  type DocumentEvidenceReference,
} from "../../services/documentControlEvidence";
import "./documentEvidencePicker.css";


type Props = {
  tenant: string;
  manualId: string;
  revisionId?: string | null;
  category: DocumentEvidenceCategory;
  purpose: string;
  value: DocumentEvidenceReference[];
  onChange: (value: DocumentEvidenceReference[]) => void;
  label?: string;
  help?: string;
};

function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentEvidencePicker({
  tenant,
  manualId,
  revisionId,
  category,
  purpose,
  value,
  onChange,
  label = "Controlled evidence",
  help = "Upload or select retained evidence. The DMS stores the checksum and document scope automatically.",
}: Props) {
  const [assets, setAssets] = useState<DocumentEvidenceAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const selectedIds = useMemo(() => new Set(value.map((item) => item.asset_id)), [value]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setAssets(await listDocumentEvidenceAssets(tenant, manualId, revisionId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Controlled evidence could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [manualId, revisionId, tenant]);

  useEffect(() => { void load(); }, [load]);

  const upload = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) {
      setError("Evidence files are limited to 25 MB.");
      return;
    }
    setUploading(true);
    setError("");
    try {
      const asset = await uploadDocumentEvidenceAsset(tenant, manualId, {
        file,
        revisionId,
        category,
        purpose,
      });
      setAssets((current) => [asset, ...current.filter((item) => item.asset_id !== asset.asset_id)]);
      onChange([...value, evidenceReference(asset)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Evidence could not be retained.");
    } finally {
      setUploading(false);
    }
  };

  const toggle = (asset: DocumentEvidenceAsset) => {
    if (selectedIds.has(asset.asset_id)) {
      onChange(value.filter((item) => item.asset_id !== asset.asset_id));
    } else {
      onChange([...value, evidenceReference(asset)]);
    }
  };

  return <fieldset className="dms-evidence-picker">
    <legend>{label}</legend>
    <p>{help}</p>
    <div className="dms-evidence-picker__toolbar">
      <label className="dc-button dc-button--primary dms-evidence-picker__upload">
        {uploading ? <Loader2 size={14} className="dms-spin" /> : <Upload size={14} />}
        {uploading ? "Retaining evidence…" : "Upload evidence"}
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.docx,.xlsx,.txt,.csv,.eml"
          disabled={uploading}
          onChange={(event) => { void upload(event.target.files); event.currentTarget.value = ""; }}
        />
      </label>
      <button type="button" className="dc-button" disabled={loading} onClick={() => void load()}><RefreshCw size={14} /> Refresh evidence</button>
      <span>{value.length} selected</span>
    </div>
    {error ? <div className="dc-form__error" role="alert">{error}</div> : null}

    {value.length ? <div className="dms-evidence-picker__selected" aria-label="Selected controlled evidence">
      {value.map((item) => <div key={item.asset_id}>
        <FileCheck2 size={15} />
        <span><strong>{item.filename}</strong><small>{formatSize(item.size_bytes)} · SHA-256 {item.sha256.slice(0, 12)}…</small></span>
        <button type="button" aria-label={`Remove ${item.filename}`} onClick={() => onChange(value.filter((current) => current.asset_id !== item.asset_id))}><Trash2 size={14} /></button>
      </div>)}
    </div> : null}

    <div className="dms-evidence-picker__library">
      <header><Paperclip size={14} /><strong>Retained evidence for this document</strong></header>
      {loading ? <div className="dms-evidence-picker__state"><Loader2 size={14} className="dms-spin" /> Loading retained evidence…</div> : null}
      {!loading && !assets.length ? <div className="dms-evidence-picker__state">No retained evidence has been uploaded for this document yet.</div> : null}
      {!loading && assets.map((asset) => <div key={asset.asset_id} className={selectedIds.has(asset.asset_id) ? "selected" : ""}>
        <label>
          <input type="checkbox" checked={selectedIds.has(asset.asset_id)} onChange={() => toggle(asset)} />
          <span><strong>{asset.filename}</strong><small>{asset.category.replaceAll("_", " ")} · {formatSize(asset.size_bytes)} · SHA-256 {asset.sha256.slice(0, 12)}…</small></span>
        </label>
        <button type="button" className="dc-button" onClick={() => void downloadDocumentEvidenceAsset(asset)}><Download size={13} /> Open</button>
      </div>)}
    </div>
  </fieldset>;
}