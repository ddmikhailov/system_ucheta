import { useState } from "react";
import { ApiError, downloadFile, uploadFile } from "../api/client";
import { dialogs } from "../utils/feedback";

interface PreviewRow {
  row: number;
  label: string;
  errors: string[];
  will_update: boolean;
}

interface Preview {
  total: number;
  ready: number;
  unchanged: number;
  with_errors: number;
  rows: PreviewRow[];
}

interface ApplyResult {
  updated: number;
  skipped_with_errors: number;
}

const MAX_FILE_BYTES = 5 * 1024 * 1024; // как на сервере (dossier_import.MAX_FILE_BYTES)

// Массовая загрузка досье из Excel: скачать шаблон → заполнить → выбрать файл →
// посмотреть предпросмотр с ошибками → применить. Строки с ошибками пропускаются.
export default function DossierImport() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    const tooBig = f !== null && f.size > MAX_FILE_BYTES;
    setFile(tooBig ? null : f);
    setPreview(null);
    setResult(null);
    // Проверяем здесь, а не ждём ответа сервера: через обратный прокси отказ по размеру приходил бы общей ошибкой.
    setError(tooBig ? "Файл больше 5 МБ — разбейте его на несколько." : null);
  }

  if (!open) {
    return (
      <p>
        <button className="link-btn" onClick={() => setOpen(true)}>
          Загрузить досье из Excel…
        </button>
      </p>
    );
  }

  return (
    <div className="add-block">
      <p className="add-block__title">Загрузка досье из Excel</p>
      <p className="hint">
        Скачайте шаблон — в нём уже вписаны ваши студенты (группа и ФИО), — заполните нужные колонки и загрузите файл.
        Пустая ячейка означает «не менять». Перед записью покажем предпросмотр с ошибками.
      </p>
      <div className="inline-form">
        <button
          onClick={() =>
            run(
              () => downloadFile("/dossier-import/template", "dossier_template.xlsx"),
              () => undefined
            )
          }
          disabled={busy}
        >
          Скачать шаблон
        </button>
        <input type="file" accept=".xlsx" onChange={(e) => pick(e.target.files?.[0] ?? null)} />
        <button
          disabled={busy || !file}
          onClick={() => file && run(() => uploadFile<Preview>("/dossier-import/preview", file), setPreview)}
        >
          Проверить файл
        </button>
        <button className="link-btn" onClick={() => setOpen(false)}>
          Закрыть
        </button>
      </div>

      {error && <div className="error-text">{error}</div>}

      {preview && (
        <>
          <p>
            Строк: <b>{preview.total}</b> · готово к записи: <b>{preview.ready}</b> · с ошибками:{" "}
            <b>{preview.with_errors}</b>
            {preview.unchanged > 0 && <> · без данных: {preview.unchanged}</>}
          </p>
          {preview.rows.some((r) => r.errors.length > 0) && (
            <table className="dash-table">
              <thead>
                <tr>
                  <th>Строка</th>
                  <th>Студент</th>
                  <th>Ошибки</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows
                  .filter((r) => r.errors.length > 0)
                  .map((r) => (
                    <tr key={r.row} className="not-submitted-row">
                      <td data-label="Строка">{r.row}</td>
                      <td data-label="Студент">{r.label || "—"}</td>
                      <td data-label="Ошибки">{r.errors.join("; ")}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}
          {preview.ready > 0 && !result && (
            <p>
              <button
                disabled={busy || !file}
                onClick={async () => {
                  if (
                    preview.with_errors > 0 &&
                    !(await dialogs.confirm(`Строк с ошибками: ${preview.with_errors} — они будут пропущены. Записать остальные?`, {
                      confirmLabel: "Записать остальные",
                    }))
                  )
                    return;
                  if (file) run(() => uploadFile<ApplyResult>("/dossier-import/apply", file), setResult);
                }}
              >
                Записать {preview.ready} {preview.with_errors > 0 ? "(без строк с ошибками)" : ""}
              </button>
            </p>
          )}
        </>
      )}

      {result && (
        <div className="day-status submitted">
          Обновлено студентов: {result.updated}
          {result.skipped_with_errors > 0 && <>, пропущено строк с ошибками: {result.skipped_with_errors}</>}
        </div>
      )}
    </div>
  );
}
