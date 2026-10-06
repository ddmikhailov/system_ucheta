import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { DepartmentAdmin, UserActivityEntry, UserActivityPage, UserProfile } from "../api/types";
import { Kpi, ProfileHero } from "../components/ProfileHero";
import { TabBar, TabPanel, type TabItem } from "../components/Tabs";
import { AUDIT_AREAS, auditActionLabel } from "../constants/auditActions";
import { ROLE_LABELS, STRUCTURE_EDITOR_ROLES, inRoles, type RoleCode } from "../constants/roles";
import { useTabParam } from "../hooks/useTabParam";
import { formatDateRu, formatServerDateTimeFull, parseServerDateTime } from "../utils/date";
import { plural } from "../utils/plural";
import { userStatusLabel } from "../utils/userStatus";
import UserManagePanel from "./admin/UserManagePanel";

const USER_TABS = ["overview", "groups", "activity", "manage"] as const;
const DAYS: [string, string, string] = ["день", "дня", "дней"];

/** Профиль пользователя для администрации (интерфейс 3.0): за какими группами закреплён,
 * как сдаёт дни и ведёт задачи, индивидуальная работа, лента действий со временем и
 * управление учётной записью. Права проверяет сервер: зав. отделением и тьютор видят
 * людей своего отделения, администратор и воспитательный отдел — всех. */
export default function UserProfilePage() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const { user: me } = useAuth();
  const canManage = inRoles(me?.role, STRUCTURE_EDITOR_ROLES);
  const [tab, setTab] = useTabParam(USER_TABS, "overview");

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<UserProfile>(`/admin/users/${userId}/profile`)
      .then((p) => {
        setProfile(p);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить профиль"));
  }, [userId]);

  useEffect(load, [load]);
  useEffect(() => {
    if (!canManage) return;
    api.get<DepartmentAdmin[]>("/admin/departments").then(setDepartments).catch(() => {});
  }, [canManage]);

  const back = (
    <p>
      <Link to="/admin?tab=users" className="link-btn">
        ← К пользователям
      </Link>
    </p>
  );

  if (error && !profile) {
    return (
      <div>
        {back}
        <div className="error-text">{error}</div>
      </div>
    );
  }
  if (!profile) return <p className="hint">Загрузка…</p>;

  const u = profile.user;
  const d = profile.discipline;
  const t = profile.tasks;
  const current = profile.groups.filter((g) => g.is_current);
  const tabs: TabItem[] = [
    { key: "overview", label: "Обзор" },
    { key: "groups", label: "Группы", badge: current.length || undefined },
    { key: "activity", label: "Действия" },
    ...(canManage ? [{ key: "manage", label: "Управление" }] : []),
  ];
  const disciplineTone = d.percent_on_time === null ? undefined : d.percent_on_time >= 90 ? "ok" : d.percent_on_time >= 70 ? "warn" : "hot";

  return (
    <div className="user-profile">
      {back}
      {error && <div className="error-text">{error}</div>}

      <ProfileHero
        name={u.full_name}
        badge={<span className={`locked-badge${u.is_active && !u.is_locked ? "" : " risk-badge"}`}>{userStatusLabel(u)}</span>}
        meta={[
          u.display_title || (ROLE_LABELS[u.role as RoleCode] ?? u.role),
          profile.department_name,
          `логин ${u.username}`,
          profile.last_activity_at ? `последнее действие ${formatServerDateTimeFull(profile.last_activity_at)}` : "действий в журнале нет",
        ]}
      >
        <Kpi
          label="Дни сданы вовремя"
          value={d.percent_on_time === null ? "—" : `${d.percent_on_time}%`}
          tone={disciplineTone}
          hint={d.study_days ? `${d.on_time} из ${d.study_days} учебных ${plural(d.study_days, DAYS)}` : "нет групп или учебных дней"}
        />
        <Kpi label="Не сданы дни" value={String(d.missed)} tone={d.missed > 0 ? "hot" : undefined} hint="за 30 дней" />
        <Kpi label="Задачи просрочены" value={String(t.overdue)} tone={t.overdue > 0 ? "hot" : undefined} hint={`из ${t.total} за 90 дней`} />
        <Kpi label="Записи работы" value={String(profile.notes_written_30d)} hint="за 30 дней" />
        <Kpi label="Вернуться к вопросу" value={String(profile.follow_ups_open)} tone={profile.follow_ups_open > 0 ? "warn" : undefined} />
      </ProfileHero>

      <TabBar tabs={tabs} active={tab} onChange={setTab} label="Разделы профиля пользователя" idPrefix="user" />

      <TabPanel idPrefix="user" tabKey="overview" active={tab}>
        <section className="profile-section">
          <h3>Активность за 30 дней</h3>
          <ActivityBars days={profile.activity_30d} />
        </section>

        <div className="profile-grid">
          <section className="profile-section">
            <h3>Дисциплина сдачи дней</h3>
            <p className="hint">
              По группам, которые ведёт сейчас, {formatDateRu(d.date_from)} — {formatDateRu(d.date_to)}.
            </p>
            {d.study_days === 0 ? (
              <p className="hint">Учебных дней по текущим группам за этот период нет.</p>
            ) : (
              <>
                <Meter parts={[
                  { value: d.on_time, tone: "ok", label: "вовремя" },
                  { value: d.late, tone: "warn", label: "с опозданием" },
                  { value: d.missed, tone: "hot", label: "не сданы" },
                ]} total={d.study_days} />
                <dl className="stat-list">
                  <div><dt>Вовремя</dt><dd>{d.on_time}</dd></div>
                  <div><dt>С опозданием</dt><dd>{d.late}</dd></div>
                  <div><dt>Не сданы</dt><dd>{d.missed}</dd></div>
                </dl>
              </>
            )}
          </section>

          <section className="profile-section">
            <h3>Задачи администрации</h3>
            <p className="hint">По группам, которые ведёт сейчас; срок — за последние 90 дней и дальше.</p>
            {t.total === 0 ? (
              <p className="hint">Задач нет.</p>
            ) : (
              <>
                <Meter parts={[
                  { value: t.accepted, tone: "ok", label: "приняты" },
                  { value: t.submitted, tone: "progress", label: "на проверке" },
                  { value: t.in_work + t.returned, tone: "idle", label: "в работе" },
                ]} total={t.total} />
                <dl className="stat-list">
                  <div><dt>Приняты</dt><dd>{t.accepted}</dd></div>
                  <div><dt>На проверке</dt><dd>{t.submitted}</dd></div>
                  <div><dt>В работе</dt><dd>{t.in_work}</dd></div>
                  <div><dt>Возвращены</dt><dd>{t.returned}</dd></div>
                  <div><dt>Просрочены</dt><dd>{t.overdue}</dd></div>
                </dl>
              </>
            )}
          </section>

          <section className="profile-section">
            <h3>Работа за 30 дней</h3>
            <dl className="stat-list">
              <div><dt>Отметок поставлено</dt><dd>{profile.marks_created_30d}</dd></div>
              <div><dt>Дней сдано лично</dt><dd>{profile.days_submitted_30d}</dd></div>
              <div><dt>Записей индивидуальной работы</dt><dd>{profile.notes_written_30d}</dd></div>
              <div><dt>Открытых «вернуться к вопросу»</dt><dd>{profile.follow_ups_open}</dd></div>
              <div><dt>Просмотров досье</dt><dd>{profile.dossier_views_30d}</dd></div>
            </dl>
            <p className="hint">В системе с {parseServerDateTime(profile.created_at).toLocaleDateString("ru-RU")}.</p>
          </section>
        </div>
      </TabPanel>

      <TabPanel idPrefix="user" tabKey="groups" active={tab}>
        {profile.groups.length === 0 ? (
          <p className="hint">Не закреплён ни за одной группой.</p>
        ) : (
          <table className="dash-table">
            <thead>
              <tr>
                <th>Группа</th>
                <th>Роль</th>
                <th>Отделение</th>
                <th>Студентов</th>
                <th>Период</th>
                <th>Журнал</th>
              </tr>
            </thead>
            <tbody>
              {profile.groups.map((g) => (
                <tr key={`${g.group_id}-${g.role_type}-${g.start_date}`} className={g.is_current ? "" : "row-muted"}>
                  <td data-label="Группа">
                    <b>{g.group_code}</b> · {g.course} курс
                  </td>
                  <td data-label="Роль">{g.role_type === "curator" ? "Куратор" : "Заместитель"}</td>
                  <td data-label="Отделение">{g.department_name ?? "—"}</td>
                  <td data-label="Студентов">{g.students_count}</td>
                  <td data-label="Период">
                    с {formatDateRu(g.start_date)}
                    {g.end_date ? ` по ${formatDateRu(g.end_date)}` : g.is_current ? " · сейчас" : ""}
                  </td>
                  <td data-label="Журнал">
                    <Link className="link-btn" to={`/admin?tab=journal&group=${g.group_id}`}>
                      Открыть
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </TabPanel>

      <TabPanel idPrefix="user" tabKey="activity" active={tab}>
        <ActivityFeed userId={u.id} />
      </TabPanel>

      {canManage && (
        <TabPanel idPrefix="user" tabKey="manage" active={tab}>
          <UserManagePanel
            key={[u.full_name, u.username, u.role, u.department_id, u.is_active, u.is_locked, u.has_password].join("|")}
            user={u}
            me={me}
            departments={departments}
            onChanged={load}
            onDeleted={(detail) => navigate("/admin?tab=users", { state: { notice: detail } })}
          />
        </TabPanel>
      )}
    </div>
  );
}

/** Столбики «сколько действий в день» за 30 дней: видно ритм работы и провалы. */
function ActivityBars({ days }: { days: { date: string; count: number }[] }) {
  const max = Math.max(1, ...days.map((x) => x.count));
  const total = days.reduce((sum, x) => sum + x.count, 0);
  const active = days.filter((x) => x.count > 0).length;
  return (
    <figure className="activity-bars">
      <div className="activity-bars__plot" aria-hidden="true">
        {days.map((x) => (
          <span
            key={x.date}
            className={`activity-bars__bar${x.count === 0 ? " is-empty" : ""}`}
            style={{ height: `${Math.max(4, Math.round((x.count / max) * 100))}%` }}
            title={`${formatDateRu(x.date)}: ${x.count}`}
          />
        ))}
      </div>
      <figcaption className="hint">
        {total === 0
          ? "За 30 дней действий в журнале нет."
          : `${total} ${plural(total, ["действие", "действия", "действий"])} за 30 дней, активных — ${active} ${plural(active, DAYS)}.`}
      </figcaption>
    </figure>
  );
}

/** Полоса из долей (вовремя / с опозданием / не сдано). */
function Meter({
  parts,
  total,
}: {
  parts: { value: number; tone: "ok" | "warn" | "hot" | "progress" | "idle"; label: string }[];
  total: number;
}) {
  return (
    <div className="split-meter" role="img" aria-label={parts.map((p) => `${p.label}: ${p.value}`).join(", ")}>
      {parts
        .filter((p) => p.value > 0)
        .map((p) => (
          <span key={p.label} className={`split-meter__part split-meter__part--${p.tone}`} style={{ flexGrow: p.value / total }} />
        ))}
    </div>
  );
}

function dayHeading(iso: string): string {
  const day = parseServerDateTime(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (day.toDateString() === today.toDateString()) return "Сегодня";
  if (day.toDateString() === yesterday.toDateString()) return "Вчера";
  return day.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", weekday: "long" });
}

function entityLink(e: UserActivityEntry): string | null {
  if (e.entity_type === "student") return `/students/${e.entity_id}`;
  if (e.entity_type === "task_assignment") return `/tasks/assignment/${e.entity_id}`;
  return null;
}

/** Лента действий: что сделано и во сколько, по дням, новые сверху; фильтр по области
 * и «Показать ещё». Значения «было/стало» сервер не отдаёт — в них бывают данные досье. */
function ActivityFeed({ userId }: { userId: number }) {
  const [area, setArea] = useState("");
  const [items, setItems] = useState<UserActivityEntry[] | null>(null);
  const [next, setNext] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback(
    (before: number | null) => {
      const qs = new URLSearchParams({ limit: "50" });
      if (before !== null) qs.set("before_id", String(before));
      if (area) qs.set("area", area);
      return api.get<UserActivityPage>(`/admin/users/${userId}/activity?${qs}`);
    },
    [userId, area]
  );
  const fail = (err: unknown) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить действия");

  // Первая страница (и заново — при смене области): старый список заменяется новым.
  useEffect(() => {
    let cancelled = false;
    request(null)
      .then((page) => {
        if (cancelled) return;
        setItems(page.items);
        setNext(page.next_before_id);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      });
    return () => {
      cancelled = true;
    };
  }, [request]);

  function loadMore() {
    if (next === null) return;
    setBusy(true);
    request(next)
      .then((page) => {
        setItems((prev) => [...(prev ?? []), ...page.items]);
        setNext(page.next_before_id);
        setError(null);
      })
      .catch(fail)
      .finally(() => setBusy(false));
  }

  const groups: { heading: string; entries: UserActivityEntry[] }[] = [];
  for (const e of items ?? []) {
    const heading = dayHeading(e.created_at);
    const last = groups[groups.length - 1];
    if (last && last.heading === heading) last.entries.push(e);
    else groups.push({ heading, entries: [e] });
  }

  return (
    <div className="activity-feed">
      <div className="toolbar">
        <label className="form-field">
          Что показать
          <select value={area} onChange={(e) => setArea(e.target.value)}>
            {AUDIT_AREAS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <div className="error-text">{error}</div>}
      {items === null ? (
        !error && <p className="hint">Загрузка…</p>
      ) : items.length === 0 ? (
        <p className="hint">Действий нет.</p>
      ) : (
        groups.map((g) => (
          <section key={g.heading} className="timeline">
            <h4 className="timeline__day">{g.heading}</h4>
            <ol className="timeline__list">
              {g.entries.map((e) => {
                const link = entityLink(e);
                return (
                  <li key={e.id} className={`timeline__item timeline__item--${e.action.split(".")[0]}`}>
                    <time dateTime={e.created_at}>
                      {parseServerDateTime(e.created_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                    </time>
                    <span className="timeline__text">
                      {auditActionLabel(e.action)}
                      {link && (
                        <>
                          {" · "}
                          <Link className="link-btn" to={link}>
                            открыть
                          </Link>
                        </>
                      )}
                    </span>
                  </li>
                );
              })}
            </ol>
          </section>
        ))
      )}
      {next !== null && (
        <button type="button" className="secondary-btn" disabled={busy} onClick={loadMore}>
          {busy ? "Загрузка…" : "Показать ещё"}
        </button>
      )}
    </div>
  );
}
