import { MARK_LABELS } from "../utils/statusMark";
import type { MarkKind } from "../utils/statusMark";

// Значок статуса назначения задачи: у каждого статуса своя форма и свой цвет, чтобы его можно было
// различить и без цвета (дальтонизм, ч/б печать). Красный — только просрочка и возврат: срочное
// громко, сделанное тихо (см. futures.md, «Ход этапа 13»).

function Shape({ kind }: { kind: MarkKind }) {
  switch (kind) {
    case "overdue":
      return (
        <>
          <circle cx="9" cy="9" r="8" className="sm-fill-hot" />
          <path d="M9 4.6v5.2" className="sm-on-fill" strokeWidth="2" strokeLinecap="round" />
          <circle cx="9" cy="12.9" r="1.2" className="sm-on-fill-dot" />
        </>
      );
    case "returned":
      return (
        <>
          <circle cx="9" cy="9" r="7.5" fill="none" className="sm-stroke-hot" strokeWidth="2" />
          <path d="M6 9h6M6 9l2.4-2.4M6 9l2.4 2.4" fill="none" className="sm-stroke-hot" strokeWidth="1.8" strokeLinecap="round" />
        </>
      );
    case "in_progress":
      return (
        <>
          <circle cx="9" cy="9" r="7.5" fill="none" className="sm-stroke-violet" strokeWidth="2" />
          <path d="M9 1.5a7.5 7.5 0 0 1 0 15z" className="sm-fill-violet" />
        </>
      );
    case "submitted":
      return (
        <>
          <circle cx="9" cy="9" r="7.5" fill="none" className="sm-stroke-violet" strokeWidth="2" strokeDasharray="3 2.2" />
          <circle cx="9" cy="9" r="2.4" className="sm-fill-violet" />
        </>
      );
    case "accepted":
      return (
        <>
          <circle cx="9" cy="9" r="8" className="sm-fill-ok" />
          <path d="M5.4 9.3l2.4 2.4 4.8-5" fill="none" className="sm-on-fill" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </>
      );
    case "locked":
      return (
        <>
          <rect x="4" y="8" width="10" height="7.5" rx="2" className="sm-fill-idle" />
          <path d="M6 8V6a3 3 0 0 1 6 0v2" fill="none" className="sm-stroke-idle" strokeWidth="1.8" />
        </>
      );
    default:
      return <circle cx="9" cy="9" r="7.5" fill="none" className="sm-stroke-idle" strokeWidth="2" />;
  }
}

/** Значок статуса. По умолчанию подписан для экранного диктора; withLabel — ещё и видимой подписью. */
export default function StatusMark({ kind, withLabel = false, label }: { kind: MarkKind; withLabel?: boolean; label?: string }) {
  const text = label ?? MARK_LABELS[kind];
  return (
    <span className={`status-mark status-mark--${kind}`}>
      <svg viewBox="0 0 18 18" width="18" height="18" role="img" aria-label={withLabel ? undefined : text} aria-hidden={withLabel ? true : undefined}>
        <Shape kind={kind} />
      </svg>
      {withLabel && <span className="status-mark__label">{text}</span>}
    </span>
  );
}
