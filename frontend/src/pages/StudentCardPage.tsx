import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { DOSSIER_AUDIT_ROLES, DOSSIER_STAFF_ROLES, STRUCTURE_EDITOR_ROLES, TEACHER_ROLES, inRoles } from "../constants/roles";
import { STUDENT_STATUS_LABELS } from "../constants/studentStatus";
import AbsenceMessageButton from "../components/AbsenceMessageButton";
import AbsenceSheetButton from "../components/AbsenceSheetButton";
import { DossierSection } from "../components/StudentDossier";
import { useDossier } from "../hooks/useDossier";
import StudentMonthAttendanceView from "../components/StudentMonthAttendance";
import { Kpi, ProfileHero } from "../components/ProfileHero";
import { TabBar, TabPanel, type TabItem } from "../components/Tabs";
import { useScrollToTopOnChange } from "../hooks/useScrollToTopOnChange";
import { useTabParam } from "../hooks/useTabParam";
import type { DeleteResult, StudentCard, StudyGroupAdmin } from "../api/types";
import { formatDateRu, todayIso } from "../utils/date";
import SearchSelect from "../components/SearchSelect";
import { dialogs } from "../utils/feedback";

const STUDENT_TABS = ["overview", "dossier", "guardians", "work", "attendance", "history", "manage"] as const;

// Личная карточка студента (интерфейс 3.0): сверху — кто это и главные цифры, ниже — вкладки
// «Обзор», «Досье», «Представители», «Индивидуальная работа», «Посещаемость», «История» и
// «Управление» (правка ФИО, перевод, статус, удаление). Управлять могут админ/тьютор и
// зав. отделением своего отделения, остальные управленческие роли видят карточку для чтения.
// Вкладка — в адресе (?tab=…), досье грузится один раз на всю карточку.
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
  const [tab, setTab] = useTabParam(STUDENT_TABS, "overview");
  const dossierState = useDossier(Number(studentId));

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
  const isAdminViewer = inRoles(user?.role, DOSSIER_AUDIT_ROLES);
  const dossier = dossierState.dossier;
  const openFollowUps = dossier?.notes.filter((n) => n.follow_up_on && !n.follow_up_done).length ?? 0;
  const tabs: TabItem[] = [
    { key: "overview", label: "Обзор" },
    { key: "dossier", label: "Досье" },
    { key: "guardians", label: "Представители", badge: dossier?.guardians.length || undefined },
    { key: "work", label: "Индивидуальная работа", badge: dossier?.notes.length || undefined },
    { key: "attendance", label: "Посещаемость" },
    { key: "history", label: "История" },
    ...(canManage ? [{ key: "manage", label: "Управление" }] : []),
  ];
  const percentTone = stats.in_list === 0 ? undefined : stats.percent >= 85 ? "ok" : stats.percent >= 70 ? "warn" : "hot";

  return (
    <div className="student-card">
      {back}
      {error && <div className="error-text">{error}</div>}
      {notice && (
        <div className="day-status submitted">
          {notice} <button className="link-btn" onClick={() => setNotice(null)}>Скрыть</button>
        </div>
      )}

      <ProfileHero
        name={card.full_name}
        badge={
          <span className={`locked-badge${card.status === "studying" ? "" : " risk-badge"}`}>
            {STUDENT_STATUS_LABELS[card.status] ?? card.status}
          </span>
        }
        meta={[`${card.group.code} · ${card.group.course} курс`, card.group.department_name, `Куратор: ${card.curator_name ?? "нет куратора"}`]}
      >
        <Kpi label="Посещаемость, 30 дней" value={stats.in_list === 0 ? "—" : `${stats.percent}%`} tone={percentTone} />
        <Kpi label="Пропуски без причины" value={String(stats.absent_unexcused)} tone={stats.absent_unexcused > 0 ? "hot" : undefined} />
        <Kpi label="Опоздания" value={String(stats.late)} />
        <Kpi label="Записи работы" value={dossier ? String(dossier.notes.length) : "…"} />
        <Kpi label="Вернуться к вопросу" value={dossier ? String(openFollowUps) : "…"} tone={openFollowUps > 0 ? "warn" : undefined} />
      </ProfileHero>

      <TabBar tabs={tabs} active={tab} onChange={setTab} label="Разделы карточки студента" idPrefix="student" />

      <TabPanel idPrefix="student" tabKey="overview" active={tab}>
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
        <div className="quick-actions">
          <AbsenceMessageButton studentId={card.id} />
          <AbsenceSheetButton studentId={card.id} lastName={card.last_name} groupCode={card.group.code} />
        </div>
      </TabPanel>

      <TabPanel idPrefix="student" tabKey="dossier" active={tab}>
        <DossierSection state={dossierState} section="profile" studentId={card.id} isAdmin={isAdminViewer} />
      </TabPanel>

      <TabPanel idPrefix="student" tabKey="guardians" active={tab}>
        <DossierSection state={dossierState} section="guardians" studentId={card.id} isAdmin={isAdminViewer} />
      </TabPanel>

      <TabPanel idPrefix="student" tabKey="work" active={tab}>
        <DossierSection state={dossierState} section="notes" studentId={card.id} isAdmin={isAdminViewer} />
      </TabPanel>

      <TabPanel idPrefix="student" tabKey="attendance" active={tab}>
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
      </TabPanel>

      <TabPanel idPrefix="student" tabKey="history" active={tab}>
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
        <DossierSection state={dossierState} section="log" studentId={card.id} isAdmin={isAdminViewer} />
      </TabPanel>

      {canManage && (
        <TabPanel idPrefix="student" tabKey="manage" active={tab}>
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
        </TabPanel>
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
      !(await dialogs.confirm(
        `Перевести студента в группу «${targetGroupCode}»? Перевод действует с сегодняшнего дня, ` +
          "прошлая посещаемость останется в прежней группе.",
        { confirmLabel: "Перевести" }
      ))
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
    if (!(await dialogs.confirm(`Сменить статус на «${STUDENT_STATUS_LABELS[status] ?? status}»?`, { confirmLabel: "Сменить статус" }))) return;
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
    if (!(await dialogs.confirm(`Удалить студента «${card.full_name}» насовсем?`, { confirmLabel: "Удалить", danger: true }))) return;
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
      <form className="add-block" onSubmit={saveProfile}>
        <p className="add-block__title">Данные и группа</p>
        <div className="inline-form">
          <input placeholder="Фамилия" aria-label="Фамилия" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
          <input placeholder="Имя" aria-label="Имя" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
          <input placeholder="Отчество" aria-label="Отчество" value={middleName} onChange={(e) => setMiddleName(e.target.value)} />
          <SearchSelect
            value={String(groupId)}
            options={[
              ...(groups.some((g) => g.id === card.group.id) ? [] : [{ value: String(card.group.id), label: card.group.code }]),
              ...groups.map((g) => ({ value: String(g.id), label: g.code })),
            ]}
            onChange={(v) => setGroupId(Number(v))}
            ariaLabel="Группа"
            title="Группа: начните вводить код, например «ГД»"
          />
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
          <select aria-label="Статус обучения" value={status} onChange={(e) => setStatus(e.target.value)}>
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
