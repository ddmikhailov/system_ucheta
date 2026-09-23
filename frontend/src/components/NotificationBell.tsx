import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { NotificationItem } from "../api/types";

const POLL_MS = 60_000;

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function NotificationBell() {
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);

  function refreshCount() {
    api.get<{ unread: number }>("/notifications/unread-count").then((r) => setUnread(r.unread)).catch(() => {});
  }

  useEffect(() => {
    refreshCount();
    const id = setInterval(refreshCount, POLL_MS);
    return () => clearInterval(id);
  }, []);

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next) {
      api.get<NotificationItem[]>("/notifications").then(setItems).catch(() => {});
    }
  }

  async function markAllRead() {
    await api.post("/notifications/read-all");
    setItems((prev) => prev.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })));
    setUnread(0);
  }

  async function markRead(id: number) {
    await api.post(`/notifications/${id}/read`);
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
    refreshCount();
  }

  return (
    <div className="notification-bell">
      <button className="notification-bell__toggle" onClick={toggleOpen} title="Уведомления">
        🔔{unread > 0 && <span className="notification-bell__badge">{unread}</span>}
      </button>

      {open && (
        <div className="notification-bell__panel">
          <div className="notification-bell__header">
            <b>Уведомления</b>
            {unread > 0 && (
              <button className="link-btn" onClick={markAllRead}>
                Прочитать все
              </button>
            )}
          </div>
          {items.length === 0 && <p className="notification-bell__empty">Уведомлений нет.</p>}
          <ul className="notification-bell__list">
            {items.map((n) => (
              <li
                key={n.id}
                className={n.read_at ? "read" : "unread"}
                onClick={() => !n.read_at && markRead(n.id)}
              >
                <span>{n.message}</span>
                <time>{formatDateTime(n.created_at)}</time>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
