import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { AttendanceChange } from "../../api/types";
import ChangeCard from "./ChangeCard";

/** Исправления прошлых дней, которые ждут решения (зав. отделением — своего отделения). Пусто — блока нет. */
export default function ChangeReviewList({ onOpenDay }: { onOpenDay: (groupId: number, date: string) => void }) {
  const [items, setItems] = useState<AttendanceChange[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<AttendanceChange[]>("/attendance-changes")
      .then((rows) => {
        setItems(Array.isArray(rows) ? rows : []);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить исправления"));
  }, []);

  useEffect(load, [load]);

  if (error) return <div className="error-text">{error}</div>;
  if (items.length === 0) return null;
  return (
    <section className="change-review" aria-label="Исправления на проверке">
      <h3>
        Исправления на проверке <span className="tabbar__badge">{items.length}</span>
      </h3>
      <div className="change-review__list">
        {items.map((c) => (
          <ChangeCard key={c.id} change={c} canReview showDay onDone={load} onOpenDay={() => onOpenDay(c.study_group_id, c.date)} />
        ))}
      </div>
    </section>
  );
}
