import { api } from "../api/client";
import DayJournal from "../components/DayJournal";
import type { GroupSummary } from "../api/types";

const fetchGroups = () =>
  api
    .get<GroupSummary[]>("/curator/groups")
    .then((gs) => gs.map((g) => ({ id: g.id, label: `${g.code} (курс ${g.course})${g.is_submitted_today ? "" : " — не сдано сегодня"}` })));

export default function CuratorCabinetPage() {
  return (
    <DayJournal
      fetchGroups={fetchGroups}
      emptyText="У вас нет закреплённых групп."
      notSubmittedText="День ещё не сдан — можно заполнить"
      submitLabel="Сдать день"
      submitErrorText="Не удалось сдать день"
    />
  );
}
