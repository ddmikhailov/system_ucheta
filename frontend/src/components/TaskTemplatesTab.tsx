import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { COLLECT_MODE_LABELS, REPEAT_LABELS, scheduleText } from "../constants/tasks";
import { formatDateRu } from "../utils/date";
import type { TaskTemplate } from "../api/types";

// Шаблоны задач и их расписание: очередная задача создаётся при открытии платформы после даты запуска.
export default function TaskTemplatesTab() {
  const [templates, setTemplates] = useState<TaskTemplate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);

  const load = useCallback(() => {
    api
      .get<TaskTemplate[]>("/tasks/templates")
      .then((rows) => {
        setTemplates(rows);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить шаблоны"));
  }, []);

  useEffect(load, [load]);

  async function remove(t: TaskTemplate) {
    if (!window.confirm(`Удалить шаблон «${t.name}»? Созданные по нему задачи не изменятся, повторный запуск прекратится.`)) return;
    try {
      await api.delete(`/tasks/templates/${t.id}`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить шаблон");
    }
  }

  return (
    <div>
      <p className="hint">
        Шаблон создаётся из карточки любой задачи («Сохранить как шаблон»). Здесь можно настроить повторный запуск: новая задача
        появится сама, когда после даты запуска кто-нибудь откроет платформу; если платформу не открывали несколько месяцев,
        создаётся одна актуальная задача, а не все пропущенные.
      </p>
      {error && <div className="error-text">{error}</div>}
      {templates === null ? (
        <p className="hint">Загрузка…</p>
      ) : templates.length === 0 ? (
        <p className="hint">Шаблонов пока нет.</p>
      ) : (
        <table className="dash-table roster-table">
          <thead>
            <tr>
              <th>Шаблон</th>
              <th>Расписание</th>
              <th>Следующий запуск</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {templates.map((t) => (
              <tr key={t.id}>
                <td data-label="Шаблон">
                  {t.name}
                  <br />
                  <span className="hint">
                    {COLLECT_MODE_LABELS[t.collect_mode]} · автор: {t.author_name ?? "—"}
                  </span>
                </td>
                <td data-label="Расписание">
                  {scheduleText(t)}
                  {t.last_error && (
                    <>
                      <br />
                      <span className="error-text">Последний запуск пропущен: {t.last_error}</span>
                    </>
                  )}
                </td>
                <td data-label="Следующий запуск">{t.next_run ? formatDateRu(t.next_run) : "—"}</td>
                <td>
                  {t.can_manage && (
                    <>
                      <button className="link-btn" onClick={() => setEditing(editing === t.id ? null : t.id)}>
                        Расписание
                      </button>
                      {" · "}
                      <button className="link-btn" onClick={() => remove(t)}>
                        Удалить
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {editing !== null && templates?.find((t) => t.id === editing) && (
        <ScheduleForm
          template={templates.find((t) => t.id === editing)!}
          onSaved={() => {
            setEditing(null);
            load();
          }}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function ScheduleForm({ template, onSaved, onCancel }: { template: TaskTemplate; onSaved: () => void; onCancel: () => void }) {
  const [repeat, setRepeat] = useState(template.repeat);
  const [day, setDay] = useState(String(template.repeat_day));
  const [offset, setOffset] = useState(String(template.due_offset_days));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await api.put(`/tasks/templates/${template.id}/schedule`, {
        repeat,
        repeat_day: Number(day),
        due_offset_days: Number(offset),
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить расписание");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="add-block">
      <p className="add-block__title">Расписание: {template.name}</p>
      {error && <div className="error-text">{error}</div>}
      <div className="inline-form">
        <select value={repeat} onChange={(e) => setRepeat(e.target.value as TaskTemplate["repeat"])} aria-label="Повторять">
          {Object.entries(REPEAT_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        {repeat !== "" && (
          <>
            <label>
              Число месяца{" "}
              <input type="number" min={1} max={28} value={day} onChange={(e) => setDay(e.target.value)} style={{ width: 70 }} />
            </label>
            <label>
              Срок через, дн.{" "}
              <input type="number" min={1} max={120} value={offset} onChange={(e) => setOffset(e.target.value)} style={{ width: 70 }} />
            </label>
          </>
        )}
      </div>
      <p className="hint">
        Задача создаётся от имени автора шаблона и с его правами на охват. К названию добавляется период («— Октябрь 2026»).
      </p>
      <div className="actions">
        <button onClick={onCancel}>Отмена</button>
        <button onClick={save} disabled={busy}>
          Сохранить
        </button>
      </div>
    </div>
  );
}
