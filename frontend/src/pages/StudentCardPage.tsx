import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { DOSSIER_AUDIT_ROLES, DOSSIER_STAFF_ROLES, STRUCTURE_EDITOR_ROLES, TEACHER_ROLES, inRoles } from "../constants/roles";
import { STUDENT_STATUS_LABELS } from "../constants/studentStatus";
import StudentDossier from "../components/StudentDossier";
import StudentMonthAttendanceView from "../components/StudentMonthAttendance";
import { useScrollToTopOnChange } from "../hooks/useScrollToTopOnChange";
import type { DeleteResult, StudentCard, StudyGroupAdmin } from "../api/types";
import { formatDateRu, todayIso } from "../utils/date";

// Личная карточка студента: вся информация на одном экране и всё управление
// им (правка ФИО, перевод в другую группу, статус обучения, удаление).
// Управлять могут админ/тьютор и зав. отделением своего отделения, остальные
// управленческие роли видят карточку только для чтения.
export default function StudentCardPage() {
  const { studentId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canManage = inRoles(user?.role, STRUCTURE_EDITOR_ROLES);

  const [card, setCard] = useState<StudentCard | null>(null);
  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useScrollToTopOnChange(error, notice);

  const load = useCallback(() => {
    api
      .get<StudentCard>(`/students/${studentId}`)
      .then((c) => {
        setCard(c);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить карточку"));
  }, [studentId]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!canManage) return;
    api
      .get<StudyGroupAdmin[]>("/admin/groups")
      .then((all) => setGroups(all.filter((g) => g.is_active)))
      .catch(() => {});
  }, [canManage]);

  // Администрация возвращается в список студентов, куратор — в свой кабинет.
  const isTeacher = inRoles(user?.role, TEACHER_ROLES);
  const isStaff = inRoles(user?.role, DOSSIER_STAFF_ROLES);
  const back = (
    <p>
      <Link to={isTeacher ? "/cabinet" : isStaff ? "/students" : "/admin?tab=students"} className="link-btn">
        {isTeacher ? "← К моим группам" : isStaff ? "← К поиску студентов" : "← К списку студентов"}
      </Link>
    </p>
  );

  if (error && !card) {
    return (
      <div>
        {back}
        <div className="error-text">{error}</div>
      </div>
    );
  }
  if (!card) return <p className="hint">Загрузка…</p>;

  const stats = card.stats;

  return (
    <div className="student-card">
      {back}
      {error && <div className="error-text">{error}</div>}
      {notice && (
        <div className="day-status submitted">
          {notice} <button className="link-btn" onClick={() => setNotice(null)}>Скрыть</button>
        </div>
      )}

      <div className="student-card__header">
        <h2>{card.full_name}</h2>
        <span className={`locked-badge${card.status === "studying" ? "" : " risk-badge"}`}>
          {STUDENT_STATUS_LABELS[card.status] ?? card.status}
        </span>
      </div>

      <dl className="student-card__grid">
        <Item label="Группа" value={`${card.group.code} · ${card.group.course} курс`} />
        <Item label="Форма обучения" value={card.group.study_form ?? "—"} />
        <Item label="Отделение" value={card.group.department_name} />
        <Item label="Куратор" value={card.curator_name ?? "нет куратора"} />
        <Item label="Заместитель куратора" value={card.deputy_name ?? "нет"} />
        <Item label="Статус обучения" value={STUDENT_STATUS_LABELS[card.status] ?? card.status} />
        <Item label="Дата зачисления" value={formatDateRu(card.enrolled_at)} />
        <Item label="Дата выбытия" value={card.left_at ? formatDateRu(card.left_at) : "—"} />
      </dl>

      <h3 className="student-card__section">Досье</h3>
      <StudentDossier studentId={card.id} isAdmin={inRoles(user?.role, DOSSIER_AUDIT_ROLES)} />

      <h3 className="student-card__section">
        Посещаемость за 30 дней ({formatDateRu(stats.date_from)} — {formatDateRu(stats.date_to)})
      </h3>
      {stats.in_list === 0 ? (
        <p className="hint">За этот период нет сданных дней по группе.</p>
      ) : (
        <>
          <dl className="student-card__grid">
            <Item label="Учтено дней" value={String(stats.in_list)} />
            <Item label="Присутствовал" value={String(stats.present)} />
            <Item
              label="Отсутствовал"
              value={`${stats.absent_total} (уваж. ${stats.absent_excused}, неуваж. ${stats.absent_unexcused})`}
            />
            <Item label="Опозданий" value={String(stats.late)} />
            <Item label="Посещаемость" value={`${stats.percent}%`} />
          </dl>
          {Object.keys(stats.by_code).length > 0 && (
            <p className="hint">
              {Object.entries(stats.by_code).map(([code, n]) => (
                <span key={code}>
                  <b>{code.toUpperCase()}</b>: {n}{" "}
                </span>
              ))}
            </p>
          )}
        </>
      )}

      <StudentMonthAttendanceView studentId={card.id} />

      <h3 className="student-card__section">Последние отметки</h3>
      {card.recent_marks.length === 0 ? (
        <p className="hint">Отметок пока нет.</p>
      ) : (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Отметка</th>
              <th>Комментарий</th>
              <th>Основание</th>
            </tr>
          </thead>
          <tbody>
            {card.recent_marks.map((m) => (
              <tr key={m.date}>
                <td data-label="Дата">{formatDateRu(m.date)}</td>
                <td data-label="Отметка">
                  <b>{m.code.toUpperCase()}</b> — {m.name}
                </td>
                <td data-label="Комментарий">{m.comment ?? "—"}</td>
                <td data-label="Основание">{m.basis_reference ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="student-card__section">История групп</h3>
      <table className="dash-table">
        <thead>
          <tr>
            <th>Группа</th>
            <th>С</th>
            <th>По</th>
          </tr>
        </thead>
        <tbody>
          {card.group_history.map((h) => (
            <tr key={`${h.group_id}-${h.start_date}`}>
              <td data-label="Группа">{h.group_code}</td>
              <td data-label="С">{formatDateRu(h.start_date)}</td>
              <td data-label="По">{h.end_date ? formatDateRu(h.end_date) : "по настоящее время"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {canManage && (
        <ManageSection
          // Форма заполняется из карточки один раз при создании; после
          // сохранения данные меняются — key пересоздаёт форму с ними.
          key={[card.last_name, card.first_name, card.middle_name, card.group.id, card.status, card.left_at].join("|")}
          card={card}
          groups={groups}
          onChanged={load}
          setNotice={setNotice}
          setError={setError}
          onDeleted={(detail) => navigate("/admin?tab=students", { state: { notice: detail } })}
        />
      )}
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className="student-card__item">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function ManageSection({
  card,
  groups,
  onChanged,
  onDeleted,
  setNotice,
  setError,
}: {
  card: StudentCard;
  groups: StudyGroupAdmin[];
  onChanged: () => void;
  onDeleted: (detail: string) => void;
  setNotice: (n: string | null) => void;
  setError: (e: string | null) => void;
}) {
  const [lastName, setLastName] = useState(card.last_name);
  const [firstName, setFirstName] = useState(card.first_name);
  const [middleName, setMiddleName] = useState(card.middle_name ?? "");
  const [groupId, setGroupId] = useState(card.group.id);
  const [status, setStatus] = useState(card.status);
  const [leftAt, setLeftAt] = useState(card.left_at ?? todayIso());
  const [busy, setBusy] = useState(false);

  const groupChanged = groupId !== card.group.id;
  const targetGroupCode = groups.find((g) => g.id === groupId)?.code;

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    if (
      groupChanged &&
      !window.confirm(
        `Перевести студента в группу «${targetGroupCode}»? Перевод действует с сегодняшнего дня, ` +
          "прошлая посещаемость останется в прежней группе."
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/admin/students/${card.id}`, {
        last_name: lastName,
        first_name: firstName,
        middle_name: middleName || null,
        study_group_id: groupId,
      });
      setNotice("Данные студента сохранены");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    } finally {
      setBusy(false);
    }
  }

  async function saveStatus() {
    if (status === card.status) return;
    if (!window.confirm(`Сменить статус на «${STUDENT_STATUS_LABELS[status] ?? status}»?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/admin/students/${card.id}/status`, {
        status,
        left_at: status !== "studying" ? leftAt : null,
      });
      setNotice("Статус обучения изменён");
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось изменить статус");
    } finally {
      setBusy(false);
    }
  }

  async function removeStudent() {
    if (!window.confirm(`Удалить студента «${card.full_name}» насовсем?`)) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/students/${card.id}`);
      onDeleted(res.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
      setBusy(false);
    }
  }

  return (
    <>
      <h3 className="student-card__section">Управление</h3>

      <form className="add-block" onSubmit={saveProfile}>
        <p className="add-block__title">Данные и группа</p>
        <div className="inline-form">
          <input placeholder="Фамилия" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
          <input placeholder="Имя" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
          <input placeholder="Отчество" value={middleName} onChange={(e) => setMiddleName(e.target.value)} />
          <select value={groupId} onChange={(e) => setGroupId(Number(e.target.value))}>
            {!groups.some((g) => g.id === card.group.id) && (
              <option value={card.group.id}>{card.group.code}</option>
            )}
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.code}
              </option>
            ))}
          </select>
          <button type="submit" disabled={busy}>
            Сохранить
          </button>
        </div>
        {groupChanged && (
          <p className="hint">Группа изменена — будет выполнен перевод с сегодняшнего дня.</p>
        )}
      </form>

      <div className="add-block">
        <p className="add-block__title">Статус обучения</p>
        <div className="inline-form">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {Object.entries(STUDENT_STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {status !== "studying" && (
            <label>
              Дата выбытия{" "}
              <input type="date" value={leftAt} onChange={(e) => setLeftAt(e.target.value)} />
            </label>
          )}
          <button onClick={saveStatus} disabled={busy || status === card.status}>
            Применить
          </button>
        </div>
      </div>

      <div className="student-card__danger">
        {card.status === "studying" ? (
          <p className="hint">
            Удалить студента можно только после перевода в академ. отпуск или отчисления.
          </p>
        ) : (
          <button className="danger-btn" onClick={removeStudent} disabled={busy}>
            Удалить студента насовсем
          </button>
        )}
      </div>
    </>
  );
}
