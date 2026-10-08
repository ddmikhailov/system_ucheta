import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import { renderPage } from "../test/utils";
import PassportPage from "./PassportPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});

const get = vi.mocked(api.get);
const download = vi.mocked(downloadFile);

const CATEGORIES = [
  { key: "orphan", title: "Сироты" },
  { key: "ovz", title: "ОВЗ" },
];

const row = (id: number, code: string, counts: Record<string, number | null>) => ({
  group_id: id, group_code: code, course: 1, department_name: "Диджитал", students_total: 25, minors: 4,
  budget: 20, contract: 5, no_guardians: 7, dossier_empty: 3, counts,
});

function summary(over = {}) {
  return {
    special_available: true,
    categories: CATEGORIES,
    rows: [row(1, "СА172", { orphan: 2, ovz: 0 }), row(2, "ИИ112", { orphan: 1, ovz: 3 })],
    totals: { ...row(0, "Итого", { orphan: 3, ovz: 3 }), students_total: 50 },
    ...over,
  };
}

const groupPassport = (over = {}) => ({
  group_id: 1, group_code: "СА172", course: 1, department_name: "Диджитал", students_total: 25, minors: 4, adults: 20,
  birth_date_missing: 1, budget: 20, contract: 5, funding_missing: 0, no_guardians: 7, dossier_empty: 3, special_available: true,
  categories: [
    { key: "orphan", title: "Сироты", count: 2, names: ["Иванов И.", "Петров П."] },
    { key: "ovz", title: "ОВЗ", count: 0, names: [] },
  ],
  ...over,
});

beforeEach(() => {
  get.mockReset();
  download.mockReset();
  download.mockResolvedValue(undefined);
});

function mockApi(over: { summary?: object; group?: object } = {}) {
  get.mockImplementation(async (path: string) => {
    if (path.startsWith("/passport/summary")) return over.summary ?? summary();
    if (path.startsWith("/passport/group/")) return over.group ?? groupPassport();
    if (path.startsWith("/admin/departments")) return [{ id: 1, name: "Диджитал", is_active: true }, { id: 2, name: "Моссовет", is_active: true }];
    throw new Error(`неожиданный запрос ${path}`);
  });
}

describe("PassportPage — сводка", () => {
  it("показывает строки по группам, итог и столбцы категорий", async () => {
    mockApi();
    renderPage(<PassportPage />, { role: "admin" });
    expect(await screen.findByRole("cell", { name: "СА172" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Сироты" })).toBeInTheDocument();
    const total = screen.getByRole("cell", { name: "Итого" }).closest("tr") as HTMLElement;
    expect(within(total).getByText("50")).toBeInTheDocument();
  });

  it("одна группа — без строки «Итого»", async () => {
    mockApi({ summary: summary({ rows: [row(1, "СА172", { orphan: 2, ovz: 0 })] }) });
    renderPage(<PassportPage />, { role: "curator", user: { groups: [{ id: 1, code: "СА172", course: 1 }] } });
    await screen.findByRole("cell", { name: "СА172" });
    expect(screen.queryByRole("cell", { name: "Итого" })).not.toBeInTheDocument();
  });

  it("нет доступных групп — сообщение вместо таблицы", async () => {
    mockApi({ summary: summary({ rows: [] }) });
    renderPage(<PassportPage />, { role: "curator" });
    expect(await screen.findByText("Нет доступных групп.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("без ключа шифрования категории показываются прочерками и есть пояснение", async () => {
    mockApi({ summary: summary({ special_available: false, rows: [row(1, "СА172", { orphan: null, ovz: null })] }) });
    renderPage(<PassportPage />, { role: "admin" });
    expect(await screen.findByText(/не задан ключ шифрования/)).toBeInTheDocument();
    const r = screen.getByRole("cell", { name: "СА172" }).closest("tr") as HTMLElement;
    expect(within(r).getAllByText("—")).toHaveLength(2);
  });

  it("куратору без доступа к особым категориям — понятная фраза без технических слов; причину видит администратор", async () => {
    mockApi({ summary: summary({ special_available: false, rows: [row(1, "СА172", { orphan: null, ovz: null })] }) });
    renderPage(<PassportPage />, { role: "curator", user: { groups: [{ id: 1, code: "СА172", course: 1 }] } });
    expect(await screen.findByText(/Особые категории \(здоровье, учёт\) сейчас не показываются/)).toBeInTheDocument();
    expect(screen.queryByText(/ключ шифрования|DOSSIER_ENCRYPTION_KEY/)).not.toBeInTheDocument();
  });

  it("широкая таблица сводки лежит в прокручиваемой обёртке, а не растягивает страницу", async () => {
    mockApi();
    renderPage(<PassportPage />, { role: "admin" });
    const table = await screen.findByRole("table");
    expect(table.closest(".table-scroll")).not.toBeNull();
  });

  it("фильтр по отделению перезапрашивает сводку, у куратора фильтра нет", async () => {
    const user = userEvent.setup();
    mockApi();
    const { unmount } = renderPage(<PassportPage />, { role: "admin" });
    await screen.findByRole("cell", { name: "СА172" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Отделение" }), "2");
    await waitFor(() => expect(get).toHaveBeenCalledWith("/passport/summary?department_id=2"));
    unmount();

    mockApi();
    renderPage(<PassportPage />, { role: "curator" });
    await screen.findByRole("cell", { name: "СА172" });
    expect(screen.queryByRole("combobox", { name: "Отделение" })).not.toBeInTheDocument();
  });

  it("выгрузка сводки учитывает выбранное отделение; ошибка скачивания показывается", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<PassportPage />, { role: "admin" });
    await screen.findByRole("cell", { name: "СА172" });
    await user.selectOptions(await screen.findByRole("combobox", { name: "Отделение" }), "2");
    await user.click(screen.getByRole("button", { name: "Экспорт сводки в Excel" }));
    expect(download).toHaveBeenCalledWith("/passport/export?department_id=2", "social_passport.xlsx");

    download.mockRejectedValueOnce(new ApiError(403, "Нет доступа"));
    await user.click(screen.getByRole("button", { name: "Экспорт сводки в Excel" }));
    expect(await screen.findByText("Нет доступа")).toBeInTheDocument();
  });

  it("ошибка загрузки показывается", async () => {
    get.mockRejectedValue(new ApiError(500, "Сервер недоступен"));
    renderPage(<PassportPage />, { role: "admin" });
    expect(await screen.findByText("Сервер недоступен")).toBeInTheDocument();
  });
});

describe("PassportPage — паспорт группы", () => {
  it("клик по строке открывает паспорт со списками по категориям", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<PassportPage />, { role: "admin" });
    await user.click(await screen.findByRole("cell", { name: "СА172" }));
    expect(await screen.findByRole("heading", { name: /Социальный паспорт группы СА172/ })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/passport/group/1");
    await user.click(screen.getByRole("tab", { name: /Особые категории/ }));
    const orphan = screen.getByRole("cell", { name: "Сироты" }).closest("tr") as HTMLElement;
    expect(within(orphan).getByText("Иванов И., Петров П.")).toBeInTheDocument();
    expect(screen.getByText(/У 3 студентов досье не заполнено/)).toBeInTheDocument();
  });

  it("можно открыть паспорт сразу по ссылке и выгрузить Excel группы", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<PassportPage />, { route: "/passport?group=1", role: "admin" });
    await screen.findByRole("heading", { name: /Социальный паспорт группы СА172/ });
    await user.click(screen.getByRole("button", { name: "Экспорт в Excel" }));
    expect(download).toHaveBeenCalledWith("/passport/export?group_id=1", "social_passport.xlsx");
  });

  it("паспорт группы выгружается в Word по бланку колледжа", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<PassportPage />, { route: "/passport?group=1", role: "curator" });
    await screen.findByRole("heading", { name: /Социальный паспорт группы СА172/ });
    await user.click(screen.getByRole("button", { name: /Экспорт в Word/ }));
    expect(download).toHaveBeenCalledWith("/passport/group/1/docx", "Социальный_паспорт_СА172.docx");
  });

  it("не показывает чужой паспорт, пока грузится нужный", async () => {
    mockApi({ group: groupPassport({ group_id: 99, group_code: "ЧУЖАЯ" }) });
    renderPage(<PassportPage />, { route: "/passport?group=1", role: "admin" });
    await waitFor(() => expect(get).toHaveBeenCalledWith("/passport/group/1"));
    expect(screen.queryByRole("heading", { name: /ЧУЖАЯ/ })).not.toBeInTheDocument();
    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  it("запрет доступа к группе показывается текстом", async () => {
    get.mockRejectedValue(new ApiError(403, "Нет доступа к паспорту этой группы"));
    renderPage(<PassportPage />, { route: "/passport?group=5", role: "curator" });
    expect(await screen.findByText("Нет доступа к паспорту этой группы")).toBeInTheDocument();
  });

  it("без ключа шифрования категории в паспорте группы — прочерки с пояснением", async () => {
    mockApi({ group: groupPassport({ special_available: false, categories: [{ key: "orphan", title: "Сироты", count: null, names: [] }] }) });
    renderPage(<PassportPage />, { route: "/passport?group=1", role: "admin" });
    await userEvent.setup().click(await screen.findByRole("tab", { name: /Особые категории/ }));
    expect(await screen.findByText(/DOSSIER_ENCRYPTION_KEY/)).toBeInTheDocument();
    const r = screen.getByRole("cell", { name: "Сироты" }).closest("tr") as HTMLElement;
    expect(within(r).getAllByText("—")).toHaveLength(2); // число и «кто»
  });

  it("«К сводке» возвращает к таблице групп", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<PassportPage />, { route: "/passport?group=1", role: "admin" });
    await user.click(await screen.findByRole("button", { name: /К сводке по группам/ }));
    expect(await screen.findByRole("cell", { name: "ИИ112" })).toBeInTheDocument();
  });
});

describe("PassportPage — поиск, фильтры и сортировка", () => {
  const rows = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);

  function many() {
    return summary({
      rows: [
        { ...row(1, "СА172", { orphan: 2, ovz: 0 }), course: 1, no_guardians: 0 },
        { ...row(2, "ИИ212", { orphan: 0, ovz: 3 }), course: 2, students_total: 30, no_guardians: 4 },
        { ...row(3, "ИС312", { orphan: null, ovz: null }), course: 3, students_total: 10, dossier_empty: 0 },
      ],
    });
  }

  it("поиск по названию группы сужает список и пересчитывает итог по видимым", async () => {
    const user = userEvent.setup();
    mockApi({ summary: many() });
    renderPage(<PassportPage />, { role: "admin" });
    await screen.findByRole("cell", { name: "СА172" });
    await user.type(screen.getByLabelText("Поиск по группе или отделению"), "ИИ");
    expect(rows()).toEqual(["ИИ212"]);
    expect(screen.getByRole("status")).toHaveTextContent("Показано 1 из 3");
    await user.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
    expect(rows()).toEqual(["СА172", "ИИ212", "ИС312", "Итого"]);
  });

  it("фильтры по курсу, «что показать» и особой категории", async () => {
    const user = userEvent.setup();
    mockApi({ summary: many() });
    renderPage(<PassportPage />, { role: "admin" });
    await screen.findByRole("cell", { name: "СА172" });
    await user.selectOptions(screen.getByLabelText("Курс"), "2");
    expect(rows()).toEqual(["ИИ212"]);
    await user.selectOptions(screen.getByLabelText("Курс"), "all");
    await user.selectOptions(screen.getByLabelText("Что показать"), "no_guardians");
    expect(rows().filter((c) => c !== "Итого")).toEqual(["ИИ212", "ИС312"]);
    await user.selectOptions(screen.getByLabelText("Что показать"), "all");
    await user.selectOptions(screen.getByLabelText("Особая категория"), "orphan");
    expect(rows()).toEqual(["СА172"]);
  });

  it("сортировка по клику на заголовок", async () => {
    const user = userEvent.setup();
    mockApi({ summary: many() });
    renderPage(<PassportPage />, { role: "admin" });
    await screen.findByRole("cell", { name: "СА172" });
    await user.click(screen.getByRole("button", { name: /Студентов/ }));
    expect(rows().slice(0, 3)).toEqual(["ИС312", "СА172", "ИИ212"]);
    await user.click(screen.getByRole("button", { name: /Студентов/ }));
    expect(rows().slice(0, 3)).toEqual(["ИИ212", "СА172", "ИС312"]);
  });

  it("если ничего не подошло — об этом написано", async () => {
    const user = userEvent.setup();
    mockApi({ summary: many() });
    renderPage(<PassportPage />, { role: "admin" });
    await screen.findByRole("cell", { name: "СА172" });
    await user.type(screen.getByLabelText("Поиск по группе или отделению"), "ЯЯЯ");
    expect(screen.getByText(/ни одна группа не подошла/)).toBeInTheDocument();
  });

  it("в паспорте группы: поиск по студенту и «только с отметками»", async () => {
    const user = userEvent.setup();
    mockApi();
    renderPage(<PassportPage />, { role: "admin", route: "/passport?group=1" });
    await user.click(await screen.findByRole("tab", { name: /Особые категории/ }));
    expect(screen.getByRole("cell", { name: "ОВЗ" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Только с отметками" }));
    expect(screen.queryByRole("cell", { name: "ОВЗ" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Все категории" }));
    await user.type(screen.getByLabelText("Поиск по категории или студенту"), "Петров");
    expect(screen.getByRole("cell", { name: "Сироты" })).toBeInTheDocument();
    expect(screen.queryByRole("cell", { name: "ОВЗ" })).not.toBeInTheDocument();
  });
});
