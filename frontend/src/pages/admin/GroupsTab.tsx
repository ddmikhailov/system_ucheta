import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import AssignCuratorModal from "../../components/AssignCuratorModal";
import type { DepartmentAdmin, StudyGroupAdmin, UserAdmin } from "../../api/types";

export default function GroupsTab({ canEdit }: { canEdit: boolean }) {
  const [rows, setRows] = useState<StudyGroupAdmin[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [curators, setCurators] = useState<UserAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [assigning, setAssigning] = useState<number | null>(null);

  const [code, setCode] = useState("");
  const [course, setCourse] = useState(1);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [studyForm, setStudyForm] = useState("");

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

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      <table className="dash-table">
        <thead>
          <tr>
            <th>Код</th>
            <th>Курс</th>
            <th>Куратор</th>
            <th>Активна</th>
            {canEdit && <th></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={g.id} className={!g.curator_name ? "not-submitted-row" : ""}>
              <td>{g.code}</td>
              <td>{g.course}</td>
              <td>{g.curator_name ?? "нет куратора"}</td>
              <td>{g.is_active ? "да" : "нет"}</td>
              {canEdit && (
                <td>
                  <button className="link-btn" onClick={() => setAssigning(g.id)}>
                    Назначить куратора
                  </button>
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
