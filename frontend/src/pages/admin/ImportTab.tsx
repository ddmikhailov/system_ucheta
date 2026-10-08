import { useMemo, useState } from "react";
import { ApiError, downloadFile, uploadFile } from "../../api/client";
import ResultsBar from "../../components/dashboards/ResultsBar";
import { dialogs, toast } from "../../utils/feedback";
import { credentialsCsv, type Credential } from "../../utils/credentialsCsv";
import { filterByQuery } from "../../utils/searchMatch";
import "../../styles/import.css";

interface Change {
  sheet: string;
  action: string;
  label: string;
  detail: string;
}
interface RowError {
  sheet: string;
  row: number;
  message: string;
}
interface Report {
  counts: Record<string, number>;
  total_changes: number;
  changes: Change[];
  changes_truncated: boolean;
  errors: RowError[];
  warnings: string[];
  needs_confirmation: string | null;
  sheets: string[];
}
interface ApplyResult extends Report {
  credentials: Credential[];
}

const MAX_FILE_BYTES = 5 * 1024 * 1024; // как на сервере (contingent_import.MAX_FILE_BYTES)

function saveCsv(rows: Credential[]) {
  const url = URL.createObjectURL(new Blob([credentialsCsv(rows)], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "vremennye_paroli.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Единая загрузка контингента: скачать шаблон → править → загрузить → предпросмотр → записать.
export default function ImportTab() {
  const [file, setFile] = useState<File | null>(null);
  const [absent, setAbsent] = useState<"keep" | "expel">("keep");
  const [replaceCurators, setReplaceCurators] = useState(false);
  const [createDepartments, setCreateDepartments] = useState(false);
  const [issuePasswords, setIssuePasswords] = useState(false);
  const [enrolledAt, setEnrolledAt] = useState("");
  const [confirmLarge, setConfirmLarge] = useState(false);

  const [report, setReport] = useState<Report | null>(null);
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sheetFilter, setSheetFilter] = useState("all");
  const [query, setQuery] = useState("");

  const params = useMemo(() => {
    const p = new URLSearchParams({ absent_students: absent });
    if (replaceCurators) p.set("replace_curators", "true");
    if (createDepartments) p.set("create_departments", "true");
    if (issuePasswords) p.set("issue_passwords", "true");
    if (enrolledAt) p.set("default_enrolled_at", enrolledAt);
    return p;
  }, [absent, replaceCurators, createDepartments, issuePasswords, enrolledAt]);

  // Любое изменение файла или настроек делает прежний предпросмотр неактуальным.
  function reset() {
    setReport(null);
    setResult(null);
    setConfirmLarge(false);
    setSheetFilter("all");
    setQuery("");
  }
  function change<T>(setter: (v: T) => void) {
    return (value: T) => {
      setter(value);
      reset();
    };
  }

  async function run<T>(action: () => Promise<T>, onOk: (v: T) => void) {
    setBusy(true);
    setError(null);
    try {
      onOk(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось выполнить операцию");
    } finally {
      setBusy(false);
    }
  }

  function pick(f: File | null) {
    reset();
    if (f && f.size > MAX_FILE_BYTES) {
      setFile(null);
      setError("Файл больше 5 МБ — разбейте его на несколько.");
      return;
    }
    setFile(f);
    setError(null);
  }

  const queryString = (extra: Record<string, string> = {}) => {
    const p = new URLSearchParams(params);
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    return p.toString();
  };

  const check = () => file && run(() => uploadFile<Report>(`/contingent-import/preview?${queryString()}`, file), (r) => {
    setReport(r);
    setResult(null);
  });

  async function save() {
    if (!file || !report) return;
    const summary = Object.entries(report.counts).map(([k, v]) => `${k}: ${v}`).join("\n") || "изменений нет";
    const ok = await dialogs.confirm(`Записать в базу?\n\n${summary}`, { confirmLabel: "Записать" });
    if (!ok) return;
    await run(
      () => uploadFile<ApplyResult>(`/contingent-import/apply?${queryString(confirmLarge ? { confirm_large: "true" } : {})}`, file),
      (r) => {
        setResult(r);
        setReport(null);
        toast("Контингент загружен");
      },
    );
  }

  const sheets = report ? [...new Set(report.changes.map((c) => c.sheet))] : [];
  const visibleChanges = useMemo(() => {
    if (!report) return [];
    const bySheet = sheetFilter === "all" ? report.changes : report.changes.filter((c) => c.sheet === sheetFilter);
    return filterByQuery(bySheet, query, (c) => `${c.label} ${c.detail} ${c.action}`);
  }, [report, sheetFilter, query]);
  const filtered = sheetFilter !== "all" || query.trim() !== "";
  const canWrite = !!report && report.errors.length === 0 && (!report.needs_confirmation || confirmLarge) && Object.keys(report.counts).length > 0;

  return (
    <div className="import">
      <p className="hint">
        Загрузка групп, студентов и кураторов одним файлом — без обновления платформы. Скачайте шаблон (в нём уже ваши текущие данные), поправьте
        и загрузите обратно: платформа сначала покажет, что изменится, и запишет только после подтверждения. Ничего не удаляется; пустая ячейка
        означает «не менять».
      </p>

      <section className="import__step" aria-labelledby="import-step-1">
        <h3 id="import-step-1">1. Шаблон</h3>
        <div className="import__row">
          <button type="button" className="btn-secondary" disabled={busy}
            onClick={() => run(() => downloadFile("/contingent-import/template", "kait20_contingent.xlsx"), () => undefined)}>
            Шаблон с текущими данными
          </button>
          <button type="button" className="btn-secondary" disabled={busy}
            onClick={() => run(() => downloadFile("/contingent-import/template?with_data=false", "kait20_contingent_empty.xlsx"), () => undefined)}>
            Пустой шаблон
          </button>
        </div>
      </section>

      <section className="import__step" aria-labelledby="import-step-2">
        <h3 id="import-step-2">2. Файл и настройки</h3>
        <div className="import__row">
          <input type="file" accept=".xlsx" aria-label="Файл Excel с контингентом" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
        </div>
        <div className="import__options">
          <label className="import__field">
            <span>Студенты, которых нет в файле</span>
            <select value={absent} onChange={(e) => change(setAbsent)(e.target.value as "keep" | "expel")} aria-label="Студенты, которых нет в файле">
              <option value="keep">Оставить без изменений</option>
              <option value="expel">Отметить «отчислен» (только в группах из файла)</option>
            </select>
          </label>
          <label className="import__field">
            <span>Дата зачисления новых студентов</span>
            <input type="date" value={enrolledAt} onChange={(e) => change(setEnrolledAt)(e.target.value)} aria-label="Дата зачисления новых студентов" />
            <small className="hint">Если в файле не указана; по умолчанию — сегодня.</small>
          </label>
          <label className="check-inline">
            <input type="checkbox" checked={replaceCurators} onChange={(e) => change(setReplaceCurators)(e.target.checked)} />
            Заменять действующих кураторов
          </label>
          <label className="check-inline">
            <input type="checkbox" checked={createDepartments} onChange={(e) => change(setCreateDepartments)(e.target.checked)} />
            Создавать новые отделения
          </label>
          <label className="check-inline">
            <input type="checkbox" checked={issuePasswords} onChange={(e) => change(setIssuePasswords)(e.target.checked)} />
            Выдать временные пароли новым кураторам
          </label>
        </div>
        <div className="import__row">
          <button type="button" className="btn-primary" disabled={busy || !file} onClick={check}>
            Проверить файл
          </button>
        </div>
      </section>

      {error && <div className="error-text" role="alert">{error}</div>}

      {report && (
        <section className="import__step" aria-labelledby="import-step-3">
          <h3 id="import-step-3">3. Что изменится</h3>
          <p className="hint">Листы в файле: {report.sheets.join(", ")}. Пока ничего не записано.</p>

          {report.errors.length > 0 ? (
            <div className="import__box import__box--bad" role="alert">
              <b>В файле {report.errors.length} ошибок — запись невозможна.</b> Исправьте строки из списка и загрузите файл заново.
              <div className="table-scroll">
                <table className="dash-table roster-table compact-cards">
                  <thead><tr><th>Лист</th><th>Строка</th><th>Что не так</th></tr></thead>
                  <tbody>
                    {report.errors.map((e, i) => (
                      <tr key={i}>
                        <td data-label="Лист">{e.sheet}</td>
                        <td data-label="Строка">{e.row}</td>
                        <td data-label="Что не так">{e.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : Object.keys(report.counts).length === 0 ? (
            <div className="import__box import__box--ok">Файл разобран: изменений нет — все данные из него уже есть на платформе.</div>
          ) : (
            <div className="import__counts" aria-label="Итоги проверки">
              {Object.entries(report.counts).map(([name, value]) => (
                <div key={name} className="import__count">
                  <span className="import__count-value">{value}</span>
                  <span className="import__count-name">{name}</span>
                </div>
              ))}
            </div>
          )}

          {report.warnings.length > 0 && (
            <div className="import__box import__box--warn">
              <b>Обратите внимание:</b>
              <ul>{report.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}

          {report.needs_confirmation && (
            <div className="import__box import__box--warn" role="alert">
              {report.needs_confirmation}
              <label className="check-inline">
                <input type="checkbox" checked={confirmLarge} onChange={(e) => setConfirmLarge(e.target.checked)} />
                Подтверждаю массовое выбытие
              </label>
            </div>
          )}

          {report.changes.length > 0 && (
            <>
              <div className="toolbar toolbar--filters">
                <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по списку" aria-label="Поиск по изменениям" />
                <div className="chip-filter" role="group" aria-label="Лист">
                  {["all", ...sheets].map((s) => (
                    <button key={s} type="button" className={`chip-filter__item${sheetFilter === s ? " is-active" : ""}`}
                      aria-pressed={sheetFilter === s} onClick={() => setSheetFilter(s)}>
                      {s === "all" ? "Все" : s}
                    </button>
                  ))}
                </div>
              </div>
              <ResultsBar shown={visibleChanges.length} total={report.changes.length} filtered={filtered}
                onReset={() => { setQuery(""); setSheetFilter("all"); }} />
              {report.changes_truncated && (
                <p className="hint">Подробно показаны первые {report.changes.length} из {report.total_changes} изменений; итоги выше — по всем.</p>
              )}
              <div className="table-scroll">
                <table className="dash-table roster-table compact-cards">
                  <thead><tr><th>Лист</th><th>Действие</th><th>Что</th><th>Подробности</th></tr></thead>
                  <tbody>
                    {visibleChanges.map((c, i) => (
                      <tr key={i}>
                        <td data-label="Лист">{c.sheet}</td>
                        <td data-label="Действие">{c.action}</td>
                        <td data-label="Что">{c.label}</td>
                        <td data-label="Подробности">{c.detail || "—"}</td>
                      </tr>
                    ))}
                    {visibleChanges.length === 0 && <tr><td colSpan={4}>Под выбранные условия ничего не нашлось.</td></tr>}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div className="import__row">
            <button type="button" className="btn-primary" disabled={busy || !canWrite} onClick={save}>
              Записать в базу
            </button>
          </div>
        </section>
      )}

      {result && (
        <section className="import__step" aria-labelledby="import-done">
          <h3 id="import-done">Готово</h3>
          <div className="import__box import__box--ok" role="status">
            Загрузка выполнена: {Object.entries(result.counts).map(([k, v]) => `${k} — ${v}`).join("; ") || "изменений не было"}.
          </div>
          {result.credentials.length > 0 && (
            <>
              <div className="import__box import__box--warn">
                <b>Временные пароли показаны один раз.</b> Сохраните список сейчас: после закрытия страницы пароли восстановить нельзя
                (можно выдать новые в карточке пользователя). Куратор при первом входе задаст свой пароль.
              </div>
              <div className="import__row">
                <button type="button" className="btn-secondary" onClick={() => saveCsv(result.credentials)}>
                  Скачать список паролей (CSV)
                </button>
              </div>
              <div className="table-scroll">
                <table className="dash-table roster-table compact-cards">
                  <thead><tr><th>ФИО</th><th>Отделение</th><th>Логин</th><th>Временный пароль</th></tr></thead>
                  <tbody>
                    {result.credentials.map((c) => (
                      <tr key={c.username}>
                        <td data-label="ФИО">{c.full_name}</td>
                        <td data-label="Отделение">{c.department || "—"}</td>
                        <td data-label="Логин">{c.username}</td>
                        <td data-label="Временный пароль"><code>{c.password}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
