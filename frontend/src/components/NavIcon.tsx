// Значки разделов для меню: тонкая линия, один стиль на все. Подпись всегда рядом — значок её не заменяет.

export type NavIconName = "day" | "groups" | "tasks" | "inbox" | "charts" | "students" | "passport" | "individual" | "plan" | "report" | "id" | "admin" | "more";

const PATHS: Record<NavIconName, string> = {
  // солнце над линией горизонта
  day: "M4 17h16M7 17a5 5 0 0 1 10 0M12 4v2M5.6 7.6l1.4 1.4M18.4 7.6 17 9M3 13h2M19 13h2",
  // два человека
  groups: "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM3 19c0-3 2.7-5 6-5s6 2 6 5M16 5.5a3 3 0 0 1 0 5.6M18 14.3c1.8.6 3 2 3 4.7",
  // список с галочками
  tasks: "M10 6h10M10 12h10M10 18h10M4 6l1.5 1.5L8 5M4 12l1.5 1.5L8 11M4 18l1.5 1.5L8 17",
  // лоток входящих
  inbox: "M4 13l2.5-7h11L20 13M4 13v5h16v-5M4 13h4.5a3.5 3.5 0 0 0 7 0H20",
  // столбики
  charts: "M4 20h16M7 16v-5M12 16V6M17 16v-8",
  // человек и лупа
  students: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM3 20c0-3.3 2.7-5.5 6-5.5 1.3 0 2.5.3 3.4.9M17 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM21 21l-1.9-1.9",
  // карточка-документ
  passport: "M5 4h14v16H5zM9 9a2 2 0 1 0 4 0 2 2 0 0 0-4 0M8 15c.6-1.4 1.8-2 3-2s2.4.6 3 2M15 8h1M15 11h1",
  // облачко разговора
  individual: "M5 5h14v10H10l-4 4v-4H5zM9 9h6M9 12h4",
  // календарь
  plan: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4M8 14h2M12 14h2M8 17h2",
  // удостоверение с лицом
  id: "M4 6h16v12H4zM9 12a2 2 0 1 0 0-.01M6.5 16c.5-1.6 1.6-2.4 2.5-2.4s2 .8 2.5 2.4M14 10h4M14 13h3",
  // лист с галочкой
  report: "M6 3h9l4 4v14H6zM14 3v5h5M9 14l2 2 4-4",
  // шестерёнка (упрощённая)
  admin: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1",
  // три точки
  more: "M6 12h.01M12 12h.01M18 12h.01",
};

export default function NavIcon({ name }: { name: NavIconName }) {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <path d={PATHS[name]} fill="none" stroke="currentColor" strokeWidth={name === "more" ? 3 : 1.7} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
