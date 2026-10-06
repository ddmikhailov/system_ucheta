import type { ReactNode } from "react";

/** Две буквы для «аватара»: фамилия и имя. */
function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

/** Шапка карточки человека (студент, пользователь): инициалы, имя, пометка статуса,
 * короткая строка «где и кто», а под ней — главные цифры (Kpi). Сначала ответ на вопрос
 * «всё ли в порядке?», подробности — во вкладках ниже. */
export function ProfileHero({
  name,
  badge,
  meta,
  avatar,
  children,
}: {
  name: string;
  /** Текст в квадрате слева; по умолчанию — инициалы из имени. */
  avatar?: string;
  badge?: ReactNode;
  meta: (string | null | undefined)[];
  children?: ReactNode;
}) {
  return (
    <header className="profile-hero">
      <div className="profile-hero__top">
        <div className="profile-hero__avatar" aria-hidden="true">
          {avatar ?? initials(name)}
        </div>
        <div className="profile-hero__main">
          <div className="profile-hero__title">
            <h2>{name}</h2>
            {badge}
          </div>
          <p className="profile-hero__meta">
            {meta.filter(Boolean).map((m) => (
              <span key={m}>{m}</span>
            ))}
          </p>
        </div>
      </div>
      {children && <div className="kpi-row">{children}</div>}
    </header>
  );
}

export function Kpi({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn" | "hot";
  /** Пояснение под цифрой: «из 18 учебных дней». */
  hint?: string;
}) {
  return (
    <div className={`kpi${tone ? ` kpi--${tone}` : ""}`}>
      <span className="kpi__value">{value}</span>
      <span className="kpi__label">{label}</span>
      {hint && <span className="kpi__hint">{hint}</span>}
    </div>
  );
}
