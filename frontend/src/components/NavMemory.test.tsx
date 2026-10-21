import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import BackLink from "./BackLink";
import NavMemory from "./NavMemory";
import { useEntryState } from "../hooks/useEntryState";
import { useUrlFlag, useUrlNumber, useUrlParam, useUrlSort } from "../hooks/useUrlState";
import { clearNavMemory, previousUrl } from "../utils/navMemory";

function Where() {
  const { pathname, search } = useLocation();
  return <output aria-label="адрес">{pathname + search}</output>;
}

function List() {
  const [group, setGroup] = useUrlNumber("group");
  const [q, setQ] = useUrlParam("q");
  const [archived, setArchived] = useUrlFlag("archived");
  const [sort, setSort] = useUrlSort(["code", "course"] as const);
  const [note, setNote] = useEntryState("note", "");
  return (
    <div>
      <p>группа {group ?? "нет"}; поиск «{q}»; архив {archived ? "да" : "нет"}; сортировка {sort ? `${sort.key}.${sort.dir}` : "нет"}</p>
      <button onClick={() => setGroup(12)}>Группа 12</button>
      <button
        onClick={() => {
          // Несколько изменений подряд в одном обработчике не затирают друг друга.
          setQ("иван");
          setArchived(true);
          setSort({ key: "code", dir: "desc" });
        }}
      >
        Фильтры
      </button>
      <button onClick={() => setNote("заметка")}>Заметка</button>
      <p>заметка «{note}»</p>
      <Link to="/students/5">Студент</Link>
    </div>
  );
}

function Card() {
  return (
    <div>
      <BackLink to="/admin?tab=students">← К списку студентов</BackLink>
      <Link to="/admin">Админка из меню</Link>
    </div>
  );
}

function renderApp(initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <NavMemory />
      <Where />
      <Routes>
        <Route path="/admin" element={<List />} />
        <Route path="/students/:id" element={<Card />} />
        <Route path="/my-day" element={<Link to="/students/5">Студент</Link>} />
      </Routes>
    </MemoryRouter>
  );
}

const address = () => screen.getByRole("status", { name: "адрес" }).textContent;

describe("Память пути и состояния экрана", () => {
  it("выбор группы и фильтры пишутся в адрес; «Назад» из карточки возвращает туда же", async () => {
    const user = userEvent.setup();
    renderApp("/admin?tab=students");
    await user.click(screen.getByRole("button", { name: "Группа 12" }));
    await user.click(screen.getByRole("button", { name: "Фильтры" }));
    expect(address()).toBe("/admin?tab=students&group=12&q=%D0%B8%D0%B2%D0%B0%D0%BD&archived=1&sort=code.desc");
    expect(screen.getByText("группа 12; поиск «иван»; архив да; сортировка code.desc")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Студент" }));
    const back = screen.getByRole("link", { name: "← К списку студентов" });
    expect(back).toHaveAttribute("href", "/admin?tab=students&group=12&q=%D0%B8%D0%B2%D0%B0%D0%BD&archived=1&sort=code.desc");
    await user.click(back);
    expect(screen.getByText("группа 12; поиск «иван»; архив да; сортировка code.desc")).toBeInTheDocument();
  });

  it("состояние без адреса (useEntryState) возвращается по «Назад», а новый заход из меню начинает заново", async () => {
    const user = userEvent.setup();
    renderApp("/admin");
    await user.click(screen.getByRole("button", { name: "Заметка" }));
    await user.click(screen.getByRole("button", { name: "Группа 12" })); // замена записи истории не теряет заметку
    await user.click(screen.getByRole("link", { name: "Студент" }));
    await user.click(screen.getByRole("link", { name: "← К списку студентов" }));
    expect(screen.getByText("заметка «заметка»")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Студент" }));
    await user.click(screen.getByRole("link", { name: "Админка из меню" }));
    expect(screen.getByText("заметка «»")).toBeInTheDocument();
    expect(screen.getByText(/группа нет/)).toBeInTheDocument();
  });

  it("открыли карточку напрямую — кнопка ведёт на запасной адрес", () => {
    renderApp("/students/5");
    expect(screen.getByRole("link", { name: "← К списку студентов" })).toHaveAttribute("href", "/admin?tab=students");
  });

  it("пришли из другого раздела — кнопка честно называется «← Назад» и возвращает туда", async () => {
    const user = userEvent.setup();
    renderApp("/my-day");
    await user.click(screen.getByRole("link", { name: "Студент" }));
    await user.click(screen.getByRole("link", { name: "← Назад" }));
    expect(address()).toBe("/my-day");
  });

  it("выход из платформы стирает память пути", async () => {
    const user = userEvent.setup();
    renderApp("/my-day");
    await user.click(screen.getByRole("link", { name: "Студент" }));
    expect(Object.keys(sessionStorage).some((k) => k.startsWith("nav:"))).toBe(true);
    clearNavMemory();
    expect(Object.keys(sessionStorage).some((k) => k.startsWith("nav:"))).toBe(false);
    expect(previousUrl("любой")).toBeNull();
  });
});
