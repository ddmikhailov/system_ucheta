import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import AssignCuratorModal from "../../components/AssignCuratorModal";
import type { DeleteResult, DepartmentAdmin, StudyGroupAdmin, UserAdmin } from "../../api/types";

export default function GroupsTab({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<StudyGroupAdmin[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [curators, setCurators] = useState<UserAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [assigning, setAssigning] = useState<number | null>(null);

  const [code, setCode] = useState("");
  const [course, setCourse] = useState(1);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [studyForm, setStudyForm] = useState("");

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editCode, setEditCode] = useState("");
  const [editCourse, setEditCourse] = useState(1);
  const [editStudyForm, setEditStudyForm] = useState("");

  function load() {
    api.get<StudyGroupAdmin[]>("/admin/groups").then(setRows).catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
    api.get<DepartmentAdmin[]>("/admin/departments").then((ds) => {
      setDepartments(ds);
      if (ds.length > 0 && departmentId === null) setDepartmentId(ds[0].id);
    });
    api
      .get<UserAdmin[]>("/admin/users")
      .then((us) => setCurators(us.filter((u) => u.role === "curator" || u.role === "deputy_curator")));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (departmentId === null) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/admin/groups", { code, course, department_id: departmentId, study_form: studyForm || null });
      setCode("");
      setStudyForm("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось создать группу");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(g: StudyGroupAdmin) {
    setEditingId(g.id);
    setEditCode(g.code);
    setEditCourse(g.course);
    setEditStudyForm(g.study_form ?? "");
  }

  async function saveEdit(groupId: number) {
    setError(null);
    try {
      await api.patch(`/admin/groups/${groupId}`, {
        code: editCode, course: editCourse, study_form: editStudyForm || null,
      });
      setEditingId(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function toggleActive(g: StudyGroupAdmin) {
    setError(null);
    try {
      await api.patch(`/admin/groups/${g.id}`, { is_active: !g.is_active });
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function removeGroup(g: StudyGroupAdmin) {
    if (!window.confirm(`Удалить группу «${g.code}» насовсем? Это необратимо.`)) return;
    setError(null);
    setNotice(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/groups/${g.id}`);
      setNotice(res.detail);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  async function endCuratorAssignment(g: StudyGroupAdmin) {
    if (g.curator_assignment_id === null) return;
    if (!window.confirm(`Снять ${g.curator_name} с группы «${g.code}»? История назначения сохранится.`)) return;
    setError(null);
    try {
      await api.post(`/admin/curator-assignments/${g.curator_assignment_id}/end`);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось снять куратора");
    }
  }

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      {notice && (
        <div className="day-status submitted">
          {notice} <button className="link-btn" onClick={() => setNotice(null)}>Скрыть</button>
        </div>
      )}
      <table className="dash-table">
        <thead>
          <tr>
            <th>Код</th>
            <th>Курс</th>
            <th>Форма обучения</th>
            <th>Куратор</th>
            <th>Активна</th>
            {canEdit && <th>Управление</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={g.id} className={!g.curator_name ? "not-submitted-row" : ""}>
              {editingId === g.id ? (
                <>
                  <td>
                    <input value={editCode} onChange={(e) => setEditCode(e.target.value)} style={{ width: 90 }} />
                  </td>
                  <td>
                    <input
                      type="number" min={1} max={4} value={editCourse}
                      onChange={(e) => setEditCourse(Number(e.target.value))}
                      style={{ width: 50 }}
                    />
                  </td>
                  <td>
                    <input value={editStudyForm} onChange={(e) => setEditStudyForm(e.target.value)} />
                  </td>
                </>
              ) : (
                <>
                  <td>{g.code}</td>
                  <td>{g.course}</td>
                  <td>{g.study_form ?? "—"}</td>
                </>
              )}
              <td>
                {g.curator_name ?? "нет куратора"}
                {canEdit && g.curator_assignment_id !== null && (
                  <button className="link-btn" onClick={() => endCuratorAssignment(g)}>
                    Снять
                  </button>
                )}
              </td>
              <td>{g.is_active ? "да" : "нет"}</td>
              {canEdit && (
                <td className="admin-row-actions">
                  {editingId === g.id ? (
                    <>
                      <button className="link-btn" onClick={() => saveEdit(g.id)}>
                        Сохранить
                      </button>
                      <button className="link-btn" onClick={() => setEditingId(null)}>
                        Отмена
                      </button>
                    </>
                  ) : (
                    <>
                      <button className="link-btn" onClick={() => startEdit(g)}>
                        Изменить
                      </button>
                      <button className="link-btn" onClick={() => setAssigning(g.id)}>
                        Назначить куратора
                      </button>
                      <button className="link-btn" onClick={() => toggleActive(g)}>
                        {g.is_active ? "В архив" : "Вернуть из архива"}
                      </button>
                      {!g.is_active && (
                        <button className="link-btn" onClick={() => removeGroup(g)}>
                          Удалить насовсем
                        </button>
                      )}
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {canEdit && (
        <form className="inline-form" onSubmit={handleCreate}>
          <input placeholder="Код группы" value={code} onChange={(e) => setCode(e.target.value)} required />
          <input
            type="number"
            min={1}
            max={4}
            value={course}
            onChange={(e) => setCourse(Number(e.target.value))}
            style={{ width: 60 }}
          />
          <select value={departmentId ?? ""} onChange={(e) => setDepartmentId(Number(e.target.value))}>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <input placeholder="Форма обучения (необязательно)" value={studyForm} onChange={(e) => setStudyForm(e.target.value)} />
          <button type="submit" disabled={busy}>
            Добавить группу
          </button>
        </form>
      )}

      {assigning !== null && (
        <AssignCuratorModal
          groupId={assigning}
          curators={curators}
          onClose={() => setAssigning(null)}
          onSaved={() => {
            setAssigning(null);
            load();
          }}
        />
      )}
    </div>
  );
}
