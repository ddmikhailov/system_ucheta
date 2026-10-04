import { api } from "../../api/client";
import DayJournal from "../../components/DayJournal";
import type { StudyGroupAdmin } from "../../api/types";

const fetchGroups = () =>
  api.get<StudyGroupAdmin[]>("/admin/groups").then((all) =>
    all
      .filter((g) => g.is_active)
      .map((g) => ({ id: g.id, label: `${g.code} (курс ${g.course})${g.curator_name ? ` — ${g.curator_name}` : " — нет куратора"}` }))
  );

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
