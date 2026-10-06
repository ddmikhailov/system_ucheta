import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import AbsencePeriodModal from "./AbsencePeriodModal";
import DayActionsBar from "./DayActionsBar";
import MarkCodeButtons from "./MarkCodeButtons";
import MarkCommentModal from "./MarkCommentModal";
import { scrollToTop } from "../utils/scroll";
import type { MarkCodeOption, MonthDayStatus, MyDayRhythmDay, RosterResponse } from "../api/types";
import { formatServerDateTime, todayIso } from "../utils/date";
import SearchSelect from "./SearchSelect";
import { dialogs, toast } from "../utils/feedback";
import GroupListModal from "./GroupListModal";
import StudentCardModal from "./StudentCardModal";
import GroupRhythm from "./GroupRhythm";
import { formatPercent } from "../utils/percent";
import DayNavigator from "./journal/DayNavigator";
import DaySummary from "./journal/DaySummary";
import ChangeCard from "./journal/ChangeCard";

const NON_WORKING = ["weekend", "holiday", "vacation"];

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
  /** Журнал одной группы (страница группы у куратора): без выбора отделения и группы. */
  fixedGroupId?: number;
  /** Кнопки «Список для печати» и «Личные карточки» в шапке журнала. */
  showGroupTools?: boolean;
  /** Пользователь решает исправления прошлых дней (зав. отделением, тьютор, админ). */
  canReview?: boolean;
  /** День сдан или изменён — например, чтобы обновить «сегодня сдано» в шапке группы. */
  onSubmitted?: () => void;
}

function pendingFrom(r: RosterResponse): Record<number, PendingMark> {
  const result: Record<number, PendingMark> = {};
  for (const entry of r.entries) {
    if (entry.mark_code && !entry.is_locked) {
      result[entry.student_id] = { mark_code: entry.mark_code, comment: entry.comment ?? "", basis_reference: entry.basis_reference ?? "" };
    }
  }
  return result;
}

/** Общий журнал дня: выбор группы и дня, календарь месяца, итоги сданного дня или форма отметок.
 * Сданный день показывается итогами; «Редактировать» открывает форму. Правка куратором уже сданного
 * прошлого дня уходит на проверку зав. отделением (запрос с причиной), а не сразу в журнал. */
export default function DayJournal({
  fetchGroups,
  emptyText,
  notSubmittedText,
  submitLabel,
  submitErrorText,
  showLastEdited = false,
  fixedGroupId,
  showGroupTools = true,
  canReview = false,
  onSubmitted,
}: DayJournalProps) {
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const deepLinkGroupId = searchParams.get("group");
  const deepLinkDate = searchParams.get("date");
  const today = todayIso();

  const [groups, setGroups] = useState<JournalGroup[]>([]);
  const [groupId, setGroupId] = useState<number | null>(fixedGroupId ?? (deepLinkGroupId ? Number(deepLinkGroupId) : null));
  const [listOpen, setListOpen] = useState(false);
  const [cardsOpen, setCardsOpen] = useState(false);
  const [date, setDate] = useState(deepLinkDate && deepLinkDate <= today ? deepLinkDate : today);
  const [roster, setRoster] = useState<RosterResponse | null>(null);
  const [markCodes, setMarkCodes] = useState<MarkCodeOption[]>([]);
  const [pending, setPending] = useState<Record<number, PendingMark>>({});
  const [editing, setEditing] = useState(false);
  const [monthStatus, setMonthStatus] = useState<MonthDayStatus[]>([]);
  const [rhythm, setRhythm] = useState<MyDayRhythmDay[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPeriodForm, setShowPeriodForm] = useState<number | null>(null);
  const [showCommentFor, setShowCommentFor] = useState<number | null>(null);
  const [groupsLoaded, setGroupsLoaded] = useState(false);
  const [groupsError, setGroupsError] = useState<string | null>(null);
  const [riskPercent, setRiskPercent] = useState(85);
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
      .get<{ risk_attendance_percent: number }>("/curator/settings")
      .then((s) => setRiskPercent(s.risk_attendance_percent))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyRoster = useCallback((r: RosterResponse) => {
    setRoster(r);
    setFirstPeriod(r.first_period != null ? String(r.first_period) : "");
    setPending(pendingFrom(r));
    setEditing(false);
  }, []);

  const loadRoster = useCallback(async () => {
    if (!groupId) return;
    setError(null);
    try {
      applyRoster(await api.get<RosterResponse>(`/curator/groups/${groupId}/day?date=${date}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось загрузить день");
    }
  }, [groupId, date, applyRoster]);

  useEffect(() => {
    loadRoster();
  }, [loadRoster]);

  const month = date.slice(0, 7);
  const loadMonthStatus = useCallback(() => {
    if (!groupId) return;
    const [year, m] = month.split("-").map(Number);
    api
      .get<MonthDayStatus[]>(`/curator/groups/${groupId}/month-status?year=${year}&month=${m}`)
      .then(setMonthStatus)
      .catch(() => setMonthStatus([]));
    // Ритм группы (посещаемость за три недели) обновляется вместе с календарём — после сдачи дня тоже.
    api
      .get<MyDayRhythmDay[]>(`/curator/groups/${groupId}/rhythm`)
      .then((r) => setRhythm(Array.isArray(r) ? r : []))
      .catch(() => setRhythm([]));
  }, [groupId, month]);

  useEffect(() => {
    loadMonthStatus();
  }, [loadMonthStatus]);

  const markCodeByCode = useMemo(() => new Map(markCodes.map((m) => [m.code, m])), [markCodes]);
  const selectedDayType = monthStatus.find((d) => d.date === date)?.day_type;
  const isNonWorkingDay = selectedDayType != null && NON_WORKING.includes(selectedDayType);
  const absentCount = Object.values(pending).length;
  // Есть несохранённые правки: форма открыта и отличается от загруженного дня.
  const dirty = !!roster && (editing || !roster.is_submitted) && JSON.stringify(pending) !== JSON.stringify(pendingFrom(roster));

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
  const showDepartments = !fixedGroupId && departments.length > 1;
  const activeDepartment = departmentChoice ?? groups.find((g) => g.id === groupId)?.departmentId ?? null;
  const visibleGroups =
    showDepartments && activeDepartment != null ? groups.filter((g) => g.departmentId === activeDepartment) : groups;
  const groupCode = (groups.find((g) => g.id === groupId)?.label ?? "").split(" ")[0];

  async function confirmLeave(what: string): Promise<boolean> {
    if (!dirty) return true;
    return dialogs.confirm(`Несохранённые изменения будут потеряны. ${what}?`, { confirmLabel: what });
  }

  async function changeDate(next: string) {
    if (next === date || next > today) return;
    if (!(await confirmLeave("Сменить дату"))) return;
    setDate(next);
  }

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

  const exceptions = (allPresent: boolean) =>
    allPresent
      ? []
      : Object.entries(pending).map(([studentId, p]) => ({
          student_id: Number(studentId),
          mark_code: p.mark_code,
          comment: p.comment || null,
          basis_reference: p.basis_reference || null,
        }));

  // Куратор правит сданный прошлый день: не в журнал, а запросом на проверку с причиной.
  async function requestChange(allPresent: boolean) {
    if (!groupId) return;
    const reason = await dialogs.prompt(
      "Почему нужно исправить уже сданный день? Исправление увидит и одобрит зав. отделением.",
      "",
      { confirmLabel: "Отправить на проверку" }
    );
    if (reason === null) return;
    if (reason.trim().length < 3) {
      setError("Напишите причину исправления (хотя бы несколько слов)");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      applyRoster(
        await api.post<RosterResponse>(`/curator/groups/${groupId}/day/change-request?date=${date}`, {
          exceptions: exceptions(allPresent),
          first_period: firstPeriod ? Number(firstPeriod) : null,
          reason: reason.trim(),
        })
      );
      toast("Исправление отправлено на проверку зав. отделением");
      scrollToTop();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отправить исправление");
    } finally {
      setBusy(false);
    }
  }

  async function submitDay(allPresent: boolean, confirmed = false) {
    if (!groupId) return;
    if (roster?.edit_requires_review) {
      await requestChange(allPresent);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const path = allPresent
        ? `/curator/groups/${groupId}/day/mark-all-present?date=${date}${confirmed ? "&confirm=true" : ""}${firstPeriod ? `&first_period=${firstPeriod}` : ""}`
        : `/curator/groups/${groupId}/day/submit?date=${date}`;
      const body = allPresent ? undefined : { first_period: firstPeriod ? Number(firstPeriod) : null, exceptions: exceptions(false) };
      applyRoster(await api.post<RosterResponse>(path, body));
      // Иначе календарь и пометка «не сдано сегодня» в списке групп остаются устаревшими (см. TODO.md 4).
      loadMonthStatus();
      if (!fixedGroupId) loadGroups();
      onSubmitted?.();
      scrollToTop();
    } catch (err) {
      // Сервер отказывает с 409, если «Все присутствуют» стёрло бы уже внесённые отметки (см. TODO.md 1.8).
      if (err instanceof ApiError && err.status === 409 && allPresent && !confirmed && !err.message.includes("проверку")) {
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

  const reviewMode = !!roster?.edit_requires_review;
  const showForm = !!roster && !isNonWorkingDay && (!roster.is_submitted || editing);
  const pendingChange = roster?.pending_change ?? null;
  const lastChange = roster?.last_change ?? null;

  return (
    <div className="journal">
      {(!fixedGroupId || showGroupTools) && (
        <div className="journal__toolbar toolbar">
          {showDepartments && (
            <select
              aria-label="Отделение"
              title="Отделение: группы в списке справа — только из него"
              value={activeDepartment ?? ""}
              onChange={async (e) => {
                const next = Number(e.target.value);
                if (!(await confirmLeave("Сменить отделение"))) return;
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
          {!fixedGroupId && (
            <SearchSelect
              value={groupId === null || groupId === undefined ? "" : String(groupId)}
              options={visibleGroups.map((g) => ({ value: String(g.id), label: g.label }))}
              ariaLabel="Группа"
              title="Группа: начните вводить код, например «ГД»"
              onChange={async (v) => {
                if (!(await confirmLeave("Сменить группу"))) return;
                setGroupId(Number(v));
              }}
            />
          )}
          {showGroupTools && (
            <span className="journal__tools">
              <button type="button" className="btn-secondary" onClick={() => setListOpen(true)} title="Список группы для печати (Word): выберите столбцы">
                Список для печати
              </button>
              <button type="button" className="btn-secondary" onClick={() => setCardsOpen(true)} title="Личные карточки всей группы в Word (бланк колледжа): выберите поля">
                Личные карточки
              </button>
            </span>
          )}
        </div>
      )}

      <div className="journal__layout">
        <aside className="journal__side">
          <DayNavigator date={date} today={today} monthStatus={monthStatus} onChange={changeDate} />
          {rhythm.length > 0 && (
            <div className="journal-rhythm">
              <span className="hint">Ритм группы за три недели</span>
              <GroupRhythm days={rhythm} />
            </div>
          )}
        </aside>

        <div className="journal__main">
          {error && <div className="error-text">{error}</div>}

          {pendingChange && (
            <ChangeCard
              change={pendingChange}
              canCancel={pendingChange.requested_by_id === user?.id}
              canReview={canReview}
              onDone={() => {
                loadRoster();
                loadMonthStatus();
              }}
            />
          )}
          {!pendingChange && lastChange && lastChange.status === "rejected" && <ChangeCard change={lastChange} onDone={loadRoster} />}

          {roster && isNonWorkingDay && <div className="day-status weekend">Нерабочий день — отмечать посещаемость не нужно</div>}

          {roster && !isNonWorkingDay && roster.is_submitted && !editing && (
            <DaySummary
              roster={roster}
              markCodes={markCodes}
              editLabel={reviewMode ? "Предложить исправление" : "Редактировать"}
              editDisabled={!!pendingChange && pendingChange.requested_by_id !== user?.id && reviewMode}
              onEdit={() => setEditing(true)}
            />
          )}

          {showForm && roster && (
            <>
              <div className={`day-status ${roster.is_submitted ? "submitted" : "not-submitted"}`}>
                {roster.is_submitted
                  ? reviewMode
                    ? "Исправление сданного дня — уйдёт на проверку зав. отделением, журнал изменится после одобрения"
                    : "Правка сданного дня"
                  : notSubmittedText}
                {roster.is_submitted && (
                  <button
                    type="button"
                    className="link-btn day-status__action"
                    onClick={async () => {
                      if (!(await confirmLeave("Отменить правку"))) return;
                      setPending(pendingFrom(roster));
                      setFirstPeriod(roster.first_period != null ? String(roster.first_period) : "");
                      setEditing(false);
                    }}
                  >
                    Отменить
                  </button>
                )}
              </div>

              <DayActionsBar
                absentCount={absentCount}
                busy={busy}
                firstPeriod={firstPeriod}
                onFirstPeriodChange={setFirstPeriod}
                submitLabel={reviewMode ? "Отправить на проверку" : roster.is_submitted ? "Сохранить изменения" : submitLabel}
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

              <table className="roster-table compact-cards journal-roster">
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
                    const risky = entry.is_risk;
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
                            <MarkCodeButtons value={code} markCodes={markCodes} onChange={(c) => setStudentMark(entry.student_id, c)} />
                          )}
                          {entry.is_draft_suggestion && !entry.is_locked && <span className="draft-badge">черновик со вчера</span>}
                          {risky && (
                            <span className="risk-badge" title={`Группа риска: посещаемость с начала семестра ниже ${riskPercent} %`}>
                              риск: посещаемость {formatPercent(entry.attendance_percent)}
                            </span>
                          )}
                        </td>
                        <td data-label="Комментарий">
                          {!entry.is_locked && code && (
                            <button className="comment-btn" onClick={() => setShowCommentFor(entry.student_id)}>
                              {hasComment ? "Комментарий добавлен" : "Добавить комментарий"}
                            </button>
                          )}
                        </td>
                        <td>
                          {!entry.is_locked && !reviewMode && (
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
        </div>
      </div>

      {listOpen && groupId !== null && <GroupListModal groupId={groupId} groupCode={groupCode} onClose={() => setListOpen(false)} />}

      {cardsOpen && groupId !== null && (
        <StudentCardModal
          endpoint={`/curator/groups/${groupId}/cards`}
          heading={`Личные карточки группы ${groupCode}`}
          filename={`Личные_карточки_${groupCode}.docx`}
          onClose={() => setCardsOpen(false)}
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
