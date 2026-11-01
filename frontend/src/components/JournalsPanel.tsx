import { useState } from "react";
import { ApiError, uploadFile } from "../api/client";
import type { JournalDiscrepancy, JournalGrid, JournalImportReport, JournalSubject } from "../api/types";
import { useApi } from "../hooks/useApi";
import { formatDateRu } from "../utils/date";

const MAX_FILE_BYTES = 5 * 1024 * 1024; // как на сервере (routers/journal.MAX_FILE_BYTES)

const COUNT_LABELS: [string, string][] = [
  ["students_matched", "студентов найдено"],
  ["grades_new", "новых оценок"],
  ["absences_new", "новых «н»"],
  ["updated", "изменено"],
  ["removed", "убрано"],
  ["unchanged", "без изменений"],
];

/** «Журналы дисциплин» (вкладка группы): куратор загружает выгрузку электронного журнала преподавателя (.xlsx, одна
 * дисциплина) и смотрит журнал в платформе — часы по столбцам, оценки и «н», темы уроков. «н» из журнала
 * преподавателя дневные отметки куратора не меняет: расхождения показаны отдельным списком. */
export default function JournalsPanel({ groupId }: { groupId: number }) {
  const subjects = useApi<JournalSubject[]>(`/journal/groups/${groupId}/subjects`, "Не удалось загрузить журналы");
  const [picked, setPicked] = useState<string | null>(null);
  const list = subjects.data ?? [];
  const code = picked && list.some((s) => s.code === picked) ? picked : (list[0]?.code ?? null);

  return (
    <div className="jr">
      <ImportBlock onApplied={subjects.reload} />
      {subjects.error && <div className="error-text">{subjects.error}</div>}
      {subjects.loading && !subjects.data && <p className="hint">Загрузка…</p>}
      {subjects.data && list.length === 0 && (
        <p className="hint">
          Журналы ещё не загружены. Выгрузите журнал дисциплины из электронного журнала колледжа и загрузите файл
          выше: оценки, «н» и темы уроков появятся здесь.
        </p>
      )}
      {list.length > 0 && (
        <>
          <div className="jr__subjects" role="group" aria-label="Дисциплины">
            {list.map((s) => (
              <button
                key={s.code}
                className={s.code === code ? "btn-primary" : "btn-secondary"}
                aria-pressed={s.code === code}
                onClick={() => setPicked(s.code)}
                title={`${formatDateRu(s.first_on)} — ${formatDateRu(s.last_on)}`}
              >
                {s.code} {s.name}
              </button>
            ))}
          </div>
          {code && <SubjectGrid key={code} groupId={groupId} code={code} />}
          <Discrepancies groupId={groupId} />
        </>
      )}
    </div>
  );
}

function ImportBlock({ onApplied }: { onApplied: () => void }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<JournalImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function pick(f: File | null) {
    const tooBig = f !== null && f.size > MAX_FILE_BYTES;
    setFile(tooBig ? null : f);
    setReport(null);
    setError(tooBig ? "Файл больше 5 МБ." : null);
  }

  async function send(path: "preview" | "apply") {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadFile<JournalImportReport>(`/journal/${path}`, file);
      setReport(result);
      if (result.applied) onApplied();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось обработать файл");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <p>
        <button className="link-btn" onClick={() => setOpen(true)}>
          Загрузить журнал из Excel…
        </button>
      </p>
    );
  }

  return (
    <div className="add-block">
      <p className="add-block__title">Загрузка журнала дисциплины</p>
      <p className="hint">
        Файл — выгрузка электронного журнала по одной дисциплине (.xlsx). Подойдёт и журнал на две подгруппы:
        студентов находим по ФИО, чужих групп пропускаем. Повторная загрузка того же журнала ничего не дублирует,
        новая версия обновляет оценки. Дневные отметки посещаемости файл не меняет.
      </p>
      <div className="inline-form">
        <input type="file" accept=".xlsx" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
        <button disabled={busy || !file} onClick={() => send("preview")}>
          Проверить файл
        </button>
        <button className="link-btn" onClick={() => setOpen(false)}>
          Закрыть
        </button>
      </div>
      {error && <div className="error-text">{error}</div>}
      {report && <Report report={report} busy={busy} onApply={() => send("apply")} />}
    </div>
  );
}

function Report({ report, busy, onApply }: { report: JournalImportReport; busy: boolean; onApply: () => void }) {
  const skipped = [
    ["Не найдены в платформе", report.not_found],
    ["Не из ваших групп", report.out_of_scope],
    ["Одинаковое ФИО, не определить", report.ambiguous],
  ] as const;
  return (
    <div className="jr__report">
      <p>
        <b>
          {report.subject_code} {report.subject_name}
        </b>
        {report.period_from && report.period_to && (
          <>
            {" "}
            · {formatDateRu(report.period_from)} — {formatDateRu(report.period_to)}
          </>
        )}
      </p>
      {report.blocked ? (
        <div className="error-text">{report.blocked}</div>
      ) : (
        <p>
          {COUNT_LABELS.filter(([key]) => (report.counts[key] ?? 0) > 0).map(([key, label], i) => (
            <span key={key}>
              {i > 0 && " · "}
              <b>{report.counts[key]}</b> {label}
            </span>
          ))}
        </p>
      )}
      {report.warnings.length > 0 && (
        <ul className="hint">
          {report.warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {skipped.map(
        ([title, names]) =>
          names.length > 0 && (
            <details key={title}>
              <summary>
                {title}: {names.length}
              </summary>
              <p className="hint">{names.join(", ")}</p>
            </details>
          )
      )}
      {report.applied ? (
        <p className="ok-text">Журнал загружен.</p>
      ) : (
        !report.blocked && (
          <p>
            <button className="btn-primary" disabled={busy} onClick={onApply}>
              Загрузить журнал
            </button>
          </p>
        )
      )}
    </div>
  );
}

function cellClass(value: string | undefined): string {
  if (!value) return "";
  if (value === "н") return "jr-absent";
  return Number(value) <= 2 ? "jr-low" : "jr-grade";
}

function SubjectGrid({ groupId, code }: { groupId: number; code: string }) {
  const grid = useApi<JournalGrid>(`/journal/groups/${groupId}/subjects/${encodeURIComponent(code)}`, "Не удалось загрузить журнал");
  if (grid.error) return <div className="error-text">{grid.error}</div>;
  if (!grid.data) return <p className="hint">Загрузка…</p>;
  const { lessons, students } = grid.data;
  const withTopics = lessons.filter((l) => l.topic);
  const weak = students.filter((s) => s.low_average || s.twos > 0);
  return (
    <>
      {weak.length > 0 && (
        <div className="jr__attention" role="status">
          <b>Обратите внимание ({weak.length}):</b>{" "}
          {weak.map((s, i) => (
            <span key={s.student_id}>
              {i > 0 && "; "}
              {s.full_name}
              {s.low_average && s.average !== null && <> — средняя {s.average.toFixed(1).replace(".", ",")}</>}
              {s.twos > 0 && <> — задолженность: оценок «2» — {s.twos}</>}
            </span>
          ))}
          . Средняя ниже 4 или оценка «2»: помогите исправить.
        </div>
      )}
      <div className="jr__scroll">
        <table className="jr-grid">
          <caption className="hint">
            {grid.data.name}: часы — столбцы, пустая ячейка — присутствовал без оценки
          </caption>
          <thead>
            <tr>
              <th scope="col" className="jr-grid__name">
                Студент
              </th>
              <th scope="col" title="Средний балл">
                Ср.
              </th>
              <th scope="col" title="Часов «н»">
                «н»
              </th>
              {lessons.map((l) => (
                <th key={l.key} scope="col" title={l.topic ?? undefined}>
                  {l.date.slice(8)}.{l.date.slice(5, 7)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {students.map((s) => (
              <tr key={s.student_id} className={s.low_average || s.twos > 0 ? "jr-weak" : undefined}>
                <th scope="row" className="jr-grid__name">
                  {s.full_name}
                </th>
                <td className={s.low_average ? "jr-low" : undefined}>{s.average !== null ? s.average.toFixed(1).replace(".", ",") : "—"}</td>
                <td>{s.absent_hours || ""}</td>
                {lessons.map((l) => (
                  <td key={l.key} className={cellClass(s.cells[l.key])}>
                    {s.cells[l.key] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {withTopics.length > 0 && (
        <details>
          <summary>Темы уроков и домашние задания ({withTopics.length})</summary>
          <ul className="jr__topics">
            {withTopics.map((l) => (
              <li key={l.key}>
                <b>{formatDateRu(l.date)}</b> — {l.topic}
                {l.homework && <span className="hint"> · задание: {l.homework}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function Discrepancies({ groupId }: { groupId: number }) {
  const rows = useApi<JournalDiscrepancy[]>(`/journal/groups/${groupId}/discrepancies`, "Не удалось загрузить сверку");
  if (!rows.data || rows.data.length === 0) return null;
  return (
    <details open>
      <summary>Сверка с вашим журналом посещаемости: {rows.data.length}</summary>
      <p className="hint">
        Преподаватель отметил «н», а в дневном журнале — присутствие или отметки нет. Ничего не меняется само: проверьте
        день и при необходимости поправьте отметку во вкладке «Журнал».
      </p>
      <ul className="jr__topics">
        {rows.data.map((r) => (
          <li key={`${r.student_id}-${r.date}`}>
            <b>{formatDateRu(r.date)}</b> · {r.full_name} — «н»: {r.hours} ч. ({r.subjects.join(", ")}) ·{" "}
            {r.kind === "present" ? `у вас: «${r.curator_code}»` : "день не отмечен"}
          </li>
        ))}
      </ul>
    </details>
  );
}
