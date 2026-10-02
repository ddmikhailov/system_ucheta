import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { STUDENT_STATUS_LABELS } from "../constants/studentStatus";
import type { StudyGroupAdmin } from "../api/types";

interface StudentRow {
  id: number;
  full_name: string;
  group_code: string;
  status: string;
}

// Поиск студента по ФИО/группе — вход в карточку и досье для соц. педагога,
// психолога и администрации. Фильтр группы живёт в адресной строке.
export default function StudentsSearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const groupId = searchParams.get("group") ?? "";
  const [query, setQuery] = useState("");
  const [groups, setGroups] = useState<StudyGroupAdmin[]>([]);
  const [rows, setRows] = useState<StudentRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<StudyGroupAdmin[]>("/admin/groups")
      .then((all) => setGroups(all.filter((g) => g.is_active)))
      .catch(() => setGroups([]));
  }, []);

  useEffect(() => {
    // Небольшая задержка, чтобы не слать запрос на каждую набранную букву.
    const timer = setTimeout(() => {
      const params = new URLSearchParams();
      if (query.trim()) params.set("q", query.trim());
      if (groupId) params.set("group_id", groupId);
      params.set("limit", "100");
      api
        .get<StudentRow[]>(`/students?${params.toString()}`)
        .then((r) => {
          setRows(r);
          setError(null);
        })
        .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить список"));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, groupId]);

  function setGroup(value: string) {
    const params = new URLSearchParams(searchParams);
    if (value) params.set("group", value);
    else params.delete("group");
    setSearchParams(params, { replace: true });
  }

  return (
    <div>
      <div className="toolbar">
        <input
          type="search"
          placeholder="Фамилия, имя или группа"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <select value={groupId} onChange={(e) => setGroup(e.target.value)}>
          <option value="">Все группы</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.code}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="error-text">{error}</div>}
      {rows === null ? (
        <p className="hint">Загрузка…</p>
      ) : rows.length === 0 ? (
        <p className="hint">Никого не найдено.</p>
      ) : (
        <>
          <table className="dash-table">
            <thead>
              <tr>
                <th>Студент</th>
                <th>Группа</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id}>
                  <td data-label="Студент">
                    <Link to={`/students/${s.id}`} className="link-btn">
                      {s.full_name}
                    </Link>
                  </td>
                  <td data-label="Группа">{s.group_code}</td>
                  <td data-label="Статус">{STUDENT_STATUS_LABELS[s.status] ?? s.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length >= 100 && <p className="hint">Показаны первые 100 — уточните запрос или выберите группу.</p>}
        </>
      )}
    </div>
  );
}
