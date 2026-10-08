import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useEscapeKey } from "../hooks/useEscapeKey";
import type { MarkCodeOption } from "../api/types";
import { todayIso } from "../utils/date";

// «Длительное отсутствие» — период по одному студенту (больничный, приказ).
export default function AbsencePeriodModal({
  studentId,
  studentName,
  markCodes,
  onClose,
  onSaved,
}: {
  studentId: number;
  studentName: string;
  markCodes: MarkCodeOption[];
  onClose: () => void;
  onSaved: () => void;
}) {
  // Только уважительные коды — период это "больничный/приказ на много
  // дней" (см. TODO.md 3: раньше по умолчанию стояло "Опоздание").
  const excusedCodes = markCodes.filter((m) => m.is_excused);
  const [markCode, setMarkCode] = useState(excusedCodes[0]?.code ?? "");
  const [dateFrom, setDateFrom] = useState(todayIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const [basisReference, setBasisReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscapeKey(onClose);

  async function save() {
    if (dateTo < dateFrom) {
      setError("Дата окончания раньше даты начала");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.post("/curator/absence-periods", {
        student_id: studentId,
        mark_code: markCode,
        date_from: dateFrom,
        date_to: dateTo,
        basis_reference: basisReference || null,
      });
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить период");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Длительное отсутствие" onClick={(e) => e.stopPropagation()}>
        <h3>Длительное отсутствие{studentName ? ` — ${studentName}` : ""}</h3>
        <label>
          Код
          <select value={markCode} onChange={(e) => setMarkCode(e.target.value)}>
            {excusedCodes.map((m) => (
              <option key={m.code} value={m.code}>
                {m.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          С
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label>
          По
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
        <label>
          Основание
          <input
            value={basisReference}
            onChange={(e) => setBasisReference(e.target.value)}
            placeholder="№ приказа / справки"
          />
        </label>
        {error && <div className="error-text">{error}</div>}
        <div className="actions">
          <button onClick={onClose}>Отмена</button>
          <button onClick={save} disabled={busy}>
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}
