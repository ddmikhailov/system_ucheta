import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import type { DeleteResult, StudentAdmin, StudyGroupAdmin } from "../../api/types";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

const STATUS_LABELS: Record<string, string> = {
  studying: "Учится",
  academic_leave: "Академ. отпуск",
  expelled: "Отчислен",
};

export default function StudentsTab({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [groupId, setGroupId] = useState<number | null>(null);
  const [students, setStudents] = useState<StudentAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useScrollToTopOnChange(error, notice);
  const [busy, setBusy] = useState(false);

  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [middleName, setMiddleName] = useState("");
  const [enrolledAt, setEnrolledAt] = useState(todayIso());

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editLastName, setEditLastName] = useState("");
  const [editFirstName, setEditFirstName] = useState("");
  const [editMiddleName, setEditMiddleName] = useState("");
  const [editGroupId, setEditGroupId] = useState<number | null>(null);

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

  // Смена статуса раньше применялась сразу по выбору в select с датой "сегодня"
  // без возможности её поменять и без подтверждения (см. TODO.md 4) — теперь
  // выбор статуса только открывает форму с датой и явным подтверждением.
  const [pendingStatusStudentId, setPendingStatusStudentId] = useState<number | null>(null);
  const [pendingStatus, setPendingStatus] = useState("studying");
  const [pendingLeftAt, setPendingLeftAt] = useState(todayIso());

  function startStatusChange(student: StudentAdmin, status: string) {
    if (status === student.status) return;
    setPendingStatusStudentId(student.id);
    setPendingStatus(status);
    setPendingLeftAt(todayIso());
  }

  async function confirmStatusChange(student: StudentAdmin) {
    const left_at = pendingStatus !== "studying" ? pendingLeftAt : null;
    if (!window.confirm(`Сменить статус «${student.full_name}» на «${STATUS_LABELS[pendingStatus] ?? pendingStatus}»?`)) return;
    setError(null);
    try {
      await api.patch(`/admin/students/${student.id}/status`, { status: pendingStatus, left_at });
      setPendingStatusStudentId(null);
      loadStudents();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось изменить статус");
    }
  }

  function splitFullName(full: string): [string, string, string] {
    const parts = full.split(" ");
    return [parts[0] ?? "", parts[1] ?? "", parts.slice(2).join(" ")];
  }

  function startEdit(s: StudentAdmin) {
    const [last, first, middle] = splitFullName(s.full_name);
    setEditingId(s.id);
    setEditLastName(last);
    setEditFirstName(first);
    setEditMiddleName(middle);
    setEditGroupId(s.study_group_id);
  }

  async function saveEdit(studentId: number) {
    setError(null);
    try {
      await api.patch(`/admin/students/${studentId}`, {
        last_name: editLastName,
        first_name: editFirstName,
        middle_name: editMiddleName || null,
        study_group_id: editGroupId,
      });
      setEditingId(null);
      loadStudents();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function removeStudent(s: StudentAdmin) {
    if (!window.confirm(`Удалить студента «${s.full_name}» насовсем?`)) return;
    setError(null);
    setNotice(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/students/${s.id}`);
      setNotice(res.detail);
      loadStudents();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  const isSearching = searchQuery.trim().length > 0;
  const searchedStudents = isSearching
    ? students.filter((s) => s.full_name.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : students;
  const visibleStudents = showArchived ? searchedStudents : searchedStudents.filter((s) => s.status === "studying");
  const archivedCount = searchedStudents.length - searchedStudents.filter((s) => s.status === "studying").length;

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      {notice && (
        <div className="day-status submitted">
          {notice} <button className="link-btn" onClick={() => setNotice(null)}>Скрыть</button>
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
            {canEdit && <th>Управление</th>}
          </tr>
        </thead>
        <tbody>
          {visibleStudents.map((s) => (
            <tr key={s.id}>
              {editingId === s.id ? (
                <>
                  <td>
                    <input value={editLastName} onChange={(e) => setEditLastName(e.target.value)} placeholder="Фамилия" />
                    <input value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)} placeholder="Имя" />
                    <input value={editMiddleName} onChange={(e) => setEditMiddleName(e.target.value)} placeholder="Отчество" />
                  </td>
                  <td>
                    <select value={editGroupId ?? ""} onChange={(e) => setEditGroupId(Number(e.target.value))}>
                      {groups.map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.code}
                        </option>
                      ))}
                    </select>
                  </td>
                </>
              ) : (
                <>
                  <td>{s.full_name}</td>
                  <td>{groups.find((g) => g.id === s.study_group_id)?.code ?? "—"}</td>
                </>
              )}
              <td>
                {canEdit ? (
                  pendingStatusStudentId === s.id ? (
                    <div className="inline-form" style={{ marginTop: 0 }}>
                      <span>{STATUS_LABELS[pendingStatus] ?? pendingStatus}</span>
                      {pendingStatus !== "studying" && (
                        <input type="date" value={pendingLeftAt} onChange={(e) => setPendingLeftAt(e.target.value)} />
                      )}
                      <button className="link-btn" onClick={() => confirmStatusChange(s)}>
                        Подтвердить
                      </button>
                      <button className="link-btn" onClick={() => setPendingStatusStudentId(null)}>
                        Отмена
                      </button>
                    </div>
                  ) : (
                    <select value={s.status} onChange={(e) => startStatusChange(s, e.target.value)}>
                      {Object.entries(STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  )
                ) : (
                  STATUS_LABELS[s.status] ?? s.status
                )}
              </td>
              <td>{s.enrolled_at}</td>
              <td>{s.left_at ?? "—"}</td>
              {canEdit && (
                <td className="admin-row-actions">
                  {editingId === s.id ? (
                    <>
                      <button className="link-btn" onClick={() => saveEdit(s.id)}>
                        Сохранить
                      </button>
                      <button className="link-btn" onClick={() => setEditingId(null)}>
                        Отмена
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="link-btn" onClick={() => startEdit(s)}>
                        Изменить
                      </button>
                      {s.status !== "studying" && (
                        <button className="link-btn" onClick={() => removeStudent(s)}>
                          Удалить насовсем
                        </button>
                      )}
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
          {visibleStudents.length === 0 && (
            <tr>
              <td colSpan={canEdit ? 6 : 5}>В группе нет студентов.</td>
            </tr>
          )}
        </tbody>
      </table>

      {canCreate && (
        <form className="inline-form" onSubmit={handleCreate}>
          <input placeholder="Фамилия" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
          <input placeholder="Имя" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
          <input placeholder="Отчество" value={middleName} onChange={(e) => setMiddleName(e.target.value)} />
          <input type="date" value={enrolledAt} onChange={(e) => setEnrolledAt(e.target.value)} />
          <button type="submit" disabled={busy || groupId === null}>
            Добавить студента
          </button>
        </form>
      )}

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
