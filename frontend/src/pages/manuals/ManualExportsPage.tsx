import { useEffect, useState } from "react";
import { createRevisionExport, listRevisionExports, type ManualExportPayload } from "../../services/manuals";
import { useManualRouteContext } from "./context";
import ManualsPageLayout from "./ManualsPageLayout";

export default function ManualExportsPage() {
  const { tenant, manualId, revId } = useManualRouteContext();
  const [items, setItems] = useState<ManualExportPayload[]>([]);
  const [controlled, setControlled] = useState(false);
  const [watermark, setWatermark] = useState(true);

  const refresh = () => {
    if (!tenant || !manualId || !revId) return;
    listRevisionExports(tenant, manualId, revId).then(setItems).catch(() => setItems([]));
  };

  useEffect(() => {
    refresh();
  }, [tenant, manualId, revId]);

  return (
    <ManualsPageLayout title="Export Artifacts">
      <div className="rounded border p-3 space-y-2 text-sm">
        <label className="flex items-center justify-between"><span>UNCONTROLLED WHEN PRINTED watermark</span><input type="checkbox" checked={watermark} onChange={(e) => setWatermark(e.target.checked)} /></label>
        <label className="flex items-center justify-between"><span>CONTROLLED HARD COPY</span><input type="checkbox" checked={controlled} onChange={(e) => setControlled(e.target.checked)} /></label>
        <button
          className="rounded bg-slate-900 px-3 py-1 text-xs text-white"
          onClick={async () => {
            if (!tenant || !manualId || !revId) return;
            await createRevisionExport(tenant, manualId, revId, {
              controlled_bool: controlled,
              watermark_uncontrolled_bool: watermark,
              version_label: `${controlled ? "C" : "U"}-${Date.now()}`,
            });
            refresh();
          }}
        >
          Generate Export
        </button>
      </div>

      <div className="rounded border p-3">
        <h2 className="font-medium mb-2">Generated artifacts</h2>
        <ul className="space-y-2 text-sm">
          {items.map((item) => (
            <li key={item.id} className="rounded border p-2">
              <div><b>{item.controlled ? "Controlled" : "Uncontrolled"}</b> · watermark: {item.watermark_uncontrolled ? "ON" : "OFF"}</div>
              <div className="text-xs text-slate-500">{item.generated_at} · sha256 {item.sha256.slice(0, 16)}…</div>
            </li>
          ))}
        </ul>
      </div>
    </ManualsPageLayout>
  );
}
