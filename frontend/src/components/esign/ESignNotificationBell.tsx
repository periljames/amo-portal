import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import InlineLoader from "../loading/InlineLoader";
import {
  dismissESignNotification,
  fetchESignNotificationCount,
  fetchESignNotifications,
  markESignNotificationRead,
} from "../../services/esign";
import type { ESignNotification } from "../../types/esign";
import { resolveNotificationLinkPath, unreadCountFromNotifications } from "./notificationState";

const ESignNotificationBell: React.FC = () => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ESignNotification[]>([]);

  const refreshCount = async () => {
    try {
      const out = await fetchESignNotificationCount();
      setCount(out.unread_count);
    } catch {
      setCount(0);
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const rows = await fetchESignNotifications(false);
      setItems(rows);
      setCount(unreadCountFromNotifications(rows));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshCount();
  }, []);

  return (
    <div className="esign-notification-menu">
      <button type="button" className="notification-bell" aria-label="E-Sign notifications" onClick={() => { setOpen((v) => !v); void load(); }}>
        <span className="notification-bell__icon">🔔</span>
        {count > 0 ? <span className="notification-bell__badge">{count}</span> : null}
      </button>
      {open ? (
        <div className="notification-panel notification-panel--drawer esign-notification-drawer">
          <div className="notification-panel__header">
            <strong>E-Sign notifications</strong>
            <span className="text-muted">{count} unread</span>
          </div>
          {loading ? <div className="notification-panel__state"><InlineLoader label="Loading" /></div> : null}
          {!loading && !items.length ? <div className="notification-panel__state">No notifications.</div> : null}
          {!loading ? (
            <div className="notification-panel__list">
              {items.map((note) => (
                <div key={note.id} className={`notification-item${note.read_at ? "" : " notification-item--unread"}`}>
                  <div className="notification-item__title">{note.title}</div>
                  {note.body ? <div className="notification-item__body">{note.body}</div> : null}
                  <div className="notification-item__meta">
                    <span>{new Date(note.created_at).toLocaleString()}</span>
                  </div>
                  <div className="loader-passkey-actions">
                    <button
                      type="button"
                      onClick={async () => {
                        if (!note.read_at) {
                          await markESignNotificationRead(note.id);
                        }
                        setOpen(false);
                        await refreshCount();
                        navigate(resolveNotificationLinkPath(note, "/"));
                      }}
                    >
                      View
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        await dismissESignNotification(note.id);
                        await load();
                        await refreshCount();
                      }}
                    >
                      Dismiss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
};

export default ESignNotificationBell;
