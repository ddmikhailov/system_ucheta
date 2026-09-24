import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../../api/client";
import MarkCodeButtons from "../../components/MarkCodeButtons";
import MarkCommentModal from "../../components/MarkCommentModal";
import { scrollToTop } from "../../utils/scroll";
import type { MarkCodeOption, MonthDayStatus, RosterResponse, StudyGroupAdmin } from "../../api/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

interface PendingMark {
  mark_code: string;
  comment: string;
  basis_reference: string;
}

/** Журнал группы для администрации (обновление 1.1): та же механика, что и
 * в кабинете куратора, но группа выбирается из всех групп в зоне видимости
 * (весь колледж у admin/edu_department, своё отделение у зав. отделением —
 * бэкенд уже разграничивает это в assert_can_access_group), для любого дня,
 * с полным правом правки и видимостью, кто и когда вносил отметку. */
export default function GroupJournalTab() {
  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [date, setDate] = useState(todayIso());
  const [roster, setRoster] = useState<RosterResponse | null>(null);
  const [markCodes, setMarkCodes] = useState<MarkCodeOption[]>([]);
  const [pending, setPending] = useState<Record<number, PendingMark>>({});
  const [monthStatus, setMonthStatus] = useState<MonthDayStatus[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPeriodForm, setShowPeriodForm] = useState<number | null>(null);
  const [showCommentFor, setShowCommentFor] = useState<number | null>(null);

  useEffect(() => {
    api.get<StudyGroupAdmin[]>("/admin/groups").then((allGroups) => {
      const gs = allGroups.filter((g) => g.is_active);
      setGroups(gs);
      if (gs.length > 0 && groupId === null) setGroupId(gs[0].id);
    });
    api.get<MarkCodeOption[]>("/curator/mark-codes").then(setMarkCodes);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadRoster = useCallback(async () => {
    if (!groupId) return;
    setError(null);
    try {
      const r = await api.get<RosterResponse>(`/curator/groups/${groupId}/day?date=${date}`);
      setRoster(r);
      const initialPending: Record<number, PendingMark> = {};
      for (const entry of r.entries) {
        if (entry.mark_code && !entry.is_locked) {
          initialPending[entry.student_id] = {
            mark_code: entry.mark_code,
            comment: entry.comment ?? "",
            basis_reference: entry.basis_reference ?? "",
          };
        }
      }
      setPending(initialPending);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить день");
    }
  }, [groupId, date]);

  useEffect(() => {
    loadRoster();
  }, [loadRoster]);

  useEffect(() => {
    if (!groupId) return;
    const [year, month] = date.split("-").map(Number);
    api
      .get<MonthDayStatus[]>(`/curator/groups/${groupId}/month-status?year=${year}&month=${month}`)
      .then(setMonthStatus)
      .catch(() => setMonthStatus([]));
  }, [groupId, date]);

  const markCodeByCode = useMemo(() => new Map(markCodes.map((m) => [m.code, m])), [markCodes]);

  function setStudentMark(studentId: number, code: string | null) {
    setPending((prev) => {
      const next = { ...prev };
      if (!code) {
        delete next[studentId];
      } else {
        next[studentId] = next[studentId]
          ? { ...next[studentId], mark_code: code }
          : { mark_code: code, comment: "", basis_reference: "" };
      }
      return next;
    });
  }

  function updateField(studentId: number, field: "comment" | "basis_reference", value: string) {
    setPending((prev) => ({
      ...prev,
      [studentId]: { ...prev[studentId], [field]: value },
    }));
  }

  async function submitDay(allPresent: boolean, confirmed = false) {
    if (!groupId) return;
    setBusy(true);
    setError(null);
    try {
      const path = allPresent
        ? `/curator/groups/${groupId}/day/mark-all-present?date=${date}${confirmed ? "&confirm=true" : ""}`
        : `/curator/groups/${groupId}/day/submit?date=${date}`;
      const body = allPresent
        ? undefined
        : {
            exceptions: Object.entries(pending).map(([studentId, p]) => ({
              student_id: Number(studentId),
              mark_code: p.mark_code,
              comment: p.comment || null,
              basis_reference: p.basis_reference || null,
            })),
          };
      const updated = await api.post<RosterResponse>(path, body);
      setRoster(updated);
      scrollToTop();
    } catch (err) {
      // Сервер отказывает с 409, если "Все присутствуют" стёрло бы уже
      // внесённые отметки (см. TODO.md 1.8) — переспрашиваем вместо того,
      // чтобы просто показать ошибку.
      if (err instanceof ApiError && err.status === 409 && allPresent && !confirmed) {
        if (window.confirm(`${err.message}\n\nВсё равно отметить всех присутствующими?`)) {
          setBusy(false);
          await submitDay(true, true);
          return;
        }
      } else {
        setError(err instanceof ApiError ? err.message : "Не удалось сохранить день");
      }
      scrollToTop();
    } finally {
      setBusy(false);
    }
  }

  if (groups.length === 0) {
    return <p>Нет ни одной группы в зоне видимости.</p>;
  }

  return (
    <div>
      <div className="roster-sticky-header">
        <div className="toolbar">
          <select value={groupId ?? ""} onChange={(e) => setGroupId(Number(e.target.value))}>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.code} (курс {g.course}){g.curator_name ? ` — ${g.curator_name}` : " — нет куратора"}
              </option>
            ))}
          </select>
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} max={todayIso()} />
        </div>

        <div className="month-strip">
          {monthStatus.map((d) => (
            <span
              key={d.date}
              title={d.date}
              className={`month-dot ${
                ["weekend", "holiday", "vacation"].includes(d.day_type)
                  ? "weekend"
                  : d.is_submitted
                    ? (d.is_on_time ? "ok" : "late")
                    : "missing"
              } ${d.day_type === "remote" ? "remote-day" : ""} ${d.date === date ? "selected" : ""}`}
              onClick={() => setDate(d.date)}
            />
          ))}
        </div>
      </div>

      {error && <div className="error-text">{error}</div>}

      {roster && (
        <>
          <div className={`day-status ${roster.is_submitted ? "submitted" : "not-submitted"}`}>
            {roster.is_submitted
              ? `День сдан${roster.is_on_time === false ? " (задним числом)" : ""}`
              : "День не активирован куратором — можно заполнить самостоятельно"}
          </div>

          <table className="roster-table">
            <thead>
              <tr>
                <th>ФИО</th>
                <th>Статус</th>
                <th>Комментарий</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {roster.entries.map((entry) => {
                const current = pending[entry.student_id];
                const code = current?.mark_code ?? null;
                const risky = entry.risk_streak >= 3;
                const hasComment = Boolean(current?.comment || current?.basis_reference);
                return (
                  <tr key={entry.student_id} className={risky ? "risk-row" : ""}>
                    <td data-label="ФИО">{entry.full_name}</td>
                    <td data-label="Статус">
                      {entry.is_locked ? (
                        <span className="locked-badge" title={entry.basis_reference ?? ""}>
                          {entry.mark_name}
                        </span>
                      ) : (
                        <MarkCodeButtons
                          value={code}
                          markCodes={markCodes}
                          onChange={(c) => setStudentMark(entry.student_id, c)}
                        />
                      )}
                      {entry.is_draft_suggestion && !entry.is_locked && (
                        <span className="draft-badge">черновик со вчера</span>
                      )}
                      {risky && <span className="risk-badge">риск: {entry.risk_streak} дн. подряд</span>}
                    </td>
                    <td data-label="Комментарий">
                      {!entry.is_locked && code && (
                        <button className="comment-btn" onClick={() => setShowCommentFor(entry.student_id)}>
                          {hasComment ? "Комментарий добавлен" : "Добавить комментарий"}
                        </button>
                      )}
                    </td>
                    <td>
                      {!entry.is_locked && (
                        <button className="link-btn" onClick={() => setShowPeriodForm(entry.student_id)}>
                          Период
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="actions">
            <button onClick={() => submitDay(true)} disabled={busy}>
              Все присутствуют
            </button>
            <button onClick={() => submitDay(false)} disabled={busy}>
              Сохранить день
            </button>
          </div>
        </>
      )}

      {showPeriodForm !== null && (
        <AbsencePeriodModal
          studentId={showPeriodForm}
          studentName={roster?.entries.find((e) => e.student_id === showPeriodForm)?.full_name ?? ""}
          markCodes={markCodes}
          onClose={() => setShowPeriodForm(null)}
          onSaved={() => {
            setShowPeriodForm(null);
            loadRoster();
            scrollToTop();
          }}
        />
      )}

      {showCommentFor !== null && (
        <MarkCommentModal
          comment={pending[showCommentFor]?.comment ?? ""}
          basisReference={pending[showCommentFor]?.basis_reference ?? ""}
          requiresDocument={Boolean(markCodeByCode.get(pending[showCommentFor]?.mark_code ?? "")?.requires_document)}
          lastEditedInfo={(() => {
            const entry = roster?.entries.find((e) => e.student_id === showCommentFor);
            if (!entry?.last_edited_by) return null;
            return entry.last_edited_at
              ? `${entry.last_edited_by}, ${formatDateTime(entry.last_edited_at)}`
              : entry.last_edited_by;
          })()}
          onClose={() => setShowCommentFor(null)}
          onSave={(comment, basisReference) => {
            updateField(showCommentFor, "comment", comment);
            updateField(showCommentFor, "basis_reference", basisReference);
          }}
        />
      )}
    </div>
  );
}

function AbsencePeriodModal({
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
      <div className="modal" onClick={(e) => e.stopPropagation()}>
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
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} max={todayIso()} />
        </label>
        <label>
          По
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} max={todayIso()} />
        </label>
        <label>
          Основание
          <input
            value={basisReference}
            onChange={(e) => setBasisReference(e.target.value)}
            placeholder="№ приказа / справки (необязательно)"
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
