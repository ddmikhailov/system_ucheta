import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import { STUDENT_STATUS_LABELS } from "../../constants/studentStatus";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import type { StudentAdmin, StudyGroupAdmin } from "../../api/types";
import { todayIso } from "../../utils/date";

// Здесь только список, поиск и добавление. Всё управление конкретным
// студентом (ФИО, перевод, статус, удаление) — на его личной карточке.
export default function StudentsTab({ canCreate }: { canEdit?: boolean; canCreate: boolean }) {
  const location = useLocation();
  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [students, setStudents] = useState<StudentAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Сообщение приходит после удаления студента на его карточке.
  const [notice, setNotice] = useState<string | null>(
    (location.state as { notice?: string } | null)?.notice ?? null
  );
  useScrollToTopOnChange(error, notice);
  const [busy, setBusy] = useState(false);

  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [middleName, setMiddleName] = useState("");
  const [enrolledAt, setEnrolledAt] = useState(todayIso());

  // Отчисленные/в академе не мешаются в основном списке группы.
  const [showArchived, setShowArchived] = useState(false);

  // Поиск по ФИО ищет сразу по всем группам (см. TODO.md 4) — раньше нужно
  // было вручную перебирать группы, чтобы найти студента.
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    api.get<StudyGroupAdmin[]>("/admin/groups").then((allGroups) => {
      const gs = allGroups.filter((g) => g.is_active);
      setGroups(gs);
      if (gs.length > 0) setGroupId(gs[0].id);
    });
  }, []);

  function loadStudents() {
    const isSearching = searchQuery.trim().length > 0;
    if (!isSearching && groupId === null) return;
    const url = isSearching ? "/admin/students" : `/admin/students?study_group_id=${groupId}`;
    api
      .get<StudentAdmin[]>(url)
      .then(setStudents)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
  }

  useEffect(loadStudents, [groupId, searchQuery]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (groupId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/admin/students", {
        last_name: lastName,
        first_name: firstName,
        middle_name: middleName || null,
        study_group_id: groupId,
        enrolled_at: enrolledAt,
      });
      setLastName("");
      setFirstName("");
      setMiddleName("");
      loadStudents();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось добавить студента");
    } finally {
      setBusy(false);
    }
  }

  const isSearching = searchQuery.trim().length > 0;
  const searchedStudents = isSearching
    ? students.filter((s) => s.full_name.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : students;
  const visibleStudents = showArchived ? searchedStudents : searchedStudents.filter((s) => s.status === "studying");
  const archivedCount = searchedStudents.length - searchedStudents.filter((s) => s.status === "studying").length;
  const groupCode = (id: number) => groups.find((g) => g.id === id)?.code ?? "—";

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      {notice && (
        <div className="day-status submitted">
          {notice} <button className="link-btn" onClick={() => setNotice(null)}>Скрыть</button>
        </div>
      )}

      {canCreate && (
        <div className="add-block">
          <p className="add-block__title">Добавить студента в выбранную группу</p>
          <form className="inline-form" onSubmit={handleCreate}>
            <input placeholder="Фамилия" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
            <input placeholder="Имя" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
            <input placeholder="Отчество" value={middleName} onChange={(e) => setMiddleName(e.target.value)} />
            <input type="date" value={enrolledAt} onChange={(e) => setEnrolledAt(e.target.value)} />
            <button type="submit" disabled={busy || groupId === null}>
              Добавить студента
            </button>
          </form>
        </div>
      )}

      <div className="toolbar">
        <select value={groupId ?? ""} onChange={(e) => setGroupId(Number(e.target.value))} disabled={isSearching}>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.code} (курс {g.course})
            </option>
          ))}
        </select>
        <input
          placeholder="Поиск по ФИО — по всем группам"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      <table className="dash-table">
        <thead>
          <tr>
            <th>ФИО</th>
            <th>Группа</th>
            <th>Статус</th>
            <th>Зачислен</th>
            <th>Выбыл</th>
          </tr>
        </thead>
        <tbody>
          {visibleStudents.map((s) => (
            <tr key={s.id}>
              <td data-label="ФИО">
                <Link to={`/students/${s.id}`} className="link-btn">
                  {s.full_name}
                </Link>
              </td>
              <td data-label="Группа">{groupCode(s.study_group_id)}</td>
              <td data-label="Статус">{STUDENT_STATUS_LABELS[s.status] ?? s.status}</td>
              <td data-label="Зачислен">{s.enrolled_at}</td>
              <td data-label="Выбыл">{s.left_at ?? "—"}</td>
            </tr>
          ))}
          {visibleStudents.length === 0 && (
            <tr>
              <td colSpan={5}>В группе нет студентов.</td>
            </tr>
          )}
        </tbody>
      </table>

      {archivedCount > 0 && (
        <p className="hint archive-toggle">
          <button className="link-btn" onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? "Скрыть архив" : `Архив (${archivedCount})`}
          </button>
        </p>
      )}
    </div>
  );
}
