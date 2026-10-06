import { useCallback, useEffect, useState } from "react";
import { useGroupParams } from "../hooks/useGroupParams";
import { TabBar, TabPanel } from "../components/Tabs";
import { api, ApiError, downloadFile } from "../api/client";
import type { CuratorReport } from "../api/types";
import SearchSelect from "../components/SearchSelect";
import { formatDateRu } from "../utils/date";
import TextArea from "../components/TextArea";

interface GroupOption {
  id: number;
  code: string;
  course: number;
}

// Отчёт куратора за семестр: платформа насчитывает то, что знает (студенты, пропуски, собрания, мероприятия), а то,
// чего у неё нет (ИУП, задолженности, стипендии, ВКУ…), куратор вносит здесь один раз — цифры хранятся по семестрам.
// Выгрузка — в Word по бланку колледжа: внесённое важнее посчитанного.
// `fixedGroupId` — вкладка на странице группы куратора: группа задана, выбора группы нет.
export default function ReportPage({ fixedGroupId }: { fixedGroupId?: number } = {}) {
  const { params: searchParams, groupId, update } = useGroupParams(fixedGroupId);
  const [groups, setGroups] = useState<GroupOption[] | null>(null);
  const [report, setReport] = useState<CuratorReport | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const year = searchParams.get("year");
  const semester = searchParams.get("semester");
  // Раздел бланка — подвкладка (их шесть, одной лентой страница была очень длинной).
  const rawSection = searchParams.get("part");
  const setSection = (key: string) => update({ part: key }, { replace: true });

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
  if (fixedGroupId == null && groups.length === 0) return <p>{error ?? "Нет доступных групп."}</p>;

  const current = report && String(report.group_id) === groupId ? report : null;
  const sectionKeys = current?.sections.map((s) => s.key) ?? [];
  const sectionKey = sectionKeys.includes(rawSection ?? "") ? rawSection! : (sectionKeys[0] ?? "");

  return (
    <div>
      <div className="toolbar">
        {fixedGroupId == null && (
          <SearchSelect
            value={groupId ?? ""}
            options={groups.map((g) => ({ value: String(g.id), label: `${g.code} (курс ${g.course})` }))}
            onChange={(v) => update({ group: v, year: null, semester: null })}
            ariaLabel="Группа"
            title="Группа: начните вводить код, например «ГД»"
          />
        )}
        {current && (
          <>
            <select
              aria-label="Учебный год"
              value={current.school_year}
              onChange={(e) => update({ year: e.target.value, semester: String(current.semester) })}
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
              onChange={(e) => update({ year: current.school_year, semester: e.target.value })}
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
          <TabBar
            tabs={current.sections.map((sec, i) => {
              const filled = sec.fields.filter((f) => (values[f.key] ?? "").trim()).length;
              return { key: sec.key, label: `${i + 1}. ${sec.title}`, badge: `${filled}/${sec.fields.length}` };
            })}
            active={sectionKey}
            onChange={setSection}
            label="Разделы отчёта"
            idPrefix="report"
            variant="sub"
          />
          {current.sections.map((section, index) => {
            const filled = section.fields.filter((f) => (values[f.key] ?? "").trim()).length;
            const next = current.sections[index + 1];
            return (
              <TabPanel key={section.key} idPrefix="report" tabKey={section.key} active={sectionKey}>
                <section className="dossier-section report-section">
                  <header className="dossier-section__head report-section__head">
                    <div>
                      <h4>
                        {index + 1}. {section.title}
                      </h4>
                      <p>
                        Заполнено {filled} из {section.fields.length}
                      </p>
                    </div>
                  </header>
                  <div className="report-grid">
                    {section.fields.map((f) => {
                      const value = values[f.key] ?? "";
                      const id = `report-${f.key}`;
                      const canTake = current.can_edit && !!f.auto && value !== f.auto;
                      return (
                        <div key={f.key} className={`report-card${f.long ? " report-card--wide" : ""}${value.trim() ? " is-filled" : ""}`}>
                          <label htmlFor={id} className="report-card__label">
                            {f.label}
                          </label>
                          {f.long ? (
                            <TextArea
                              id={id}
                              expandTitle={f.label}
                              rows={2}
                              value={value}
                              maxLength={2000}
                              disabled={!current.can_edit}
                              placeholder={f.auto ? `По платформе: ${f.auto}` : "Впишите или оставьте пустым"}
                              onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                            />
                          ) : (
                            <input
                              id={id}
                              value={value}
                              maxLength={2000}
                              disabled={!current.can_edit}
                              placeholder={f.auto ? `По платформе: ${f.auto}` : "—"}
                              onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
                            />
                          )}
                          {(f.auto || f.hint) && (
                            <div className="report-card__foot">
                              {f.auto && (
                                <span className="report-card__auto">
                                  По платформе: <b>{f.auto}</b>
                                </span>
                              )}
                              {canTake && (
                                <button
                                  type="button"
                                  className="report-card__take"
                                  aria-label={`Взять посчитанное: ${f.label}`}
                                  onClick={() => setValues({ ...values, [f.key]: f.auto ?? "" })}
                                >
                                  Взять
                                </button>
                              )}
                              {f.hint && <span className="report-card__hint">{f.hint}</span>}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {next && (
                    <div className="report-section__next">
                      <button type="button" className="btn-secondary" onClick={() => setSection(next.key)}>
                        Следующий раздел: {next.title} →
                      </button>
                    </div>
                  )}
                </section>
              </TabPanel>
            );
          })}
          <div className={`dossier-savebar${dirty ? " is-dirty" : ""}`}>
            <span className="dossier-savebar__state" aria-live="polite">
              {current.can_edit ? (dirty ? "Есть несохранённые изменения" : "Все изменения сохранены") : "Только просмотр"}
            </span>
            <span className="report-savebar__buttons">
              <button type="button" className="btn-secondary" onClick={exportWord} title="Отчёт куратора — бланк колледжа">
                Отчёт в Word
              </button>
              {current.can_edit && (
                <button type="button" className="btn-primary" onClick={save} disabled={busy || !dirty}>
                  Сохранить
                </button>
              )}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
