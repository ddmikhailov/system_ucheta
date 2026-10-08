import { plural } from "../../utils/plural";

/** «Показано 5 из 44» и кнопка «Сбросить» — под фильтрами таблицы. */
export default function ResultsBar({
  shown, total, filtered, onReset,
}: {
  shown: number;
  total: number;
  filtered: boolean;
  onReset: () => void;
}) {
  if (total === 0) return null;
  return (
    <p className="hint results-bar" role="status">
      Показано {shown} из {total} {plural(total, ["записи", "записей", "записей"])}
      {filtered && (
        <>
          {" · "}
          <button type="button" className="link-btn" onClick={onReset}>Сбросить фильтры</button>
        </>
      )}
    </p>
  );
}
