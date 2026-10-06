import { PLATFORM_NAME } from "../constants/brand";

/** Логотип колледжа в двух вариантах из брендбука: цветной — для светлой темы, белый — для
 * тёмной. Файлы вставлены как есть (без обрезки, перекраски и наложений); какой показать,
 * решает CSS по той же теме, что и остальная страница (см. .college-logo в profile.css). */
export function CollegeLogo({ className = "" }: { className?: string }) {
  return (
    <span className={`college-logo ${className}`.trim()}>
      <img className="college-logo__img college-logo__img--color" src="/kait20-logo-color.png" alt="КАИТ №20" />
      <img className="college-logo__img college-logo__img--white" src="/kait20-logo-white.png" alt="КАИТ №20" />
    </span>
  );
}

/** Логотип и под ним — название платформы обычным текстом (сам логотип не меняется). */
export default function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand-mark${compact ? " brand-mark--compact" : ""}`}>
      <CollegeLogo />
      {!compact && <span className="brand-mark__name">{PLATFORM_NAME}</span>}
    </span>
  );
}
