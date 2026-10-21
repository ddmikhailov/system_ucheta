import type { MouseEvent, ReactNode } from "react";
import { Link } from "react-router-dom";
import { useGoBack } from "../hooks/useGoBack";

/** Кнопка «← Назад» в интерфейсе. Если пользователь пришёл сюда изнутри платформы — возвращает
 * ровно туда, откуда пришёл (та же группа, вкладка, фильтры и прокрутка), как браузерная «Назад».
 * Если страницу открыли напрямую (закладка, обновление в новой вкладке) — ведёт на `to`.
 * Подпись `children` показывается, когда возврат идёт на тот же раздел, что и `to`;
 * если пришли из другого места — честное «← Назад». */
export default function BackLink({ to, children, className = "link-btn" }: { to: string; children: ReactNode; className?: string }) {
  const { from: prev, goBack: back } = useGoBack(to);

  if (!prev) {
    return (
      <Link to={to} className={className}>
        {children}
      </Link>
    );
  }

  const samePlace = prev.split("?")[0] === to.split("?")[0];
  function goBack(e: MouseEvent<HTMLAnchorElement>) {
    // Ctrl/Cmd-клик и средняя кнопка — открыть в новой вкладке, как обычная ссылка.
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    back();
  }
  return (
    <a href={prev} className={className} onClick={goBack}>
      {samePlace ? children : "← Назад"}
    </a>
  );
}
