import type { SortState } from "../../utils/tableView";

/** Заголовок столбца, по которому можно сортировать таблицу. */
export default function SortHeader<K extends string>({
  label, sortKey, sort, onSort,
}: {
  label: string;
  sortKey: K;
  sort: SortState<K> | null;
  onSort: (key: K) => void;
}) {
  const active = sort?.key === sortKey ? sort.dir : null;
  return (
    <th aria-sort={active === "asc" ? "ascending" : active === "desc" ? "descending" : "none"}>
      <button type="button" className="sort-btn" onClick={() => onSort(sortKey)} title="Сортировать">
        {label}
        <span className="sort-btn__arrow" aria-hidden="true">{active === "asc" ? "▲" : active === "desc" ? "▼" : "↕"}</span>
      </button>
    </th>
  );
}
