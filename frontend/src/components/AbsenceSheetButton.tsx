import { useState } from "react";
import type { FormEvent } from "react";
import { ApiError, downloadFile } from "../api/client";
import { toIso, todayIso } from "../utils/date";

function monthStartIso(): string {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth(), 1));
}

/** «Лист ознакомления и письменного объяснения по пропускам и опозданиям» — файл Word (.docx) по образцу колледжа
 * с днями пропусков студента за выбранный период (часов в листе нет). Кураторы распечатывают его и дают студенту
 * на подпись. По умолчанию — пропуски без уважительной причины и опоздания; пропуски по уважительной причине
 * (больничный, приказ, практика) добавляются галочкой. */
export default function AbsenceSheetButton({ studentId, lastName, groupCode }: { studentId: number; lastName: string; groupCode: string }) {
  const [dateFrom, setDateFrom] = useState(monthStartIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const [includeExcused, setIncludeExcused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function download(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      const query = `date_from=${dateFrom}&date_to=${dateTo}${includeExcused ? "&include_excused=true" : ""}`;
      await downloadFile(`/students/${studentId}/absence-sheet?${query}`, `Лист_ознакомления_${lastName}_${groupCode}.docx`);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сформировать лист");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="add-block absence-sheet" onSubmit={download}>
      <p className="add-block__title">Лист ознакомления по пропускам (Word)</p>
      <div className="inline-form">
        <label>
          С{" "}
          <input type="date" value={dateFrom} max={dateTo} onChange={(e) => setDateFrom(e.target.value)} required />
        </label>
        <label>
          По{" "}
          <input type="date" value={dateTo} min={dateFrom} max={todayIso()} onChange={(e) => setDateTo(e.target.value)} required />
        </label>
        <label>
          <input type="checkbox" checked={includeExcused} onChange={(e) => setIncludeExcused(e.target.checked)} /> Добавить пропуски по
          уважительной причине
        </label>
        <button type="submit" disabled={busy || !dateFrom || !dateTo}>
          Сформировать .docx
        </button>
      </div>
      {error && <div className="error-text">{error}</div>}
      {done && <p className="hint">Файл сформирован и скачан. В листе — дни пропусков и опоздания за период, без часов.</p>}
    </form>
  );
}
