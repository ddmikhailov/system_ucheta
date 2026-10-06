import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError, downloadFile } from "../api/client";
import type { CuratorReport } from "../api/types";
import SearchSelect from "../components/SearchSelect";
import { formatDateRu } from "../utils/date";

interface GroupOption {
  id: number;
  code: string;
  course: number;
}

// Отчёт куратора за семестр: платформа насчитывает то, что знает (студенты, пропуски, собрания, мероприятия), а то,
// чего у неё нет (ИУП, задолженности, стипендии, ВКУ…), куратор вносит здесь один раз — цифры хранятся по семестрам.
// Выгрузка — в Word по бланку колледжа: внесённое важнее посчитанного.
export default function ReportPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [groups, setGroups] = useState<GroupOption[] | null>(null);
  const [report, setReport] = useState<CuratorReport | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const groupId = searchParams.get("group");
  const year = searchParams.get("year");
  const semester = searchParams.get("semester");

  useEffect(() => {
    api
      .get<GroupOption[]>("/individual-work/groups")
      .then((list) => {
        setGroups(list);
        if (!groupId && list.length > 0) setSearchParams({ group: String(list[0].id) }, { replace: true });
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить список групп");
        setGroups([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const query = `${year ? `year=${year}` : ""}${year && semester ? "&" : ""}${semester ? `semester=${semester}` : ""}`;

  const load = useCallback(() => {
    if (!groupId) return;
    api
      .get<CuratorReport>(`/reports/groups/${groupId}${query ? `?${query}` : ""}`)
      .then((r) => {
        const stored: Record<string, string> = {};
        for (const s of r.sections) for (const f of s.fields) if (f.value) stored[f.key] = f.value;
        setReport(r);
        setValues(stored);
        setSaved(stored);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить отчёт"));
  }, [groupId, query]);

  useEffect(load, [load]);

  const dirty = JSON.stringify(values) !== JSON.stringify(saved);

  async function save(): Promise<boolean> {
    if (!report) return false;
    setBusy(true);
    setError(null);
    try {
      await api.put<CuratorReport>(`/reports/groups/${report.group_id}?year=${report.school_year}&semester=${report.semester}`, { values });
      setSaved(values);
      setNotice("Сохранено");
      load();
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить отчёт");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function exportWord() {
    if (!report) return;
    if (dirty && report.can_edit && !(await save())) return;
    downloadFile(
      `/reports/groups/${report.group_id}/report.docx?year=${report.school_year}&semester=${report.semester}`,
      `Отчёт_куратора_${report.group_code}_${report.semester}_семестр.docx`,
    ).catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось сформировать отчёт"));
  }

  if (groups === null) return <p className="hint">Загрузка…</p>;
  if (groups.length === 0) return <p>{error ?? "Нет доступных групп."}</p>;

  const current = report && String(report.group_id) === groupId ? report : null;

  return (
    <div>
      <div className="toolbar">
        <SearchSelect
          value={groupId ?? ""}
          options={groups.map((g) => ({ value: String(g.id), label: `${g.code} (курс ${g.course})` }))}
          onChange={(v) => setSearchParams({ group: v })}
          ariaLabel="Группа"
          title="Группа: начните вводить код, например «ГД»"
        />
        {current && (
          <>
            <select
              aria-label="Учебный год"
              value={current.school_year}
              onChange={(e) => setSearchParams({ group: String(current.group_id), year: e.target.value, semester: String(current.semester) })}
            >
              {current.years.map((y) => (
                <option key={y} value={y}>
                  {y.replace("-", "/")} уч. год
                </option>
              ))}
            </select>
            <select
              aria-label="Семестр"
              value={current.semester}
              onChange={(e) => setSearchParams({ group: String(current.group_id), year: current.school_year, semester: e.target.value })}
            >
              <option value={1}>1 семестр</option>
              <option value={2}>2 семестр</option>
            </select>
          </>
        )}
      </div>
      {error && <div className="error-text">{error}</div>}
      {notice && !error && !dirty && <p className="hint" aria-live="polite">{notice}</p>}
      {!current ? (
        !error && <p className="hint">Загрузка…</p>
      ) : (
        <>
          <p className="hint">
            Период: {formatDateRu(current.period_from)} — {formatDateRu(current.period_to)}. Серым показано, что насчитала платформа:
            нажмите «Взять», если согласны, или впишите своё. Что не заполнено, в Word остаётся пустым для записи от руки.
          </p>
          <div className="toolbar">
            {current.can_edit && (
              <button type="button" onClick={save} disabled={busy || !dirty}>
                Сохранить
              </button>
            )}
            <button type="button" className="link-btn" onClick={exportWord} title="Отчёт куратора — бланк колледжа">
              Отчёт в Word
            </button>
          </div>
          {current.sections.map((section) => (
            <section key={section.key} className="report-section">
              <h3 className="student-card__section">{section.title}</h3>
              <div className="report-fields">
                {section.fields.map((f) => {
                  const value = values[f.key] ?? "";
                  const id = `report-${f.key}`;
                  return (
                    <div key={f.key} className="report-field">
                      <label htmlFor={id}>{f.label}</label>
                      {f.long ? (
                        <textarea id={id} rows={2} value={value} maxLength={2000} disabled={!current.can_edit} placeholder={f.auto ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                      ) : (
                        <input id={id} value={value} maxLength={2000} disabled={!current.can_edit} placeholder={f.auto ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                      )}
                      {(f.auto || f.hint) && (
                        <div className="hint">
                          {f.auto && (
                            <>
                              По платформе: <b>{f.auto}</b>{" "}
                              {current.can_edit && value !== f.auto && (
                                <button type="button" className="link-btn" aria-label={`Взять посчитанное: ${f.label}`} onClick={() => setValues({ ...values, [f.key]: f.auto ?? "" })}>
                                  Взять
                                </button>
                              )}{" "}
                            </>
                          )}
                          {f.hint}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
