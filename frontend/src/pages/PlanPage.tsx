import { useCallback, useEffect, useState } from "react";
import { api, ApiError, downloadFile } from "../api/client";
import type { GroupEvent, GroupMeetings, GroupPlan, ParentMeeting } from "../api/types";
import AttendanceModal from "../components/AttendanceModal";
import EventForm from "../components/EventForm";
import MeetingForm from "../components/MeetingForm";
import ParentsAttendanceModal from "../components/ParentsAttendanceModal";
import SearchSelect from "../components/SearchSelect";
import { TabBar } from "../components/Tabs";
import { useGroupParams } from "../hooks/useGroupParams";
import { EVENT_STATUSES } from "../constants/eventStatuses";
import { formatDateRu } from "../utils/date";
import { dialogs } from "../utils/feedback";

interface GroupOption {
  id: number;
  code: string;
  course: number;
}

// План воспитательной работы группы: мероприятия по разделам бланка колледжа, отметка о выполнении, классные часы
// с присутствующими. Выгрузка в Word — план группы, план куратора, протокол классного часа.
// Подвкладки «Мероприятия» и «Родительские собрания», мероприятия — с фильтром по разделу бланка, чтобы
// страница не была одной длинной лентой. `fixedGroupId` — вкладка на странице группы куратора.
export default function PlanPage({ fixedGroupId }: { fixedGroupId?: number } = {}) {
  const { params: searchParams, groupId, update } = useGroupParams(fixedGroupId);
  const [groups, setGroups] = useState<GroupOption[] | null>(null);
  const [plan, setPlan] = useState<GroupPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ event: GroupEvent | null; section: string } | null>(null);
  const [attendance, setAttendance] = useState<GroupEvent | null>(null);
  const [meetings, setMeetings] = useState<GroupMeetings | null>(null);
  const [meetingForm, setMeetingForm] = useState<{ meeting: ParentMeeting | null } | null>(null);
  const [parentsOf, setParentsOf] = useState<ParentMeeting | null>(null);
  const year = searchParams.get("year");
  const part = searchParams.get("part") === "meetings" ? "meetings" : "events";
  const sectionFilter = searchParams.get("section") ?? "all";

  useEffect(() => {
    if (fixedGroupId != null) {
      setGroups([]);
      return;
    }
    api
      .get<GroupOption[]>("/individual-work/groups")
      .then((list) => {
        setGroups(list);
        if (!groupId && list.length > 0) update({ group: String(list[0].id) }, { replace: true });
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Не удалось загрузить список групп");
        setGroups([]);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(() => {
    if (!groupId) return;
    api
      .get<GroupPlan>(`/events/groups/${groupId}${year ? `?year=${year}` : ""}`)
      .then((p) => {
        setPlan(p);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить план"));
  }, [groupId, year]);

  useEffect(load, [load]);

  const loadMeetings = useCallback(() => {
    if (!groupId) return;
    api
      .get<GroupMeetings>(`/meetings/groups/${groupId}${year ? `?year=${year}` : ""}`)
      .then(setMeetings)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить родительские собрания"));
  }, [groupId, year]);

  useEffect(loadMeetings, [loadMeetings]);

  function download(path: string, filename: string) {
    downloadFile(path, filename).catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось сформировать документ"));
  }

  async function remove(event: GroupEvent) {
    if (!(await dialogs.confirm(`Удалить мероприятие «${event.title}»?`, { confirmLabel: "Удалить", danger: true }))) return;
    try {
      await api.delete(`/events/${event.id}`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить мероприятие");
    }
  }

  async function removeMeeting(m: ParentMeeting) {
    if (!(await dialogs.confirm(`Удалить родительское собрание №${m.number}?`, { confirmLabel: "Удалить", danger: true }))) return;
    try {
      await api.delete(`/meetings/${m.id}`);
      loadMeetings();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить собрание");
    }
  }

  if (groups === null) return <p className="hint">Загрузка…</p>;
  if (fixedGroupId == null && groups.length === 0) return <p>{error ?? "Нет доступных групп."}</p>;

  const current = plan && String(plan.group_id) === groupId ? plan : null;

  return (
    <div>
      <div className="toolbar">
        {fixedGroupId == null && (
          <SearchSelect
            value={groupId ?? ""}
            options={groups.map((g) => ({ value: String(g.id), label: `${g.code} (курс ${g.course})` }))}
            onChange={(v) => update({ group: v, year: null, section: null })}
            ariaLabel="Группа"
            title="Группа: начните вводить код, например «ГД»"
          />
        )}
        {current && (
          <select
            aria-label="Учебный год"
            value={current.school_year}
            onChange={(e) => update({ year: e.target.value })}
          >
            {current.years.map((y) => (
              <option key={y} value={y}>
                {y.replace("-", "/")} уч. год
              </option>
            ))}
          </select>
        )}
      </div>
      {error && <div className="error-text">{error}</div>}
      {!current ? (
        !error && <p className="hint">Загрузка…</p>
      ) : (
        <>
          <div className="toolbar">
            {current.can_edit && (
              <button type="button" onClick={() => setEditing({ event: null, section: sectionFilter !== "all" ? sectionFilter : current.sections[0].key })}>
                Добавить мероприятие
              </button>
            )}
            <button
              type="button"
              className="btn-secondary"
              title="План воспитательной работы учебной группы — бланк колледжа"
              onClick={() => download(`/events/groups/${current.group_id}/plan.docx?kind=group&year=${current.school_year}`, `План_группы_${current.group_code}.docx`)}
            >
              План группы в Word
            </button>
            <button
              type="button"
              className="btn-secondary"
              title="План воспитательной работы куратора — бланк колледжа с подписями"
              onClick={() => download(`/events/groups/${current.group_id}/plan.docx?kind=curator&year=${current.school_year}`, `План_куратора_${current.group_code}.docx`)}
            >
              План куратора в Word
            </button>
          </div>
          <TabBar
            tabs={[
              { key: "events", label: "Мероприятия", badge: current.events.length || undefined },
              { key: "meetings", label: "Родительские собрания", badge: meetings?.meetings.length || undefined },
            ]}
            active={part}
            onChange={(key) => update({ part: key === "events" ? null : key }, { replace: true })}
            label="Разделы плана"
            idPrefix="plan"
            variant="sub"
          />
          {part === "events" && (
            <>
              <p className="hint">
                Мероприятия по разделам бланка колледжа. Отметьте проведённое и результат — в Word попадёт всё как в бланке; для
                классного часа отметьте присутствующих и скачайте протокол.
              </p>
              <div className="chip-filter" role="group" aria-label="Раздел бланка">
                <button
                  type="button"
                  className={`chip-filter__item${sectionFilter === "all" ? " is-active" : ""}`}
                  aria-pressed={sectionFilter === "all"}
                  onClick={() => update({ section: null }, { replace: true })}
                >
                  Все разделы
                </button>
                {current.sections.map((section) => {
                  const count = current.events.filter((e) => e.section === section.key).length;
                  return (
                    <button
                      key={section.key}
                      type="button"
                      className={`chip-filter__item${sectionFilter === section.key ? " is-active" : ""}`}
                      aria-pressed={sectionFilter === section.key}
                      onClick={() => update({ section: section.key }, { replace: true })}
                    >
                      {section.title}
                      {count > 0 && <span className="chip-filter__count">{count}</span>}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          {part === "events" && current.sections
            .filter((section) =>
              sectionFilter === "all" ? current.events.some((e) => e.section === section.key) : section.key === sectionFilter
            )
            .map((section) => {
            const items = current.events.filter((e) => e.section === section.key);
            return (
              <section key={section.key} className="plan-section">
                <h3 className="student-card__section">
                  {section.title} <span className="hint">({items.length})</span>
                </h3>
                {items.length === 0 ? (
                  current.can_edit && (
                    <p>
                      <button type="button" className="link-btn" onClick={() => setEditing({ event: null, section: section.key })}>
                        + Добавить в раздел
                      </button>
                    </p>
                  )
                ) : (
                  <>
                    <div className="table-scroll">
                      <table className="dash-table roster-table">
                        <thead>
                          <tr>
                            <th>Дата</th>
                            <th>Мероприятие</th>
                            <th>Ответственные</th>
                            <th>Результат</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {items.map((e) => (
                            <tr key={e.id}>
                              <td data-label="Дата">
                                {e.event_date ? formatDateRu(e.event_date) : "—"}
                                {e.time_text ? <div className="hint">{e.time_text}</div> : null}
                              </td>
                              <td data-label="Мероприятие">
                                {e.title}
                                {e.is_class_hour && <span className="chip"> классный час</span>}
                                {e.goal && <div className="hint">Цель: {e.goal}</div>}
                              </td>
                              <td data-label="Ответственные">{e.responsible ?? "—"}</td>
                              <td data-label="Результат">
                                <b>{EVENT_STATUSES[e.status] ?? e.status}</b>
                                {e.result && <div className="hint">{e.result}</div>}
                                {e.is_class_hour && (
                                  <div className="hint">
                                    Присутствовало: {e.attendee_ids.length > 0 ? `${e.attendee_ids.length} из ${current.students.length}` : "не отмечено"}
                                  </div>
                                )}
                              </td>
                              <td data-label="Действия">
                                {current.can_edit && (
                                  <button type="button" className="link-btn" onClick={() => setEditing({ event: e, section: e.section })}>
                                    Изменить
                                  </button>
                                )}{" "}
                                {e.is_class_hour && current.can_edit && (
                                  <button type="button" className="link-btn" onClick={() => setAttendance(e)}>
                                    Присутствующие
                                  </button>
                                )}{" "}
                                {e.is_class_hour && (
                                  <button
                                    type="button"
                                    className="link-btn"
                                    onClick={() => download(`/events/${e.id}/protocol.docx`, `Протокол_классного_часа_${current.group_code}.docx`)}
                                  >
                                    Протокол в Word
                                  </button>
                                )}{" "}
                                {current.can_edit && (
                                  <button type="button" className="link-btn" onClick={() => remove(e)}>
                                    Удалить
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {current.can_edit && (
                      <p>
                        <button type="button" className="link-btn" onClick={() => setEditing({ event: null, section: section.key })}>
                          + Добавить в раздел
                        </button>
                      </p>
                    )}
                  </>
                )}
              </section>
            );
          })}
          {part === "events" && sectionFilter === "all" && (
            <p className="hint plan-empty-sections">
              {current.events.length === 0
                ? "Мероприятий в этом учебном году ещё нет — выберите раздел выше или нажмите «Добавить мероприятие»."
                : `Разделов без мероприятий: ${current.sections.filter((s) => !current.events.some((e) => e.section === s.key)).length} — их можно открыть кнопками выше.`}
            </p>
          )}
          {part === "meetings" && (
          <section className="plan-section">
            <h3 className="student-card__section">
              Родительские собрания <span className="hint">({meetings?.meetings.length ?? 0})</span>
            </h3>
            {meetings && meetings.school_year === current.school_year && (
              <>
                {meetings.meetings.length === 0 ? (
                  <p className="hint">В этом учебном году собраний ещё нет.</p>
                ) : (
                  <div className="table-scroll">
                    <table className="dash-table roster-table">
                      <thead>
                        <tr>
                          <th>№</th>
                          <th>Дата</th>
                          <th>Повестка</th>
                          <th>Родителей</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {meetings.meetings.map((m) => (
                          <tr key={m.id}>
                            <td data-label="№">{m.number}</td>
                            <td data-label="Дата">
                              {m.meeting_date ? formatDateRu(m.meeting_date) : "—"}
                              <div className="hint">{m.meeting_format === "remote" ? "дистанционно" : "очно"}</div>
                            </td>
                            <td data-label="Повестка" style={{ whiteSpace: "pre-wrap" }}>
                              {m.agenda ?? "—"}
                            </td>
                            <td data-label="Родителей">
                              {m.attendee_ids.length > 0 ? m.attendee_ids.length : (m.parents_count ?? "не указано")}
                            </td>
                            <td data-label="Действия">
                              {current.can_edit && (
                                <button type="button" className="link-btn" onClick={() => setMeetingForm({ meeting: m })}>
                                  Изменить
                                </button>
                              )}{" "}
                              {current.can_edit && (
                                <button type="button" className="link-btn" onClick={() => setParentsOf(m)}>
                                  Присутствующие родители
                                </button>
                              )}{" "}
                              <button
                                type="button"
                                className="link-btn"
                                onClick={() => download(`/meetings/${m.id}/protocol.docx`, `Протокол_родительского_собрания_${current.group_code}.docx`)}
                              >
                                Протокол собрания в Word
                              </button>{" "}
                              {current.can_edit && (
                                <button type="button" className="link-btn" onClick={() => removeMeeting(m)}>
                                  Удалить собрание
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {current.can_edit && (
                  <p>
                    <button type="button" className="link-btn" onClick={() => setMeetingForm({ meeting: null })}>
                      + Добавить родительское собрание
                    </button>
                  </p>
                )}
              </>
            )}
          </section>
          )}
          {meetingForm && (
            <MeetingForm
              groupId={current.group_id}
              year={current.school_year}
              meeting={meetingForm.meeting}
              onSaved={() => {
                setMeetingForm(null);
                loadMeetings();
              }}
              onClose={() => setMeetingForm(null)}
            />
          )}
          {parentsOf && meetings && (
            <ParentsAttendanceModal
              meeting={parentsOf}
              guardians={meetings.guardians}
              onSaved={() => {
                setParentsOf(null);
                loadMeetings();
              }}
              onClose={() => setParentsOf(null)}
            />
          )}
          {editing && (
            <EventForm
              groupId={current.group_id}
              year={current.school_year}
              sections={current.sections}
              event={editing.event}
              defaultSection={editing.section}
              onSaved={() => {
                setEditing(null);
                load();
              }}
              onClose={() => setEditing(null)}
            />
          )}
          {attendance && (
            <AttendanceModal
              event={attendance}
              students={current.students}
              onSaved={() => {
                setAttendance(null);
                load();
              }}
              onClose={() => setAttendance(null)}
            />
          )}
        </>
      )}
    </div>
  );
}
