import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { AttendanceSummary, SummaryGroupDay, SummaryLine } from "../api/types";
import { defaultSummaryFilters } from "../utils/summaryFilters";
import type { SummaryFilters } from "../utils/summaryFilters";
import AttendanceSummaryView from "./AttendanceSummary";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);

const line = (over: Partial<SummaryLine>): SummaryLine => ({
  date: "2026-10-01", department: "Диджитал", slice_name: "Всего", groups: 4, groups_submitted: 4, headcount: 100,
  counted: 100, present: 95, absent: 5, percent: 95, by_code: { н: 3, б: 2 }, ...over,
});

const DATA: AttendanceSummary = {
  codes: [
    { code: "о", name: "Опоздание", counts_as_present: true },
    { code: "н", name: "Неуважительная причина", counts_as_present: false },
    { code: "б", name: "Больничный лист", counts_as_present: false },
  ],
  daily: [
    line({ date: "2026-10-01", percent: 95 }),
    line({ date: "2026-10-01", slice_name: "К 1 паре", counted: 60, headcount: 60, present: 50, absent: 10, percent: 83.3, by_code: { н: 8, б: 2 } }),
    line({ date: "2026-10-02", percent: 88, groups_submitted: 3, present: 88, absent: 12, by_code: { н: 12 } }),
    line({ date: "2026-10-03", counted: 0, headcount: 0, present: 0, absent: 0, percent: null, groups_submitted: 0, by_code: {} }),
    line({ date: "2026-10-04", percent: 99, groups_submitted: 3, by_code: {} }),
  ],
  period: [
    line({ date: null, percent: 91.2, groups: 12, groups_submitted: 10, headcount: 400, counted: 380, present: 346, absent: 34 }),
    line({ date: null, slice_name: "К 1 паре", percent: 85, headcount: 200, counted: 190, present: 161, absent: 29 }),
  ],
  group_days: [
    { date: "2026-10-01", department: "Диджитал", group_id: 1, group_code: "СА172", course: 1, headcount: 25, is_submitted: true, present: 24, absent: 1, percent: 96, first_period: 2, by_code: { н: 1 } },
    { date: "2026-10-01", department: "Диджитал", group_id: 2, group_code: "ИИ212", course: 2, headcount: 20, is_submitted: false, present: null, absent: null, percent: null, first_period: null, by_code: {} },
    { date: "2026-10-02", department: "Диджитал", group_id: 1, group_code: "СА172", course: 1, headcount: 25, is_submitted: true, present: 20, absent: 5, percent: 80, first_period: null, by_code: { б: 5 } },
  ] as SummaryGroupDay[],
};

const GROUPS = [
  { id: 1, code: "СА172", course: 1, department_id: 1, study_form: null, is_active: true, curator_name: null, curator_assignment_id: null, deputy_name: null, deputy_assignment_id: null },
  { id: 2, code: "ИИ212", course: 2, department_id: 1, study_form: null, is_active: true, curator_name: null, curator_assignment_id: null, deputy_name: null, deputy_assignment_id: null },
  { id: 3, code: "ИТ301", course: 3, department_id: 2, study_form: null, is_active: true, curator_name: null, curator_assignment_id: null, deputy_name: null, deputy_assignment_id: null },
  { id: 4, code: "АРХ-1", course: 1, department_id: 1, study_form: null, is_active: false, curator_name: null, curator_assignment_id: null, deputy_name: null, deputy_assignment_id: null },
];
const DEPARTMENTS = [{ id: 1, name: "Диджитал", is_active: true }, { id: 2, name: "Моссовет", is_active: true }];

let current: SummaryFilters;

function Harness({ canFilterDepartment = true, initial }: { canFilterDepartment?: boolean; initial?: Partial<SummaryFilters> }) {
  const [filters, setFilters] = useState<SummaryFilters>({ ...defaultSummaryFilters(), ...initial });
  useEffect(() => {
    current = filters; // тесты читают итоговые фильтры
  }, [filters]);
  return (
    <AttendanceSummaryView
      filters={filters}
      onChange={setFilters}
      canFilterDepartment={canFilterDepartment}
      departments={DEPARTMENTS}
      groups={GROUPS}
    />
  );
}

/** Таблица отрисована (в ней несколько строк с отделением, поэтому — findAll). */
const ready = () => screen.findAllByText("Диджитал", { selector: "td" });
const summaryCalls = () => get.mock.calls.map((c) => String(c[0])).filter((p) => p.startsWith("/dashboards/summary"));
const headers = () => screen.getAllByRole("columnheader").map((h) => h.textContent?.replace(/ [▲▼]$/, ""));
const bodyRows = () => within(screen.getAllByRole("rowgroup")[1]).getAllByRole("row");

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue(DATA);
});

describe("AttendanceSummaryView — запрос", () => {
  it("период, пара и отбор уходят на сервер; для «по группам» добавляется include_group_days", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ departmentId: 1, course: 2, groupId: 2, pair: 3 }} />);
    await ready();
    const f = defaultSummaryFilters();
    expect(summaryCalls()[0]).toBe(`/dashboards/summary?date_from=${f.dateFrom}&date_to=${f.dateTo}&pair=3&department_id=1&course=2&study_group_id=2`);
    await user.click(screen.getByRole("button", { name: "По группам и дням" }));
    await waitFor(() => expect(summaryCalls().at(-1)).toMatch(/&include_group_days=true$/));
  });

  it("если начало позже конца — сообщение, запрос не уходит", async () => {
    render(<Harness initial={{ dateFrom: "2026-10-10", dateTo: "2026-10-01" }} />);
    expect(await screen.findByText("Дата начала позже даты окончания")).toBeInTheDocument();
    expect(summaryCalls()).toHaveLength(0);
  });

  it("ошибка сервера показывается; пока грузится — «Загрузка…»", async () => {
    let release: (v: unknown) => void = () => undefined;
    get.mockReturnValueOnce(new Promise((resolve) => { release = resolve; }));
    const { unmount } = render(<Harness />);
    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
    release(DATA);
    await ready();
    unmount();

    get.mockRejectedValue(new ApiError(403, "Недостаточно прав"));
    render(<Harness />);
    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
  });
});

describe("AttendanceSummaryView — период и область", () => {
  it("быстрый период ставит даты и подсвечивается; ручная правка даты снимает подсветку", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("button", { name: "Вчера" }));
    expect(current.preset).toBe("yesterday");
    expect(current.dateFrom).toBe(current.dateTo);
    expect(screen.getByRole("button", { name: "Вчера" })).toHaveClass("active");
    fireEvent.change(document.querySelectorAll('input[type="date"]')[0], { target: { value: "2026-09-01" } });
    expect(current.preset).toBeNull();
    expect(screen.getByRole("button", { name: "Вчера" })).not.toHaveClass("active");
  });

  it("выбор отделения только у тех, кому он положен", async () => {
    const { unmount } = render(<Harness canFilterDepartment />);
    await ready();
    expect(screen.getByTitle("Отделение")).toBeInTheDocument();
    unmount();
    render(<Harness canFilterDepartment={false} />);
    await ready();
    expect(screen.queryByTitle("Отделение")).not.toBeInTheDocument();
  });

  it("список групп учитывает курс и отделение; архивные группы не предлагаются", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    const names = () => {
      const list = screen.queryByRole("listbox");
      return list ? within(list).getAllByRole("option").map((o) => o.textContent) : [];
    };
    const open = async () => {
      if (!screen.queryByRole("listbox")) await user.click(screen.getByRole("combobox", { name: "Группа" }));
    };
    await open();
    expect(names()).toEqual(["Все группы", "СА172", "ИИ212", "ИТ301"]);
    await user.selectOptions(screen.getByTitle("Курс"), "1");
    await open();
    expect(names()).toEqual(["Все группы", "СА172"]);
    await user.selectOptions(screen.getByTitle("Курс"), "all");
    await user.selectOptions(screen.getByTitle("Отделение"), "2");
    await open();
    expect(names()).toEqual(["Все группы", "ИТ301"]);
  });

  it("смена курса сбрасывает группу, которая в него не входит; подходящую оставляет", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ groupId: 2 }} />);
    await ready();
    await user.selectOptions(screen.getByTitle("Курс"), "2");
    expect(current.groupId).toBe(2);
    await user.selectOptions(screen.getByTitle("Курс"), "1");
    expect(current.groupId).toBe("all");
  });
});

describe("AttendanceSummaryView — отбор строк на экране", () => {
  it("«По дням»: по умолчанию строки без данных скрыты, срез «всего и к паре»", async () => {
    render(<Harness />);
    await ready();
    expect(bodyRows()).toHaveLength(4); // 01.10 (всего + к паре), 02.10, 04.10; 03.10 без данных скрыт
    expect(screen.queryByText("03.10.2026")).not.toBeInTheDocument();
  });

  it("«Скрыть строки без данных» можно выключить", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("button", { name: /Дополнительно/ }));
    await user.click(screen.getByLabelText(/Скрыть строки без данных/));
    expect(screen.getByText("03.10.2026")).toBeInTheDocument();
  });

  it("срез «Только Всего» и «Только К 1 паре»", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("button", { name: "Всего" }));
    expect(screen.queryByText("К 1 паре", { selector: "b" })).not.toBeInTheDocument();
    expect(screen.queryByTitle("Какая пара считается первой для среза")).not.toBeInTheDocument(); // при «Всего» выбор пары не нужен
    await user.click(screen.getByRole("button", { name: "К 1 паре" }));
    expect(screen.getAllByText("К 1 паре", { selector: "b" })).toHaveLength(1);
    expect(screen.queryByText("Всего", { selector: "b" })).not.toBeInTheDocument();
  });

  it("«Только проблемные»: ниже порога или есть несданные группы; порог меняется", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("button", { name: /Дополнительно/ }));
    await user.click(screen.getByLabelText(/Только проблемные/));
    // 01.10 всего: 95% и все сдали — не проблема; 01.10 «к паре»: 83% — проблема; 02.10: 88%, сдали 3 из 4 — проблема;
    // 04.10: 99%, но сдали 3 из 4 — проблема; 03.10: нет данных, но 0 из 4 не сдали — проблема.
    expect(screen.getByText("01.10.2026")).toBeInTheDocument();
    expect(bodyRows()).toHaveLength(4);
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "99" } });
    expect(bodyRows().length).toBeGreaterThanOrEqual(4);
    // «Скрыть строки без данных» при этом отключён: проблемные показываются всегда
    expect(screen.getByLabelText(/Скрыть строки без данных/)).toBeDisabled();
  });

  it("порог ограничен 1–100", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("button", { name: /Дополнительно/ }));
    const input = screen.getByRole("spinbutton");
    fireEvent.change(input, { target: { value: "500" } });
    expect(current.threshold).toBe(100);
    fireEvent.change(input, { target: { value: "0" } });
    expect(current.threshold).toBe(1);
  });
});

describe("AttendanceSummaryView — столбцы кодов и сортировка", () => {
  it("кодовые столбцы переключаются галочками; «Только пропуски» убирает коды-присутствия; «Все» возвращает", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("button", { name: /Дополнительно/ }));
    expect(headers().slice(-3)).toEqual(["О", "Н", "Б"]);
    await user.click(screen.getByLabelText(/Опоздание/));
    expect(headers().slice(-2)).toEqual(["Н", "Б"]);
    await user.click(screen.getByRole("button", { name: "Все" }));
    expect(headers().slice(-3)).toEqual(["О", "Н", "Б"]);
    await user.click(screen.getByRole("button", { name: "Только пропуски" }));
    expect(current.hiddenCodes).toEqual(["о"]);
    expect(headers().slice(-2)).toEqual(["Н", "Б"]);
    expect(screen.getByText(/Столбцы кодов \(2\/3\)/)).toBeInTheDocument();
  });

  it("сортировка по клику: по возрастанию → по убыванию → выключена; пустые всегда внизу", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ hideEmpty: false, slice: "all" }} />);
    await ready();
    const percentColumn = () => bodyRows().map((r) => within(r).getAllByRole("cell")[8].textContent);
    expect(percentColumn()).toEqual(["95%", "88%", "—", "99%"]);
    const th = screen.getByRole("columnheader", { name: "%" });
    await user.click(th);
    expect(th).toHaveAttribute("aria-sort", "ascending");
    expect(percentColumn()).toEqual(["88%", "95%", "99%", "—"]);
    await user.click(th);
    expect(th).toHaveAttribute("aria-sort", "descending");
    expect(percentColumn()).toEqual(["99%", "95%", "88%", "—"]); // пустое по-прежнему внизу
    await user.click(th);
    expect(th).toHaveAttribute("aria-sort", "none");
    expect(percentColumn()).toEqual(["95%", "88%", "—", "99%"]);
  });

  it("смена вида сбрасывает сортировку", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("columnheader", { name: "%" }));
    await user.click(screen.getByRole("button", { name: "За период" }));
    expect(screen.getByRole("columnheader", { name: "%" })).toHaveAttribute("aria-sort", "none");
  });
});

describe("AttendanceSummaryView — «За период» и «По группам и дням»", () => {
  it("за период: строки без даты, подпись про студенто-дни", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    await user.click(screen.getByRole("button", { name: "За период" }));
    expect(screen.getByText("91.2%")).toBeInTheDocument();
    expect(screen.getByText(/в студенто-днях/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Групп-дней сдано" })).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument(); // групп-дней сдано (без «из N»)
  });

  it("по группам: несданный день с прочерками, пара «не указана», поиск по коду", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ view: "groups", hideEmpty: false }} />);
    const table = await screen.findByRole("table");
    const cell = (code: string, index = 0) => within(table).getAllByText(code, { selector: "td" })[index].closest("tr") as HTMLElement;
    expect(cell("ИИ212")).toHaveClass("not-submitted-row");
    expect(within(cell("ИИ212")).getAllByText("—").length).toBeGreaterThanOrEqual(5);
    expect(within(cell("СА172", 0)).getByText("2")).toBeInTheDocument(); // пара, указанная куратором
    expect(within(cell("СА172", 1)).getByText("не указана")).toBeInTheDocument();

    // hideEmpty: false отличается от умолчания, поэтому панель «Дополнительно» уже открыта.
    const search = screen.getByPlaceholderText("Поиск по коду группы");
    await user.type(search, "ии");
    expect(within(table).queryByText("СА172", { selector: "td" })).not.toBeInTheDocument();
    expect(within(table).getByText("ИИ212", { selector: "td" })).toBeInTheDocument();
    await user.clear(search);
    await user.type(search, "нет такой");
    expect(screen.getByText("Нет строк под выбранные фильтры.")).toBeInTheDocument();
  });

  it("по группам по умолчанию несданные дни скрыты вместе с «Скрыть строки без данных»", async () => {
    render(<Harness initial={{ view: "groups" }} />);
    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("СА172", { selector: "td" })).toHaveLength(2);
    expect(within(table).queryByText("ИИ212", { selector: "td" })).not.toBeInTheDocument();
  });
});

describe("AttendanceSummaryView — панель фильтров", () => {
  it("группа выбирается вводом с клавиатуры: «GD» оставляет группы с ГД, Enter берёт первую", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    const box = screen.getByRole("combobox", { name: "Группа" });
    await user.click(box);
    await user.type(box, "ии");
    expect(within(screen.getByRole("listbox")).getAllByRole("option").map((o) => o.textContent)).toEqual(["ИИ212"]);
    await user.keyboard("{Enter}");
    expect(current.groupId).toBe(2);
  });

  it("блоки подписаны: период, кого учитывать, что показать; доп. фильтры скрыты и показывают счётчик", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    for (const label of ["Период", "Кого учитывать", "Что показать"]) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText(/Только на экране/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Дополнительно/ })).toHaveAttribute("aria-expanded", "false");

    await user.click(screen.getByRole("button", { name: /Дополнительно/ }));
    expect(screen.getByText(/Только на экране/)).toBeInTheDocument();
    await user.click(screen.getByLabelText(/Только проблемные/));
    expect(screen.getByRole("button", { name: /Дополнительно \(1\)/ })).toBeInTheDocument();
  });

  it("если доп. фильтр уже включён (из ссылки), панель открыта сразу", async () => {
    render(<Harness initial={{ onlyProblems: true }} />);
    await ready();
    expect(screen.getByRole("button", { name: /Дополнительно \(1\)/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("выбор пары показывается только когда срез «К N паре» участвует", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    expect(screen.getByTitle("Какая пара считается первой для среза")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Всего" }));
    expect(screen.queryByTitle("Какая пара считается первой для среза")).not.toBeInTheDocument();
  });
});

describe("AttendanceSummaryView — сброс и ссылка", () => {
  it("«Сбросить» недоступна на умолчаниях, возвращает их, когда фильтры изменены", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await ready();
    const reset = screen.getByRole("button", { name: "Сбросить" });
    expect(reset).toBeDisabled();
    await user.selectOptions(screen.getByTitle("Курс"), "2");
    expect(reset).toBeEnabled();
    await user.click(reset);
    expect(current).toEqual(defaultSummaryFilters());
  });

  it("«Копировать ссылку»: кладёт в буфер и подтверждает; без доступа к буферу — предлагает скопировать вручную", async () => {
    const user = userEvent.setup();
    render(<Harness initial={{ course: 2 }} />);
    await ready();
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    await user.click(screen.getByRole("button", { name: "Копировать ссылку" }));
    expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/dashboards\?.*course=2.*tab=summary|\/dashboards\?.*tab=summary.*course=2/));
    expect(await screen.findByRole("button", { name: "Ссылка скопирована" })).toBeInTheDocument();

    writeText.mockRejectedValue(new Error("нет доступа"));
    const prompt = vi.spyOn(window, "prompt").mockReturnValue(null);
    await user.click(await screen.findByRole("button", { name: "Ссылка скопирована" }));
    await waitFor(() => expect(prompt).toHaveBeenCalledWith("Скопируйте ссылку:", expect.stringContaining("/dashboards?")));
    vi.unstubAllGlobals();
  });
});
