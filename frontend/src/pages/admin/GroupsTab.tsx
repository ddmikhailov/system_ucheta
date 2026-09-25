import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import AssignCuratorModal from "../../components/AssignCuratorModal";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { useScrollToTopOnChange } from "../../hooks/useScrollToTopOnChange";
import type { DeleteResult, DepartmentAdmin, StudyGroupAdmin, UserAdmin } from "../../api/types";

export default function GroupsTab({ canEdit, canCreate }: { canEdit: boolean; canCreate: boolean }) {
  const [rows, setRows] = useState<StudyGroupAdmin[]>([]);
  const [departments, setDepartments] = useState<DepartmentAdmin[]>([]);
  const [curators, setCurators] = useState<UserAdmin[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  useScrollToTopOnChange(error, notice);
  const [busy, setBusy] = useState(false);

  const [code, setCode] = useState("");
  const [course, setCourse] = useState(1);
  const [departmentId, setDepartmentId] = useState<number | null>(null);
  const [studyForm, setStudyForm] = useState("");

  // Раньше на каждую строку было 4-5 кнопок сразу (см. TODO.md 4) — теперь
  // всё управление группой (редактирование, куратор, архив, удаление) в
  // одном модальном окне, как в UsersTab.
  const [detailId, setDetailId] = useState<number | null>(null);

  // Архивные группы не мешаются в основном списке — их можно найти отдельно.
  const [showArchived, setShowArchived] = useState(false);

  function load() {
    api.get<StudyGroupAdmin[]>("/admin/groups").then(setRows).catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка"));
    api.get<DepartmentAdmin[]>("/admin/departments").then((ds) => {
      setDepartments(ds);
      if (ds.length > 0 && departmentId === null) setDepartmentId(ds[0].id);
    });
    api
      .get<UserAdmin[]>("/admin/users")
      .then((us) => setCurators(us.filter((u) => u.is_active && (u.role === "curator" || u.role === "deputy_curator"))));
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

  const visibleRows = showArchived ? rows : rows.filter((g) => g.is_active);
  const archivedCount = rows.length - rows.filter((g) => g.is_active).length;
  const detailGroup = rows.find((g) => g.id === detailId) ?? null;

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
          </tr>
        </thead>
        <tbody>
          {visibleRows.map((g) => (
            <tr key={g.id} className={!g.curator_name ? "not-submitted-row" : ""}>
              <td>
                {canEdit ? (
                  <button className="link-btn" onClick={() => setDetailId(g.id)}>
                    {g.code}
                  </button>
                ) : (
                  g.code
                )}
              </td>
              <td>{g.course}</td>
              <td>{g.study_form ?? "—"}</td>
              <td>{g.curator_name ?? "нет куратора"}</td>
              <td>{g.is_active ? "да" : "нет"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {canCreate && (
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

      {detailGroup && (
        <GroupDetailModal
          group={detailGroup}
          curators={curators}
          onClose={() => setDetailId(null)}
          onChanged={load}
          setNotice={setNotice}
          setError={setError}
        />
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

function GroupDetailModal({
  group,
  curators,
  onClose,
  onChanged,
  setNotice,
  setError,
}: {
  group: StudyGroupAdmin;
  curators: UserAdmin[];
  onClose: () => void;
  onChanged: () => void;
  setNotice: (n: string | null) => void;
  setError: (e: string | null) => void;
}) {
  const [editCode, setEditCode] = useState(group.code);
  const [editCourse, setEditCourse] = useState(group.course);
  const [editStudyForm, setEditStudyForm] = useState(group.study_form ?? "");
  const [assigning, setAssigning] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  useEscapeKey(onClose);

  async function saveEdit() {
    setLocalError(null);
    try {
      await api.patch(`/admin/groups/${group.id}`, {
        code: editCode, course: editCourse, study_form: editStudyForm || null,
      });
      onChanged();
    } catch (err) {
      setLocalError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function toggleActive() {
    setLocalError(null);
    try {
      await api.patch(`/admin/groups/${group.id}`, { is_active: !group.is_active });
      onChanged();
      onClose();
    } catch (err) {
      setLocalError(err instanceof ApiError ? err.message : "Не удалось сохранить");
    }
  }

  async function removeGroup() {
    if (!window.confirm(`Удалить группу «${group.code}» насовсем? Это необратимо.`)) return;
    setLocalError(null);
    setNotice(null);
    try {
      const res = await api.delete<DeleteResult>(`/admin/groups/${group.id}`);
      setNotice(res.detail);
      onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось удалить");
    }
  }

  async function endCuratorAssignment() {
    if (group.curator_assignment_id === null) return;
    if (!window.confirm(`Снять ${group.curator_name} с группы «${group.code}»? История назначения сохранится.`)) return;
    setLocalError(null);
    try {
      await api.post(`/admin/curator-assignments/${group.curator_assignment_id}/end`);
      onChanged();
    } catch (err) {
      setLocalError(err instanceof ApiError ? err.message : "Не удалось снять куратора");
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={group.code} onClick={(e) => e.stopPropagation()}>
        <h3>Группа {group.code}</h3>

        {localError && <div className="error-text">{localError}</div>}

        <label>
          Код
          <input value={editCode} onChange={(e) => setEditCode(e.target.value)} />
        </label>
        <label>
          Курс
          <input type="number" min={1} max={4} value={editCourse} onChange={(e) => setEditCourse(Number(e.target.value))} />
        </label>
        <label>
          Форма обучения
          <input value={editStudyForm} onChange={(e) => setEditStudyForm(e.target.value)} placeholder="необязательно" />
        </label>
        <div className="actions">
          <button onClick={saveEdit}>Сохранить</button>
        </div>

        <hr />

        <p className="hint">Куратор: {group.curator_name ?? "нет куратора"}</p>
        <div className="admin-row-actions">
          <button className="link-btn" onClick={() => setAssigning(true)}>
            {group.curator_name ? "Сменить куратора" : "Назначить куратора"}
          </button>
          {group.curator_assignment_id !== null && (
            <button className="link-btn" onClick={endCuratorAssignment}>
              Снять куратора
            </button>
          )}
        </div>

        <hr />

        <div className="actions">
          <button onClick={onClose}>Закрыть</button>
          <button className="link-btn" onClick={toggleActive}>
            {group.is_active ? "В архив" : "Вернуть из архива"}
          </button>
          {!group.is_active && (
            <button className="link-btn" onClick={removeGroup}>
              Удалить насовсем
            </button>
          )}
        </div>

        {assigning && (
          <AssignCuratorModal
            groupId={group.id}
            curators={curators}
            onClose={() => setAssigning(false)}
            onSaved={() => {
              setAssigning(false);
              onChanged();
            }}
          />
        )}
      </div>
    </div>
  );
}
