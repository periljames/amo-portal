import React, { useEffect, useState } from "react";
import { Download, FileImage, FileUp, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { authHeaders } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import "./ReliabilityTechlogEvidence.css";

type Asset = {
  id: string;
  source_evidence_ref: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  aircraft_serial_number: string;
  techsheet_ref: string;
};
type Props = {
  aircraft: string;
  techsheet: string;
  reference: string;
  onReference?: (value: string) => void;
  canUpload?: boolean;
};
const PREFIX = "OCTM_ASSET:";
const maxFileBytes = 20 * 1024 * 1024;
const acceptedFileTypes = new Set(["application/pdf", "image/jpeg", "image/png"]);

function assetId(reference: string): string | null {
  if (!reference.startsWith(PREFIX)) return null;
  const id = reference.slice(PREFIX.length);
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) ? id : null;
}
function basePath(id?: string) {
  return getApiBaseUrl() + "/reliability/octm/source-assets" + (id ? "/" + encodeURIComponent(id) : "");
}

export default function ReliabilityTechlogEvidence({ aircraft, techsheet, reference, onReference, canUpload = false }: Props): React.ReactElement {
  const [asset, setAsset] = useState<Asset | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const id = assetId(reference.trim());

  useEffect(() => {
    let active = true;
    if (!id) return;
    void fetch(basePath(id), { headers: authHeaders(), credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) throw new Error("The referenced scan is unavailable or access is denied.");
        return response.json() as Promise<Asset>;
      }).then((result) => { if (active) setAsset(result); })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : "Cannot read source file."); });
    return () => { active = false; };
  }, [id]);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const loadPreview = async () => {
    if (!id) return;
    setError(""); setLoading(true);
    try {
      const response = await fetch(basePath(id) + "/content", {
        headers: authHeaders(), credentials: "same-origin", cache: "no-store",
      });
      if (!response.ok) throw new Error("Source document could not be opened. Check permissions and storage.");
      const mime = response.headers.get("content-type")?.split(";")[0];
      if (!mime || !acceptedFileTypes.has(mime)) throw new Error("The server returned an unsupported preview format.");
      const blob = await response.blob();
      if (blob.size > maxFileBytes) throw new Error("Preview exceeds the controlled document size limit.");
      setPreviewUrl(URL.createObjectURL(blob));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Source document preview unavailable.");
    } finally { setLoading(false); }
  };
  const upload = async (file: File | undefined) => {
    if (!file || !onReference) return;
    if (!aircraft.trim() || !techsheet.trim()) {
      setError("Select a registered aircraft and enter the technical-log page before uploading its scan.");
      return;
    }
    if (!acceptedFileTypes.has(file.type) || file.size > maxFileBytes || file.size === 0) {
      setError("Use a nonempty PDF, PNG or JPEG scan no larger than 20 MB.");
      return;
    }
    setUploading(true); setError("");
    const form = new FormData();
    form.append("aircraft_serial_number", aircraft.trim());
    form.append("techsheet_ref", techsheet.trim());
    form.append("file", file);
    try {
      const response = await fetch(basePath(), {
        method: "POST", headers: authHeaders(), body: form, credentials: "same-origin",
      });
      if (!response.ok) {
        let message = "Source scan could not be retained.";
        try {
          const problem = await response.json() as { detail?: string };
          if (typeof problem.detail === "string") message = problem.detail;
        } catch { /* keep safe fallback */ }
        throw new Error(message);
      }
      const retained = await response.json() as Asset;
      setAsset(retained);
      onReference(retained.source_evidence_ref);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Evidence upload failed."); }
    finally { setUploading(false); }
  };
  const matches = !!asset && asset.aircraft_serial_number === aircraft && asset.techsheet_ref === techsheet;

  return <section className="rel-techlog-evidence" aria-label="Controlled technical-log source scan">
    <div className="rel-techlog-evidence__heading"><FileImage size={19} aria-hidden="true" />
      <div><strong>Original SL/MCM/1 scanned page</strong><small>Retained source evidence · Read-only preview</small></div>
    </div>
    {canUpload && onReference && <label className="rel-techlog-evidence__upload">
      <FileUp size={17} aria-hidden="true" /> {uploading ? "Retaining scan…" : "Upload source PDF / image"}
      <input type="file" accept=".pdf,.png,.jpg,.jpeg" disabled={uploading || !aircraft || !techsheet}
        onChange={(event) => { void upload(event.currentTarget.files?.[0]); event.currentTarget.value = ""; }} />
    </label>}
    {id && matches && <div className="rel-techlog-evidence__metadata">
      <ShieldCheck size={15} aria-hidden="true" />
      <span><strong>{asset.filename}</strong><small>{(asset.size_bytes / 1024).toFixed(1)} KB · SHA-256 {asset.sha256.slice(0, 16)}…</small></span>
    </div>}
    {id && asset && !matches && <p role="alert" className="rel-techlog-evidence__error">
      This scan belongs to {asset.aircraft_serial_number} / {asset.techsheet_ref}, not the selected page. Upload the correct scan.</p>}
    {id && matches && <div className="rel-techlog-evidence__buttons">
      <button type="button" disabled={loading} onClick={() => void loadPreview()}>
        {loading ? <Loader2 size={15} aria-hidden="true" /> : <RefreshCw size={15} aria-hidden="true" />}
        {previewUrl ? "Reload original scan" : "Preview original scan"}
      </button>
      {previewUrl && <a href={previewUrl} download={asset.filename}><Download size={15} aria-hidden="true" /> Save copy</a>}
    </div>}
    {id && !asset && !error && <p role="status">Resolving controlled source scan…</p>}
    {error && <p role="alert" className="rel-techlog-evidence__error">{error}</p>}
    {previewUrl && asset && matches && <div className="rel-techlog-evidence__preview">
      {asset.mime_type === "application/pdf"
        ? <iframe title={"Read-only technical-log scan " + asset.filename} src={previewUrl} />
        : <img src={previewUrl} alt={"Source scan " + asset.filename} />}
    </div>}
    {!id && <p className="rel-techlog-evidence__note">An external evidence reference alone is not a stored
      scan. Upload the original for side-by-side checking; existing paper references remain valid as references,
      but must be independently examined.</p>}
  </section>;
}
