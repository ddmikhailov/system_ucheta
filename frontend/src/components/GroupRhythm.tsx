import type { MyDayRhythmDay } from "../api/types";
import { formatDayMonthRu } from "../utils/date";
import { plural } from "../utils/plural";

export type RhythmItem = {
  date: string;
  kind: MyDayRhythmDay["kind"] | "excused";
  absent?: number;
  /** Своя подпись дня (например, отметка студента); по умолчанию — по виду дня. */
  title?: string;
};

const TITLES: Record<RhythmItem["kind"], string> = {
  off: "занятий нет",
  missing: "день не сдан",
  ok: "без пропусков без причины",
  absent: "пропуски без причины",
  excused: "отсутствие по уважительной причине",
};

/** «Ритм группы»: посещаемость по дням одной полосой. Высокий фиолетовый столбик — все на месте
 * (или отсутствуют по уважительной причине), красный — пропуски без причины, пустой контур — день
 * не сдан, низкая серая черта — занятий нет. */
export default function GroupRhythm({ days, label: customLabel }: { days: RhythmItem[]; label?: string }) {
  if (days.length === 0) return null;
  const study = days.filter((d) => d.kind !== "off");
  const absent = days.filter((d) => d.kind === "absent").length;
  const missing = days.filter((d) => d.kind === "missing").length;
  const label =
    customLabel ??
    `Ритм за ${days.length} ${plural(days.length, ["день", "дня", "дней"])}: учебных ${study.length}, ` +
    `с пропусками без причины ${absent}, не сдано ${missing}`;
  return (
    <div className="rhythm" role="img" aria-label={label}>
      {days.map((d) => (
        <i
          key={d.date}
          className={`rhythm__day rhythm__day--${d.kind}`}
          title={`${formatDayMonthRu(d.date)}: ${d.title ?? (d.kind === "absent" && d.absent ? `${TITLES.absent} — ${d.absent}` : TITLES[d.kind])}`}
        />
      ))}
    </div>
  );
}
