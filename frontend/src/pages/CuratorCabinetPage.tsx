import { useEffect, useMemo, useState, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import MarkCodeButtons from "../components/MarkCodeButtons";
import MarkCommentModal from "../components/MarkCommentModal";
import { scrollToTop } from "../utils/scroll";
import type { GroupSummary, MarkCodeOption, MonthDayStatus, RosterResponse } from "../api/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

interface PendingMark {
  mark_code: string;
  comment: string;
  basis_reference: string;
}

export default function CuratorCabinetPage() {
  const [searchParams] = useSearchParams();
  const deepLinkGroupId = searchParams.get("group");
  const deepLinkDate = searchParams.get("date");

  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [groupId, setGroupId] = useState<number | null>(deepLinkGroupId ? Number(deepLinkGroupId) : null);
  const [date, setDate] = useState(deepLinkDate ?? todayIso());
  const [roster, setRoster] = useState<RosterResponse | null>(null);
  const [markCodes, setMarkCodes] = useState<MarkCodeOption[]>([]);
  const [pending, setPending] = useState<Record<number, PendingMark>>({});
  const [monthStatus, setMonthStatus] = useState<MonthDayStatus[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPeriodForm, setShowPeriodForm] = useState<number | null>(null);
  const [showCommentFor, setShowCommentFor] = useState<number | null>(null);

  useEffect(() => {
    api.get<GroupSummary[]>("/curator/groups").then((gs) => {
      setGroups(gs);
      // Ссылка "Открыть" из Telegram уже задаёт группу — не перезатираем её.
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

  async function submitDay(allPresent: boolean) {
    if (!groupId) return;
    setBusy(true);
    setError(null);
    try {
      const path = allPresent
        ? `/curator/groups/${groupId}/day/mark-all-present?date=${date}`
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
      setError(err instanceof ApiError ? err.message : "Не удалось сдать день");
      scrollToTop();
    } finally {
      setBusy(false);
    }
  }

  if (groups.length === 0) {
    return <p>У вас нет закреплённых групп.</p>;
  }

  return (
    <div>
      <div className="roster-sticky-header">
        <div className="toolbar">
          <select value={groupId ?? ""} onChange={(e) => setGroupId(Number(e.target.value))}>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.code} (курс {g.course}){g.is_submitted_today ? "" : " — не сдано сегодня"}
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
              : "День не активирован — куратор ещё не сдал"}
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
              Сдать день
            </button>
          </div>
        </>
      )}

      {showPeriodForm !== null && (
        <AbsencePeriodModal
          studentId={showPeriodForm}
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
  markCodes,
  onClose,
  onSaved,
}: {
  studentId: number;
  markCodes: MarkCodeOption[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [markCode, setMarkCode] = useState(markCodes[0]?.code ?? "");
  const [dateFrom, setDateFrom] = useState(todayIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const [basisReference, setBasisReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
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
        <h3>Длительное отсутствие</h3>
        <label>
          Код
          <select value={markCode} onChange={(e) => setMarkCode(e.target.value)}>
            {markCodes.map((m) => (
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
          <input value={basisReference} onChange={(e) => setBasisReference(e.target.value)} placeholder="№ приказа / справки" />
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
