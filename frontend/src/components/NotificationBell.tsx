import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { NotificationItem } from "../api/types";

const POLL_MS = 60_000;
const MANAGEMENT_ROLES = ["dept_head", "edu_department", "admin", "tutor"];

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function NotificationBell() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onOutsideClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [open]);

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

  // Раньше клик по уведомлению никуда не вёл (см. TODO.md 4) — уведомление о
  // позднем редактировании несёт entity_id "groupId:date", открываем на нём
  // журнал группы (у управленцев — в админке, у куратора — в его кабинете).
  function openNotification(n: NotificationItem) {
    if (!n.read_at) markRead(n.id);
    if (n.entity_type === "study_group_day" && n.entity_id) {
      const [groupId, date] = n.entity_id.split(":");
      if (user && MANAGEMENT_ROLES.includes(user.role)) {
        navigate(`/admin?tab=journal&group=${groupId}&date=${date}`);
      } else {
        navigate(`/cabinet?group=${groupId}&date=${date}`);
      }
      setOpen(false);
    }
  }

  return (
    <div className="notification-bell" ref={panelRef}>
      <button className="notification-bell__toggle" onClick={toggleOpen} title="Уведомления" aria-label="Уведомления">
        🔔{unread > 0 && <span className="notification-bell__badge">{unread}</span>}
      </button>

      {open && (
        <div className="notification-bell__panel" role="dialog" aria-label="Уведомления">
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
                onClick={() => openNotification(n)}
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
