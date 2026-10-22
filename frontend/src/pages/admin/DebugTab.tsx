import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { AuditEntry, AuditPage, UserAdmin } from "../../api/types";
import { AUDIT_AREAS, auditActionLabel } from "../../constants/auditActions";
import { ROLE_LABELS, type RoleCode } from "../../constants/roles";
import { formatServerDateTimeFull } from "../../utils/date";

interface Filters {
  user_id: string;
  area: string;
  entity_type: string;
  entity_id: string;
  date_from: string;
  date_to: string;
}

const EMPTY: Filters = { user_id: "", area: "", entity_type: "", entity_id: "", date_from: "", date_to: "" };

function entityLink(e: AuditEntry): string | null {
  if (e.entity_type === "student") return `/students/${e.entity_id}`;
  if (e.entity_type === "task_assignment") return `/tasks/assignment/${e.entity_id}`;
  if (e.entity_type === "user") return `/admin/users/${e.entity_id}`;
  return null;
}

function Value({ value }: { value: string | null }) {
  if (value === null || value === "") return <span className="hint">—</span>;
  return <span className="debug-log__value">{value}</span>;
}

/** «Отладка»: полный журнал действий всех пользователей — кто, когда, что сделал и что было/стало, чтобы
 * разобраться, что привело к результату. Только администратор; журнал запрашивается лишь при открытии
 * этой вкладки (и при «Показать»/«Показать ещё»), каждый просмотр сервер пишет в тот же журнал. */
export default function DebugTab() {
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [users, setUsers] = useState<UserAdmin[]>([]);
  const [items, setItems] = useState<AuditEntry[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback(
    (before: number | null) => {
      const qs = new URLSearchParams({ limit: "100" });
      for (const [key, value] of Object.entries(filters)) if (value.trim()) qs.set(key, value.trim());
      if (before !== null) qs.set("before_id", String(before));
      return api.get<AuditPage>(`/admin/debug/audit?${qs}`);
    },
    [filters]
  );
  const fail = (err: unknown) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить журнал");

  useEffect(() => {
    let cancelled = false;
    api
      .get<UserAdmin[]>("/admin/users")
      .then((list) => {
        if (!cancelled) setUsers([...list].sort((a, b) => a.full_name.localeCompare(b.full_name, "ru")));
      })
      .catch(() => undefined); // без списка фильтр по человеку недоступен, журнал работает
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    request(null)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setNext(page.next_before_id);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      });
    return () => {
      cancelled = true;
    };
  }, [request]);

  function apply(e: FormEvent) {
    e.preventDefault();
    setItems(null);
    setFilters({ ...draft });
  }

  function reset() {
    setDraft(EMPTY);
    setItems(null);
    setFilters(EMPTY);
  }

  function loadMore() {
    if (next === null) return;
    setBusy(true);
    request(next)
      .then((page) => {
        setItems((prev) => [...(prev ?? []), ...page.items]);
        setNext(page.next_before_id);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }

  const set = (key: keyof Filters) => (e: { target: { value: string } }) => setDraft((d) => ({ ...d, [key]: e.target.value }));

  return (
    <div className="debug-log">
      <p className="hint">
        Полный журнал действий всех пользователей за последний год: кто, когда и что сделал, что было и что стало.
        Загружается только здесь; каждый просмотр тоже записывается в журнал.
      </p>
      <form className="toolbar debug-log__filters" onSubmit={apply}>
        <label className="form-field">
          Кто
          <select value={draft.user_id} onChange={set("user_id")}>
            <option value="">Все</option>
            {users.map((u) => (
              <option key={u.id} value={String(u.id)}>
                {u.full_name}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          Что
          <select value={draft.area} onChange={set("area")}>
            {AUDIT_AREAS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="form-field">
          Объект
          <input value={draft.entity_type} onChange={set("entity_type")} placeholder="student, study_group…" maxLength={64} />
        </label>
        <label className="form-field">
          Номер объекта
          <input value={draft.entity_id} onChange={set("entity_id")} maxLength={64} />
        </label>
        <label className="form-field">
          С
          <input type="date" value={draft.date_from} onChange={set("date_from")} />
        </label>
        <label className="form-field">
          По
          <input type="date" value={draft.date_to} onChange={set("date_to")} />
        </label>
        <div className="debug-log__buttons">
          <button type="submit" className="btn-primary">
            Показать
          </button>
          <button type="button" className="btn-secondary" onClick={reset}>
            Сбросить
          </button>
        </div>
      </form>

      {error && <div className="error-text">{error}</div>}
      {items === null ? (
        !error && <p className="hint">Загрузка…</p>
      ) : items.length === 0 ? (
        <p className="hint">Записей нет.</p>
      ) : (
        <table className="roster-table debug-log__table">
          <thead>
            <tr>
              <th>Когда</th>
              <th>Кто</th>
              <th>Действие</th>
              <th>Объект</th>
              <th>Было</th>
              <th>Стало</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e) => {
              const link = entityLink(e);
              return (
                <tr key={e.id}>
                  <td data-label="Когда">{formatServerDateTimeFull(e.created_at)}</td>
                  <td data-label="Кто">
                    {e.user_id === null ? (
                      <span className="hint">система</span>
                    ) : (
                      <>
                        <Link className="link-btn" to={`/admin/users/${e.user_id}`}>
                          {e.user_name ?? `№${e.user_id}`}
                        </Link>
                        {e.user_role && <span className="hint"> · {ROLE_LABELS[e.user_role as RoleCode] ?? e.user_role}</span>}
                      </>
                    )}
                  </td>
                  <td data-label="Действие">
                    {auditActionLabel(e.action)}
                    <span className="hint debug-log__code"> {e.action}</span>
                  </td>
                  <td data-label="Объект">
                    {link ? (
                      <Link className="link-btn" to={link}>
                        {e.entity_type} №{e.entity_id}
                      </Link>
                    ) : (
                      `${e.entity_type} ${e.entity_id}`
                    )}
                  </td>
                  <td data-label="Было">
                    <Value value={e.old_value} />
                  </td>
                  <td data-label="Стало">
                    <Value value={e.new_value} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {next !== null && (
        <button type="button" className="btn-secondary" disabled={busy} onClick={loadMore}>
          {busy ? "Загрузка…" : "Показать ещё"}
        </button>
      )}
    </div>
  );
}
