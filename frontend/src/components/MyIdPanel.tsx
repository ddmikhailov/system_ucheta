import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { MyIdData, MyIdRow } from "../api/types";
import { useGroupParams } from "../hooks/useGroupParams";
import SearchSelect from "./SearchSelect";

type Check = "biometrics" | "max_student" | "max_parent";

const CHECKS: { key: Check; reason: "biometrics_reason" | "max_student_reason" | "max_parent_reason"; label: string; reasonLabel: string }[] = [
  { key: "biometrics", reason: "biometrics_reason", label: "Биометрия «Мой.ID»", reasonLabel: "Причина отсутствия биометрии" },
  { key: "max_student", reason: "max_student_reason", label: "Студент в чате MAX", reasonLabel: "Причина: нет MAX у студента" },
  { key: "max_parent", reason: "max_parent_reason", label: "Родитель в чате MAX", reasonLabel: "Причина: нет MAX у родителя" },
];

interface GroupOption {
  id: number;
  code: string;
  course: number;
}

/** «Мой ID»: у каждого студента — зарегистрирована ли биометрия «Мой.ID», есть ли он сам и его родитель в чатах MAX,
 * и причина, если нет. Заполняется вручную; сохраняются только изменённые строки. `fixedGroupId` — вкладка на странице
 * группы куратора (выбора группы нет); без него — отдельный раздел меню с выбором группы, как «План группы» и «Отчёт». */
export default function MyIdPanel({ fixedGroupId }: { fixedGroupId?: number } = {}) {
  const { groupId, update } = useGroupParams(fixedGroupId);
  const [groups, setGroups] = useState<GroupOption[] | null>(null);
  const [data, setData] = useState<MyIdData | null>(null);
  const [draft, setDraft] = useState<Record<number, MyIdRow>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (fixedGroupId != null) {
      setGroups([]);
      return;
    }
    api
      .get<GroupOption[]>("/individual-work/groups")
      .then((list) => {
        setGroups(list);
        if (!groupId && list.length > 0) update({ group: String(list[0].id) }, { replace: true });
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить список групп");
        setGroups([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(() => {
    if (!groupId) return;
    api
      .get<MyIdData>(`/my-id/groups/${groupId}`)
      .then((d) => {
        setData(d);
        setDraft({});
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить данные «Мой ID»"));
  }, [groupId]);

  useEffect(load, [load]);

  if (groups === null) return <p className="hint">Загрузка…</p>;
  if (fixedGroupId == null && groups.length === 0) return <p>{error ?? "Нет доступных групп."}</p>;

  const current = data && String(data.group_id) === groupId ? data : null;
  const rowOf = (r: MyIdRow): MyIdRow => draft[r.student_id] ?? r;
  const dirtyIds = Object.keys(draft).map(Number);

  function change(base: MyIdRow, patch: Partial<MyIdRow>) {
    setNotice(null);
    setDraft((d) => ({ ...d, [base.student_id]: { ...(d[base.student_id] ?? base), ...patch } }));
  }

  async function save() {
    if (!current || dirtyIds.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const rows = dirtyIds.map((id) => {
        const r = draft[id];
        return {
          student_id: id, biometrics: r.biometrics, biometrics_reason: r.biometrics_reason, max_student: r.max_student,
          max_student_reason: r.max_student_reason, max_parent: r.max_parent, max_parent_reason: r.max_parent_reason,
        };
      });
      const saved = await api.put<MyIdData>(`/my-id/groups/${current.group_id}`, { rows });
      setData(saved);
      setDraft({});
      setNotice("Сохранено");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  }

  const live = current ? current.rows.map(rowOf) : [];
  const total = live.length;
  const yes = (k: Check) => live.filter((r) => r[k] === true).length;
  const no = (k: Check) => live.filter((r) => r[k] === false).length;

  return (
    <div>
      <div className="toolbar">
        {fixedGroupId == null && (
          <SearchSelect
            value={groupId ?? ""}
            options={groups.map((g) => ({ value: String(g.id), label: `${g.code} (курс ${g.course})` }))}
            onChange={(v) => {
              if (dirtyIds.length > 0) setDraft({});
              update({ group: v });
            }}
            ariaLabel="Группа"
            title="Группа: начните вводить код, например «ГД»"
          />
        )}
        {current?.can_edit && (
          <button type="button" onClick={save} disabled={busy || dirtyIds.length === 0}>
            Сохранить{dirtyIds.length > 0 ? ` (${dirtyIds.length})` : ""}
          </button>
        )}
      </div>
      {error && <div className="error-text">{error}</div>}
      {notice && !error && dirtyIds.length === 0 && (
        <p className="hint" aria-live="polite">
          {notice}
        </p>
      )}
      <p className="hint">
        Отметьте «Да» или «Нет»: зарегистрирована ли биометрия «Мой.ID» и состоят ли студент и его родитель в чатах MAX.
        После «Нет» появится поле причины. Сохранённый ответ исправить нельзя.
      </p>
      {!current ? (
        !error && <p className="hint">Загрузка…</p>
      ) : total === 0 ? (
        <p className="hint">В группе {current.group_code} нет студентов.</p>
      ) : (
        <>
          <p className="my-id-summary" aria-live="polite">
            <span>
              Численность в группе: <b>{total}</b>
            </span>
            <span>
              Биометрия зарегистрирована: <b>{yes("biometrics")}</b> из {total}
            </span>
            <span>
              Не зарегистрированы: <b>{total - yes("biometrics")}</b>
            </span>
          </p>
          <div className="table-scroll">
            <table className="dash-table roster-table compact-cards">
              <thead>
                <tr>
                  <th>№</th>
                  <th>Студент</th>
                  {CHECKS.map((c) => (
                    <th key={c.key}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {current.rows.map((base, i) => {
                  const r = rowOf(base);
                  return (
                    <tr key={base.student_id} className={draft[base.student_id] ? "row-dirty" : ""}>
                      <td data-label="№">{i + 1}</td>
                      <td data-label="Студент">{base.full_name}</td>
                      {CHECKS.map((c) => (
                        <MyIdCell
                          key={c.key}
                          name={base.full_name}
                          check={c}
                          row={r}
                          locked={base[c.key] !== null}
                          disabled={!current.can_edit}
                          onChange={(patch) => change(base, patch)}
                        />
                      ))}
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={2}>Итого</td>
                  {CHECKS.map((c) => (
                    <td key={c.key}>
                      Да: <b>{yes(c.key)}</b> · Нет: <b>{no(c.key)}</b>
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/** Ячейка показателя: две кнопки «Да» / «Нет» (пока ответа нет — обе неактивны) и, только после «Нет», поле причины
 * (пустое — поле для ввода). Сохранённый ответ исправить нельзя — кнопки блокируются; причину при «Нет» дописать можно. */
function MyIdCell({
  name, check, row, locked, disabled, onChange,
}: {
  name: string;
  check: (typeof CHECKS)[number];
  row: MyIdRow;
  locked: boolean;
  disabled: boolean;
  onChange: (patch: Partial<MyIdRow>) => void;
}) {
  const value = row[check.key];
  return (
    <td data-label={check.label} className="my-id-cell">
      <div className="my-id-cell__body">
      <div className="yesno" role="group" aria-label={`${check.label}: ${name}`}>
        <button
          type="button"
          className={`yesno__btn yesno__btn--yes${value === true ? " is-active" : ""}`}
          aria-pressed={value === true}
          disabled={disabled || locked}
          onClick={() => onChange({ [check.key]: true, [check.reason]: null } as Partial<MyIdRow>)}
        >
          Да
        </button>
        <button
          type="button"
          className={`yesno__btn yesno__btn--no${value === false ? " is-active" : ""}`}
          aria-pressed={value === false}
          disabled={disabled || locked}
          onClick={() => onChange({ [check.key]: false } as Partial<MyIdRow>)}
        >
          Нет
        </button>
      </div>
      {value === false && (
        <input
          className="my-id-reason"
          aria-label={`${check.reasonLabel}: ${name}`}
          placeholder="Причина"
          value={row[check.reason] ?? ""}
          maxLength={255}
          disabled={disabled}
          onChange={(e) => onChange({ [check.reason]: e.target.value } as Partial<MyIdRow>)}
        />
      )}
      </div>
    </td>
  );
}
