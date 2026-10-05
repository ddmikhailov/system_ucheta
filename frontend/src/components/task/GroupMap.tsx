import { Link } from "react-router-dom";
import type { TaskAssignmentSummary } from "../../api/types";
import { MARK_LABELS, markKind } from "../../utils/statusMark";

/** Карта групп по задаче: плитка на группу, цвет — статус, строки — курсы. 44 группы видны одним
 * экраном, а не длинной таблицей. Плитка ведёт к ответу группы. */
export default function GroupMap({ assignments }: { assignments: TaskAssignmentSummary[] }) {
  const courses = [...new Set(assignments.map((a) => a.course))].sort((a, b) => a - b);
  return (
    <div className="group-map">
      {courses.map((course) => (
        <div key={course} className="group-map__row">
          <span className="group-map__course">{course} курс</span>
          <ul className="group-map__tiles">
            {assignments
              .filter((a) => a.course === course)
              .map((a) => {
                const kind = markKind(a);
                const title = `${a.group_code}, ${a.department_name}: ${MARK_LABELS[kind]}`;
                return (
                  <li key={a.id}>
                    <Link to={`/tasks/assignment/${a.id}`} className={`group-tile group-tile--${kind}`} title={title} aria-label={title}>
                      {a.group_code}
                    </Link>
                  </li>
                );
              })}
          </ul>
        </div>
      ))}
      <div className="group-map__legend" aria-hidden="true">
        {(["accepted", "submitted", "in_progress", "returned", "new", "overdue", "locked"] as const).map((k) => (
          <span key={k}>
            <i className={`group-tile--${k}`} />
            {MARK_LABELS[k].toLowerCase()}
          </span>
        ))}
      </div>
    </div>
  );
}
