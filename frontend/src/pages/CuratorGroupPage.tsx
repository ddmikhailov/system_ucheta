import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import BackLink from "../components/BackLink";
import { useEntryState } from "../hooks/useEntryState";
import { api, ApiError } from "../api/client";
import { MODULE } from "../constants/modules";
import type { ModuleName } from "../constants/modules";
import { isModuleOn } from "../utils/modules";
import { useAuth } from "../auth/useAuth";
import type { GroupSummary, RosterResponse } from "../api/types";
import CompensationPanel from "../components/CompensationPanel";
import DayJournal from "../components/DayJournal";
import GroupListModal from "../components/GroupListModal";
import MyIdPanel from "../components/MyIdPanel";
import { Kpi, ProfileHero } from "../components/ProfileHero";
import StudentCardModal from "../components/StudentCardModal";
import GroupMealsPanel from "../components/meals/GroupMealsPanel";
import { TabBar, TabPanel } from "../components/Tabs";
import { filterByQuery } from "../utils/searchMatch";
import { formatPercent } from "../utils/percent";
import { todayIso } from "../utils/date";
import IndividualWorkPage from "./IndividualWorkPage";
import { GroupPassportPanel } from "./PassportPage";
import PlanPage from "./PlanPage";
import ReportPage from "./ReportPage";

const TABS = ["journal", "students", "meals", "work", "passport", "plan", "report", "my-id"] as const;
type GroupTab = (typeof TABS)[number];
// Вкладки, которые есть только при включённом модуле (релиз 3.5.0: «Журнал» и «Студенты» — посещаемость, всегда).
const TAB_MODULE: Partial<Record<GroupTab, ModuleName>> = {
  meals: MODULE.MEALS,
  work: MODULE.INDIVIDUAL_WORK,
  passport: MODULE.PASSPORT,
  plan: MODULE.PLAN,
  report: MODULE.REPORTS,
  "my-id": MODULE.MY_ID,
};
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
  const visibleTabs = TABS.filter((t) => !TAB_MODULE[t] || isModuleOn(user, TAB_MODULE[t]));
  // Ссылка на выключенную вкладку (?tab=passport из закладки) открывает «Журнал».
  const tab: GroupTab = (visibleTabs as readonly string[]).includes(rawTab ?? "") ? (rawTab as GroupTab) : "journal";
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
      <BackLink to="/cabinet">← Мои группы</BackLink>
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
        <Kpi
          label="В группе риска"
          value={String(summary.risk_count)}
          tone={summary.risk_count > 0 ? "hot" : undefined}
          hint="пропуски без уважительной причины"
        />
        <Kpi
          label="Восполнить пропуски"
          value={String(summary.compensation_count ?? 0)}
          tone={summary.compensation_count ? "warn" : undefined}
          hint="закрыть — во вкладке «Студенты»"
        />
      </ProfileHero>

      <TabBar
        tabs={[
          { key: "journal", label: "Журнал" },
          { key: "students", label: "Студенты", badge: summary.students_count || undefined },
          { key: "meals", label: "Питание" },
          { key: "work", label: "Индивидуальная работа" },
          { key: "passport", label: "Соц. паспорт" },
          { key: "plan", label: "План группы" },
          { key: "report", label: "Отчёт" },
          { key: "my-id", label: "Мой ID" },
        ].filter((t) => (visibleTabs as readonly string[]).includes(t.key))}
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
        <GroupStudents
          groupId={groupId}
          groupCode={summary.code}
          documents={isModuleOn(user, MODULE.DOSSIER)}
          onChanged={loadSummary}
        />
      </TabPanel>
      <TabPanel idPrefix="group" tabKey="meals" active={tab}>
        <GroupMealsPanel groupId={groupId} />
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

/** Весь список группы: поиск, посещаемость с начала семестра, группа риска и «Восполнить пропуски» (сверху — поле,
 * где куратор закрывает их комментарием); ФИО — переход в карточку студента. Здесь же — «Список для печати» и
 * «Личные карточки» в Word. */
function GroupStudents({
  groupId,
  groupCode,
  documents,
  onChanged,
}: {
  groupId: number;
  groupCode: string;
  documents: boolean;
  onChanged?: () => void;
}) {
  const [roster, setRoster] = useState<RosterResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useEntryState("query", "");
  const [listOpen, setListOpen] = useState(false);
  const [cardsOpen, setCardsOpen] = useState(false);

  const loadRoster = useCallback(() => {
    api
      .get<RosterResponse>(`/curator/groups/${groupId}/day?date=${todayIso()}`)
      .then(setRoster)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить список группы"));
  }, [groupId]);

  useEffect(loadRoster, [loadRoster]);

  const rows = useMemo(() => (roster ? filterByQuery(roster.entries, query, (e) => e.full_name) : []), [roster, query]);

  return (
    <div className="group-students">
      <CompensationPanel
        groupId={groupId}
        onChanged={() => {
          loadRoster();
          onChanged?.();
        }}
      />
      <div className="toolbar">
        <label className="form-field group-students__search">
          Поиск по ФИО
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Начните вводить фамилию" />
        </label>
        {documents && (
          <span className="journal__tools">
            <button type="button" className="btn-secondary" onClick={() => setListOpen(true)}>
              Список для печати
            </button>
            <button type="button" className="btn-secondary" onClick={() => setCardsOpen(true)}>
              Личные карточки
            </button>
          </span>
        )}
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
                <td data-label="Статус">
                  {e.is_risk ? (
                    <span className="risk-badge" title={`Без уважительной причины пропущено ${formatPercent(e.unexcused_percent)} дней`}>
                      группа риска
                    </span>
                  ) : e.needs_compensation ? (
                    <span className="compensate-badge">восполнить пропуски</span>
                  ) : (
                    "—"
                  )}
                </td>
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
