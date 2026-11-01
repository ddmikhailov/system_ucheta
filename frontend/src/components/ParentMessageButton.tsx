import { useState } from "react";
import TextArea from "./TextArea";
import { api, ApiError } from "../api/client";
import type { ParentMessage } from "../api/types";

const KINDS: { value: string; label: string }[] = [
  { value: "absences", label: "О пропусках" },
  { value: "late", label: "Об опозданиях" },
  { value: "long_absence", label: "О длительном отсутствии" },
  { value: "meeting", label: "Приглашение на собрание" },
  { value: "semester", label: "Итог семестра (посещаемость)" },
];

/** «Сообщение родителям»: платформа готовит текст по данным студента и группы, куратор правит его и копирует в
 * мессенджер (отправки из платформы нет). Если браузер не даёт доступ к буферу обмена, текст остаётся в поле — его
 * можно скопировать вручную. */
export default function ParentMessageButton({ studentId, days = 14 }: { studentId: number; days?: number }) {
  const [kind, setKind] = useState("absences");
  const [text, setText] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function prepare() {
    setBusy(true);
    setError(null);
    setNotice(null);
    setText("");
    try {
      const m = await api.get<ParentMessage>(`/students/${studentId}/parent-message?kind=${kind}&days=${days}`);
      if (!m.text) {
        setNotice(m.empty_reason ?? "Сообщать нечего.");
        return;
      }
      setText(m.text);
      try {
        await navigator.clipboard.writeText(m.text);
        setNotice("Текст скопирован — вставьте его в мессенджер.");
      } catch {
        setNotice("Не удалось скопировать автоматически — выделите текст ниже и скопируйте вручную.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось подготовить сообщение");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="absence-message">
      <label>
        Вид сообщения родителям
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </label>{" "}
      <button onClick={prepare} disabled={busy}>
        Подготовить сообщение
      </button>
      {error && <div className="error-text">{error}</div>}
      {notice && <p className="hint">{notice}</p>}
      {text && (
        <TextArea className="absence-message__text" expandTitle="Сообщение родителям" rows={8} value={text} onChange={(e) => setText(e.target.value)} aria-label="Текст сообщения родителям" />
      )}
    </div>
  );
}
