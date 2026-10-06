import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import AbsencePeriodModal from "./AbsencePeriodModal";
import DayActionsBar from "./DayActionsBar";
import MarkCodeButtons from "./MarkCodeButtons";
import MarkCommentModal from "./MarkCommentModal";
import { scrollToTop } from "../utils/scroll";
import type { MarkCodeOption, MonthDayStatus, MyDayRhythmDay, RosterResponse } from "../api/types";
import { formatServerDateTime, todayIso } from "../utils/date";
import SearchSelect from "./SearchSelect";
import { dialogs } from "../utils/feedback";
import GroupListModal from "./GroupListModal";
import GroupRhythm from "./GroupRhythm";

// Раньше подсказка точки в полоске месяца была просто ISO-датой (см. TODO.md 4).
const MONTH_DOT_TITLES: Record<string, string> = {
  study_day: "учебный день",
  weekend: "выходной",
  holiday: "праздник",
  vacation: "каникулы",
  remote: "ЭФО",
};

interface PendingMark {
  mark_code: string;
  comment: string;
  basis_reference: string;
}

/** Группа в выпадающем списке журнала: подпись формирует вызывающая сторона. */
export interface JournalGroup {
  id: number;
  label: string;
  /** Отделение группы: если групп из нескольких отделений, сначала выбирается отделение. */
  departmentId?: number | null;
  departmentName?: string | null;
}

export interface DayJournalProps {
  /** Откуда берутся группы: кабинет куратора — свои, администрация — все в зоне видимости. */
  fetchGroups: () => Promise<JournalGroup[]>;
  emptyText: string;
  notSubmittedText: string;
  submitLabel: string;
  submitErrorText: string;
  /** Администрации видно, кто и когда правил отметку (кабинет куратора — нет). */
  showLastEdited?: boolean;
}

/** Общий журнал дня: выбор группы и даты, полоска месяца, отметки студентов, сдача дня.
 * Кабинет куратора и «Журнал» администрации различаются только источником групп и текстами. */
export default function DayJournal({
  fetchGroups,
  emptyText,
  notSubmittedText,
  submitLabel,
  submitErrorText,
  showLastEdited = false,
}: DayJournalProps) {
  const [searchParams] = useSearchParams();
  const deepLinkGroupId = searchParams.get("group");
  const deepLinkDate = searchParams.get("date");

  const [groups, setGroups] = useState<JournalGroup[]>([]);
  const [groupId, setGroupId] = useState<number | null>(deepLinkGroupId ? Number(deepLinkGroupId) : null);
  const [listOpen, setListOpen] = useState(false);
  const [date, setDate] = useState(deepLinkDate ?? todayIso());
  const [roster, setRoster] = useState<RosterResponse | null>(null);
  const [markCodes, setMarkCodes] = useState<MarkCodeOption[]>([]);
  const [pending, setPending] = useState<Record<number, PendingMark>>({});
  const [monthStatus, setMonthStatus] = useState<MonthDayStatus[]>([]);
  const [rhythm, setRhythm] = useState<MyDayRhythmDay[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPeriodForm, setShowPeriodForm] = useState<number | null>(null);
  const [showCommentFor, setShowCommentFor] = useState<number | null>(null);
  const [groupsLoaded, setGroupsLoaded] = useState(false);
  const [groupsError, setGroupsError] = useState<string | null>(null);
  const [riskThreshold, setRiskThreshold] = useState(3);
  const [firstPeriod, setFirstPeriod] = useState("");
  // Выбранное отделение; пока не выбирали — отделение текущей группы.
  const [departmentChoice, setDepartmentChoice] = useState<number | null>(null);

  function loadGroups() {
    fetchGroups()
      .then((gs) => {
        setGroups(gs);
        setGroupsLoaded(true);
        // Ссылка из уведомления уже задаёт группу (?group=) — не перезатираем её.
        if (gs.length > 0 && groupId === null) setGroupId(gs[0].id);
      })
      .catch((err) => {
        setGroupsError(err instanceof ApiError ? err.message : "Не удалось загрузить список групп");
        setGroupsLoaded(true);
      });
  }

  useEffect(() => {
    loadGroups();
    api.get<MarkCodeOption[]>("/curator/mark-codes").then(setMarkCodes);
    api
      .get<{ risk_threshold_consecutive_unexcused: number }>("/curator/settings")
      .then((s) => setRiskThreshold(s.risk_threshold_consecutive_unexcused))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadRoster = useCallback(async () => {
    if (!groupId) return;
    setError(null);
    try {
      const r = await api.get<RosterResponse>(`/curator/groups/${groupId}/day?date=${date}`);
      setRoster(r);
      setFirstPeriod(r.first_period != null ? String(r.first_period) : "");
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

  const loadMonthStatus = useCallback(() => {
    if (!groupId) return;
    const [year, month] = date.split("-").map(Number);
    api
      .get<MonthDayStatus[]>(`/curator/groups/${groupId}/month-status?year=${year}&month=${month}`)
      .then(setMonthStatus)
      .catch(() => setMonthStatus([]));
    // Ритм группы (посещаемость за три недели) обновляется вместе с полосой месяца — после сдачи дня тоже.
    api
      .get<MyDayRhythmDay[]>(`/curator/groups/${groupId}/rhythm`)
      .then((r) => setRhythm(Array.isArray(r) ? r : []))
      .catch(() => setRhythm([]));
  }, [groupId, date]);

  useEffect(() => {
    loadMonthStatus();
  }, [loadMonthStatus]);

  const markCodeByCode = useMemo(() => new Map(markCodes.map((m) => [m.code, m])), [markCodes]);
  const selectedDayType = monthStatus.find((d) => d.date === date)?.day_type;
  const isNonWorkingDay = selectedDayType != null && ["weekend", "holiday", "vacation"].includes(selectedDayType);
  const absentCount = Object.values(pending).length;

  // Групп много (весь колледж) — список режется по отделению: сначала отделение, потом группа.
  const departments = useMemo(() => {
    const byId = new Map<number, { id: number; name: string; count: number }>();
    for (const g of groups) {
      if (g.departmentId == null || !g.departmentName) continue;
      const d = byId.get(g.departmentId) ?? { id: g.departmentId, name: g.departmentName, count: 0 };
      d.count += 1;
      byId.set(g.departmentId, d);
    }
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name, "ru"));
  }, [groups]);
  const showDepartments = departments.length > 1;
  const activeDepartment = departmentChoice ?? groups.find((g) => g.id === groupId)?.departmentId ?? null;
  const visibleGroups =
    showDepartments && activeDepartment != null ? groups.filter((g) => g.departmentId === activeDepartment) : groups;

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
        ? `/curator/groups/${groupId}/day/mark-all-present?date=${date}${confirmed ? "&confirm=true" : ""}${firstPeriod ? `&first_period=${firstPeriod}` : ""}`
        : `/curator/groups/${groupId}/day/submit?date=${date}`;
      const body = allPresent
        ? undefined
        : {
            first_period: firstPeriod ? Number(firstPeriod) : null,
            exceptions: Object.entries(pending).map(([studentId, p]) => ({
              student_id: Number(studentId),
              mark_code: p.mark_code,
              comment: p.comment || null,
              basis_reference: p.basis_reference || null,
            })),
          };
      const updated = await api.post<RosterResponse>(path, body);
      setRoster(updated);
      setFirstPeriod(updated.first_period != null ? String(updated.first_period) : "");
      // Иначе полоска месяца и пометка "не сдано сегодня" в списке групп
      // остаются устаревшими до следующей смены даты/группы (см. TODO.md 4).
      loadMonthStatus();
      loadGroups();
      scrollToTop();
    } catch (err) {
      // Сервер отказывает с 409, если "Все присутствуют" стёрло бы уже
      // внесённые отметки (см. TODO.md 1.8) — переспрашиваем вместо того,
      // чтобы просто показать ошибку.
      if (err instanceof ApiError && err.status === 409 && allPresent && !confirmed) {
        if (await dialogs.confirm(`${err.message}\n\nВсё равно отметить всех присутствующими?`, { confirmLabel: "Отметить всех" })) {
          setBusy(false);
          await submitDay(true, true);
          return;
        }
      } else {
        setError(err instanceof ApiError ? err.message : submitErrorText);
      }
      scrollToTop();
    } finally {
      setBusy(false);
    }
  }

  if (!groupsLoaded) {
    return <p className="hint">Загрузка…</p>;
  }
  if (groupsError) {
    return <div className="error-text">{groupsError}</div>;
  }
  if (groups.length === 0) {
    return <p>{emptyText}</p>;
  }

  return (
    <div>
      <div className="roster-sticky-header">
        <div className="toolbar">
          {showDepartments && (
            <select
              aria-label="Отделение"
              title="Отделение: группы в списке справа — только из него"
              value={activeDepartment ?? ""}
              onChange={async (e) => {
                const next = Number(e.target.value);
                if (absentCount > 0 && !(await dialogs.confirm("Несохранённые изменения будут потеряны. Сменить отделение?", { confirmLabel: "Сменить отделение" }))) return;
                setDepartmentChoice(next);
                const first = groups.find((g) => g.departmentId === next);
                if (first) setGroupId(first.id);
              }}
            >
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} ({d.count})
                </option>
              ))}
            </select>
          )}
          <SearchSelect
            value={groupId === null || groupId === undefined ? "" : String(groupId)}
            options={visibleGroups.map((g) => ({ value: String(g.id), label: g.label }))}
            ariaLabel="Группа"
            title="Группа: начните вводить код, например «ГД»"
            onChange={async (v) => {
              if (absentCount > 0 && !(await dialogs.confirm("Несохранённые изменения будут потеряны. Сменить группу?", { confirmLabel: "Сменить группу" }))) return;
              setGroupId(Number(v));
            }}
          />
          <input
            type="date"
            aria-label="Дата"
            value={date}
            max={todayIso()}
            onChange={async (e) => {
              const next = e.target.value;
              if (absentCount > 0 && !(await dialogs.confirm("Несохранённые изменения будут потеряны. Сменить дату?", { confirmLabel: "Сменить дату" }))) return;
              setDate(next);
            }}
          />
          <button type="button" className="link-btn" onClick={() => setListOpen(true)} title="Список группы для печати (Word): выберите столбцы">
            Список для печати
          </button>
        </div>

        <div className="month-strip">
          {monthStatus.map((d) => (
            <span
              key={d.date}
              title={`${d.date} — ${MONTH_DOT_TITLES[d.day_type] ?? d.day_type}`}
              tabIndex={0}
              role="button"
              aria-label={`${d.date}, ${MONTH_DOT_TITLES[d.day_type] ?? d.day_type}`}
              className={`month-dot ${
                ["weekend", "holiday", "vacation"].includes(d.day_type)
                  ? "weekend"
                  : d.is_submitted
                    ? (d.is_on_time ? "ok" : "late")
                    : "missing"
              } ${d.day_type === "remote" ? "remote-day" : ""} ${d.date === date ? "selected" : ""}`}
              onClick={() => setDate(d.date)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") setDate(d.date);
              }}
            />
          ))}
        </div>
        <p className="hint month-strip-legend">
          <span className="legend-dot ok" /> вовремя <span className="legend-dot late" /> задним числом{" "}
          <span className="legend-dot missing" /> не сдано <span className="legend-dot weekend" /> нерабочий
        </p>
      </div>

      {rhythm.length > 0 && (
        <div className="journal-rhythm">
          <span className="hint">Ритм группы за три недели</span>
          <GroupRhythm days={rhythm} />
        </div>
      )}

      {error && <div className="error-text">{error}</div>}

      {roster && isNonWorkingDay && (
        <div className="day-status weekend">Нерабочий день — отмечать посещаемость не нужно</div>
      )}

      {roster && !isNonWorkingDay && (
        <>
          <div className={`day-status ${roster.is_submitted ? "submitted" : "not-submitted"}`}>
            {roster.is_submitted
              ? `День сдан${roster.is_on_time === false ? " (задним числом)" : ""}`
              : notSubmittedText}
          </div>

          <DayActionsBar
            absentCount={absentCount}
            busy={busy}
            firstPeriod={firstPeriod}
            onFirstPeriodChange={setFirstPeriod}
            submitLabel={submitLabel}
            onAllPresent={async () => {
              if (
                absentCount > 0 &&
                !(await dialogs.confirm(`Отметки отсутствующих (${absentCount}) будут сброшены. Отметить всех присутствующими?`, {
                  confirmLabel: "Отметить всех",
                }))
              )
                return;
              submitDay(true);
            }}
            onSubmit={() => submitDay(false)}
          />

          <p className="hint mark-code-legend">
            {markCodes.map((m) => (
              <span key={m.code}>
                <b>{m.code.toUpperCase()}</b> — {m.name}
              </span>
            ))}
          </p>

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
                const risky = entry.risk_streak >= riskThreshold;
                const hasComment = Boolean(current?.comment || current?.basis_reference);
                return (
                  <tr key={entry.student_id} className={risky ? "risk-row" : ""}>
                    <td data-label="ФИО">
                      <Link to={`/students/${entry.student_id}`} className="link-btn">
                        {entry.full_name}
                      </Link>
                    </td>
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

        </>
      )}

      {listOpen && groupId !== null && (
        <GroupListModal
          groupId={groupId}
          groupCode={(groups.find((g) => g.id === groupId)?.label ?? "").split(" ")[0]}
          onClose={() => setListOpen(false)}
        />
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
          lastEditedInfo={showLastEdited ? lastEditedInfo(roster, showCommentFor) : undefined}
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

function lastEditedInfo(roster: RosterResponse | null, studentId: number): string | null {
  const entry = roster?.entries.find((e) => e.student_id === studentId);
  if (!entry?.last_edited_by) return null;
  return entry.last_edited_at ? `${entry.last_edited_by}, ${formatServerDateTime(entry.last_edited_at)}` : entry.last_edited_by;
}
