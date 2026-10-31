import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { GroupPractice, GroupPractices } from "../api/types";
import { useApi } from "../hooks/useApi";
import { formatDateRu } from "../utils/date";
import { dialogs } from "../utils/feedback";
import PracticeForm from "./PracticeForm";
import { PRACTICE_STATE_LABEL } from "./practice";

/** Вкладка «Практика» в группе (п. 3.1.17 положения): периоды практики, база, руководители, получение характеристики.
 * Платформа сама ставит студентам группы отметку «р»; на восполнение пропусков и группу риска она не влияет. */
export default function PracticePanel({ groupId }: { groupId: number }) {
  const { data, error, loading, reload } = useApi<GroupPractices>(`/practice/groups/${groupId}`, "Не удалось загрузить практику");
  const [form, setForm] = useState<{ practice: GroupPractice | null } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function remove(p: GroupPractice) {
    const ok = await dialogs.confirm(`Удалить практику ${formatDateRu(p.date_from)} — ${formatDateRu(p.date_to)}? Отметки «р» за этот период тоже уберутся.`, {
      confirmLabel: "Удалить", danger: true,
    });
    if (!ok) return;
    try {
      await api.delete(`/practice/${p.id}`);
      setNotice(null);
      reload();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Не удалось удалить практику");
    }
  }

  return (
    <section className="plan-section">
      <h3 className="student-card__section">
        Практика группы <span className="hint">({data?.practices.length ?? 0})</span>
      </h3>
      {error && <div className="error-text">{error}</div>}
      {actionError && <div className="error-text">{actionError}</div>}
      {notice && <p className="hint">{notice}</p>}
      {loading && !data && <p className="hint">Загрузка…</p>}
      {data && data.practices.length === 0 && <p className="hint">Практика ещё не внесена.</p>}
      {data && data.practices.length > 0 && (
        <div className="table-scroll">
          <table className="dash-table roster-table">
            <thead>
              <tr>
                <th>Период</th>
                <th>База</th>
                <th>Руководители</th>
                <th>Характеристика</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.practices.map((p) => (
                <tr key={p.id}>
                  <td data-label="Период">
                    {formatDateRu(p.date_from)} — {formatDateRu(p.date_to)}
                    <div className="hint">{p.kind_name}</div>
                    {p.state && <span className={p.state === "no_review" ? "risk-badge" : "compensate-badge"}>{PRACTICE_STATE_LABEL[p.state]}</span>}
                  </td>
                  <td data-label="База">{p.base ?? "—"}</td>
                  <td data-label="Руководители">
                    {p.college_supervisor && <div>Колледж: {p.college_supervisor}</div>}
                    {p.base_supervisor && <div>База: {p.base_supervisor}</div>}
                    {p.phone && <div className="hint">{p.phone}</div>}
                    {!p.college_supervisor && !p.base_supervisor && !p.phone && "—"}
                  </td>
                  <td data-label="Характеристика">
                    {p.review_received ? `Получена${p.review_received_on ? ` ${formatDateRu(p.review_received_on)}` : ""}` : "Не получена"}
                  </td>
                  <td data-label="Действия">
                    {data.can_edit && (
                      <>
                        <button type="button" className="link-btn" onClick={() => setForm({ practice: p })}>
                          Изменить
                        </button>{" "}
                        <button type="button" className="link-btn" onClick={() => remove(p)}>
                          Удалить практику
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data?.can_edit && (
        <p>
          <button type="button" className="link-btn" onClick={() => setForm({ practice: null })}>
            + Добавить практику
          </button>
        </p>
      )}
      {form && (
        <PracticeForm
          groupId={groupId}
          practice={form.practice}
          onSaved={(replaced) => {
            setForm(null);
            setActionError(null);
            setNotice(replaced > 0 ? `Практика сохранена. Отметок, которые она заменила: ${replaced}.` : "Практика сохранена.");
            reload();
          }}
          onClose={() => setForm(null)}
        />
      )}
    </section>
  );
}
