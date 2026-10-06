import { api } from "../../api/client";
import DayJournal, { type JournalGroup } from "../../components/DayJournal";
import type { DepartmentAdmin, StudyGroupAdmin } from "../../api/types";

// Группы в порядке сервера, у каждой — отделение: в журнале сначала выбирается отделение, потом группа
// из него (раньше был один длинный список на весь колледж). Отделения не загрузились — список общий.
const fetchGroups = async (): Promise<JournalGroup[]> => {
  const [all, departments] = await Promise.all([
    api.get<StudyGroupAdmin[]>("/admin/groups"),
    api.get<DepartmentAdmin[]>("/admin/departments").catch(() => [] as DepartmentAdmin[]),
  ]);
  const names = new Map(departments.map((d) => [d.id, d.name]));
  return all
    .filter((g) => g.is_active)
    .map((g) => ({
      id: g.id,
      label: `${g.code} (курс ${g.course})${g.curator_name ? ` — ${g.curator_name}` : " — нет куратора"}`,
      departmentId: g.department_id ?? null,
      departmentName: names.get(g.department_id) ?? null,
    }));
};

/** Журнал группы для администрации (обновление 1.1): та же механика, что и
 * в кабинете куратора, но группа выбирается из всех групп в зоне видимости
 * (весь колледж у admin/edu_department, своё отделение у зав. отделением —
 * бэкенд уже разграничивает это в assert_can_access_group), для любого дня,
 * с полным правом правки и видимостью, кто и когда вносил отметку. */
export default function GroupJournalTab() {
  return (
    <DayJournal
      fetchGroups={fetchGroups}
      emptyText="Нет ни одной группы в зоне видимости."
      notSubmittedText="День не активирован куратором — можно заполнить самостоятельно"
      submitLabel="Сохранить день"
      submitErrorText="Не удалось сохранить день"
      showLastEdited
    />
  );
}
