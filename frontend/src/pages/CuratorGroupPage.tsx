import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { GroupSummary, RosterResponse } from "../api/types";
import DayJournal from "../components/DayJournal";
import GroupListModal from "../components/GroupListModal";
import MyIdPanel from "../components/MyIdPanel";
import { Kpi, ProfileHero } from "../components/ProfileHero";
import StudentCardModal from "../components/StudentCardModal";
import { TabBar, TabPanel } from "../components/Tabs";
import { filterByQuery } from "../utils/searchMatch";
import { formatPercent } from "../utils/percent";
import { todayIso } from "../utils/date";
import IndividualWorkPage from "./IndividualWorkPage";
import { GroupPassportPanel } from "./PassportPage";
import PlanPage from "./PlanPage";
import ReportPage from "./ReportPage";

const TABS = ["journal", "students", "work", "passport", "plan", "report", "my-id"] as const;
type GroupTab = (typeof TABS)[number];
// Параметры вкладок (год, семестр, раздел) — свои у каждой; при смене вкладки они сбрасываются.
const TAB_SCOPED_PARAMS = ["part", "section", "year", "semester", "date"];

/** Страница группы куратора (интерфейс 3.2): всё, что относится к группе, — во вкладках, а не отдельными
 * разделами меню. «Журнал» (посещаемость по дням), «Студенты» (весь список, карточка — по клику),
 * «Индивидуальная работа», «Соц. паспорт», «План группы», «Отчёт», «Мой ID». Вкладка — в адресе (?tab=…). */
export default function CuratorGroupPage() {
  const { groupId: raw } = useParams();
  const groupId = Number(raw);
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const rawTab = params.get("tab");
  const tab: GroupTab = (TABS as readonly string[]).includes(rawTab ?? "") ? (rawTab as GroupTab) : "journal";
  const [summary, setSummary] = useState<GroupSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadSummary = useCallback(() => {
    api
      .get<GroupSummary[]>("/curator/groups")
      .then((gs) => {
        const found = (Array.isArray(gs) ? gs : []).find((g) => g.id === groupId);
        if (found) {
          setSummary(found);
          setError(null);
        } else setError("Эта группа не закреплена за вами");
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить группу"));
  }, [groupId]);

  useEffect(loadSummary, [loadSummary]);

  function setTab(next: string) {
    setParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        for (const key of TAB_SCOPED_PARAMS) p.delete(key);
        if (next === "journal") p.delete("tab");
        else p.set("tab", next);
        return p;
      },
      { replace: true }
    );
  }

  const severalGroups = (user?.groups.length ?? 0) > 1;
  const back = severalGroups && (
    <p>
      <Link to="/cabinet" className="link-btn">
        ← Мои группы
      </Link>
    </p>
  );

  if (error) {
    return (
      <div>
        {back}
        <div className="error-text">{error}</div>
      </div>
    );
  }
  if (!summary) return <p className="hint">Загрузка…</p>;

  return (
    <div className="group-page">
      {back}
      <ProfileHero
        name={`Группа ${summary.code}`}
        avatar={summary.code.replace(/[^A-Za-zА-Яа-яЁё]/g, "").slice(0, 2).toUpperCase() || "Гр"}
        badge={
          <span className={`locked-badge${summary.is_submitted_today ? "" : " risk-badge"}`}>
            {summary.is_submitted_today ? "сегодня сдано" : "сегодня не сдано"}
          </span>
        }
        meta={[`${summary.course} курс`, summary.role_type === "deputy" ? "вы — заместитель куратора" : "вы — куратор"]}
      >
        <Kpi label="Студентов" value={String(summary.students_count)} />
        <Kpi label="В группе риска" value={String(summary.risk_count)} tone={summary.risk_count > 0 ? "hot" : undefined} hint="посещаемость ниже нормы" />
      </ProfileHero>

      <TabBar
        tabs={[
          { key: "journal", label: "Журнал" },
          { key: "students", label: "Студенты", badge: summary.students_count || undefined },
          { key: "work", label: "Индивидуальная работа" },
          { key: "passport", label: "Соц. паспорт" },
          { key: "plan", label: "План группы" },
          { key: "report", label: "Отчёт" },
          { key: "my-id", label: "Мой ID" },
        ]}
        active={tab}
        onChange={setTab}
        label="Разделы группы"
        idPrefix="group"
      />

      <TabPanel idPrefix="group" tabKey="journal" active={tab}>
        <DayJournal
          fetchGroups={async () => [{ id: groupId, label: summary.code }]}
          fixedGroupId={groupId}
          showGroupTools={false}
          emptyText="Группа не найдена."
          notSubmittedText="День ещё не сдан — можно заполнить"
          submitLabel="Сдать день"
          submitErrorText="Не удалось сдать день"
          onSubmitted={loadSummary}
        />
      </TabPanel>
      <TabPanel idPrefix="group" tabKey="students" active={tab}>
        <GroupStudents groupId={groupId} groupCode={summary.code} />
      </TabPanel>
      <TabPanel idPrefix="group" tabKey="work" active={tab}>
        <IndividualWorkPage fixedGroupId={groupId} />
      </TabPanel>
      <TabPanel idPrefix="group" tabKey="passport" active={tab}>
        <GroupPassportPanel groupId={groupId} />
      </TabPanel>
      <TabPanel idPrefix="group" tabKey="plan" active={tab}>
        <PlanPage fixedGroupId={groupId} />
      </TabPanel>
      <TabPanel idPrefix="group" tabKey="report" active={tab}>
        <ReportPage fixedGroupId={groupId} />
      </TabPanel>
      <TabPanel idPrefix="group" tabKey="my-id" active={tab}>
        <MyIdPanel fixedGroupId={groupId} />
      </TabPanel>
    </div>
  );
}

/** Весь список группы: поиск, посещаемость с начала семестра, группа риска; ФИО — переход в карточку
 * студента. Здесь же — «Список для печати» и «Личные карточки» в Word. */
function GroupStudents({ groupId, groupCode }: { groupId: number; groupCode: string }) {
  const [roster, setRoster] = useState<RosterResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [listOpen, setListOpen] = useState(false);
  const [cardsOpen, setCardsOpen] = useState(false);

  useEffect(() => {
    api
      .get<RosterResponse>(`/curator/groups/${groupId}/day?date=${todayIso()}`)
      .then(setRoster)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить список группы"));
  }, [groupId]);

  const rows = useMemo(() => (roster ? filterByQuery(roster.entries, query, (e) => e.full_name) : []), [roster, query]);

  return (
    <div className="group-students">
      <div className="toolbar">
        <label className="form-field group-students__search">
          Поиск по ФИО
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Начните вводить фамилию" />
        </label>
        <span className="journal__tools">
          <button type="button" className="btn-secondary" onClick={() => setListOpen(true)}>
            Список для печати
          </button>
          <button type="button" className="btn-secondary" onClick={() => setCardsOpen(true)}>
            Личные карточки
          </button>
        </span>
      </div>
      {error && <div className="error-text">{error}</div>}
      {!roster ? (
        !error && <p className="hint">Загрузка…</p>
      ) : rows.length === 0 ? (
        <p className="hint">{query ? "Никого не нашлось." : "В группе нет студентов."}</p>
      ) : (
        <table className="dash-table roster-table compact-cards">
          <thead>
            <tr>
              <th>№</th>
              <th>ФИО</th>
              <th>Посещаемость с начала семестра</th>
              <th>Статус</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={e.student_id} className={e.is_risk ? "risk-row" : ""}>
                <td data-label="№">{i + 1}</td>
                <td data-label="ФИО">
                  <Link to={`/students/${e.student_id}`} className="link-btn">
                    {e.full_name}
                  </Link>
                </td>
                <td data-label="Посещаемость">{e.attendance_percent === null ? "—" : formatPercent(e.attendance_percent)}</td>
                <td data-label="Статус">{e.is_risk ? <span className="risk-badge">группа риска</span> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {listOpen && <GroupListModal groupId={groupId} groupCode={groupCode} onClose={() => setListOpen(false)} />}
      {cardsOpen && (
        <StudentCardModal
          endpoint={`/curator/groups/${groupId}/cards`}
          heading={`Личные карточки группы ${groupCode}`}
          filename={`Личные_карточки_${groupCode}.docx`}
          onClose={() => setCardsOpen(false)}
        />
      )}
    </div>
  );
}
