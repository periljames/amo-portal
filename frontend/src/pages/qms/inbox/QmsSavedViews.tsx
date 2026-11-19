import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest, qmsPath } from "../../../services/apiClient";

export type SavedWorkFilters = {
  view: string;
  q: string;
  source: string;
  due: string;
  sort: string;
};
type StoredView = { id: string; title: string; filters: SavedWorkFilters };
type SavedViewsResponse = { items: StoredView[]; limit: number };

export default function QmsSavedViews({
  amoCode, filters, onApply,
}: {
  amoCode: string;
  filters: SavedWorkFilters;
  onApply: (saved: SavedWorkFilters) => void;
}) {
  const queryClient = useQueryClient();
  const queryKey = ["qms-work-saved-views", amoCode];
  const [title, setTitle] = useState("");
  const [selection, setSelection] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const endpoint = qmsPath(amoCode, "/work-inbox/saved-views");

  const saved = useQuery({
    queryKey,
    enabled: Boolean(amoCode),
    queryFn: ({ signal }) => apiRequest<SavedViewsResponse>(endpoint, { signal, cacheTtlMs: 0 }),
  });
  const create = useMutation({
    mutationFn: (newTitle: string) => apiRequest<StoredView>(endpoint, {
      method: "POST", body: JSON.stringify({ title: newTitle, ...filters }),
    }),
    onSuccess: async (item) => {
      setError("");
      setTitle("");
      setSelection(item.id);
      setNotice("Saved \"" + item.title + "\" for your own account.");
      await queryClient.invalidateQueries({ queryKey });
    },
    onError: (cause) => {
      setNotice("");
      setError(cause instanceof Error ? cause.message : "The saved view could not be created.");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest(endpoint + "/" + encodeURIComponent(id), { method: "DELETE" }),
    onSuccess: async () => {
      setError("");
      setSelection("");
      setNotice("Saved view removed.");
      await queryClient.invalidateQueries({ queryKey });
    },
    onError: (cause) => {
      setNotice("");
      setError(cause instanceof Error ? cause.message : "The saved view could not be removed.");
    },
  });
  const rows = saved.data?.items || [];
  const selected = rows.find(item => item.id === selection);
  const working = create.isPending || remove.isPending;

  return <section className="qms-saved-views" aria-label="My saved Quality work views">
    <div className="qms-saved-views__heading">
      <div><h3>My saved filters</h3>
        <p>Keep useful work searches for your account. Saved filters do not grant access to source records.</p></div>
      <span>{rows.length} / {saved.data?.limit || 20}</span>
    </div>
    <div className="qms-saved-views__controls">
      <label>Saved view
        <select value={selection} disabled={saved.isLoading || working}
          onChange={event => { setSelection(event.target.value); setNotice(""); setError(""); }}>
          <option value="">Choose a saved view</option>
          {rows.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
      </label>
      <button type="button" disabled={!selected || working}
        onClick={() => { if (selected) { onApply(selected.filters); setNotice("Applied \"" + selected.title + "\"."); } }}>
        Apply filters
      </button>
      <button type="button" disabled={!selected || working}
        onClick={() => { if (selected) remove.mutate(selected.id); }}>
        Remove saved view
      </button>
      <form onSubmit={event => {
        event.preventDefault();
        if (title.trim().length >= 2) create.mutate(title.trim());
      }} aria-label="Save current work filters">
        <label>Save current filters as
          <input type="text" maxLength={80} minLength={2}
            value={title} placeholder="e.g. My audit deadlines"
            onChange={event => { setTitle(event.target.value); setError(""); }} />
        </label>
        <button type="submit" disabled={working || saved.isLoading || rows.length >= 20 || title.trim().length < 2}>
          {create.isPending ? "Saving…" : "Save view"}
        </button>
      </form>
    </div>
    {saved.isError && <p className="qms-inbox__notice" role="alert">
      Saved filters could not be loaded. <button type="button" onClick={() => void saved.refetch()}>Retry</button>
    </p>}
    {error && <p className="qms-inbox__notice" role="alert">{error}</p>}
    {notice && <p className="qms-saved-views__feedback" role="status">{notice}</p>}
  </section>;
}
