import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import type { CuratorFolder } from "../api/types";
import { renderPage } from "../test/utils";
import CuratorFolderPanel from "./CuratorFolderPanel";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const download = vi.mocked(downloadFile);

const FOLDER: CuratorFolder = {
  group_id: 7,
  group_code: "СА172",
  school_year: "2026-2027",
  items: [
    {
      code: "5.1.1", title: "План воспитательной работы", state: "filled", note: "Мероприятий в плане: 3",
      downloads: [
        { label: "План группы", path: "/events/groups/7/plan.docx?kind=group", filename: "План_группы.docx" },
        { label: "План куратора", path: "/events/groups/7/plan.docx?kind=curator", filename: "План_куратора.docx" },
      ],
      open_tab: "plan", open_part: null, can_add: null,
    },
    {
      code: "5.1.7", title: "Протоколы родительских собраний", state: "blank", note: "Собраний пока нет", downloads: [],
      open_tab: "plan", open_part: "meetings", can_add: null,
    },
    {
      code: "5.1.12", title: "Отчёты о посещаемости по месяцам", state: "filled", note: "Табель",
      downloads: ["Сентябрь", "Октябрь", "Ноябрь", "Декабрь", "Январь", "Февраль"].map((m, i) => ({
        label: `${m} 2026`, path: `/export/pdf/7?m=${i}`, filename: `Табель_${i}.pdf`,
      })),
      open_tab: null, open_part: null, can_add: null,
    },
    { code: "5.1.2", title: "Циклограмма куратора", state: "outside", note: "Платформа циклограмму не ведёт", downloads: [], open_tab: null, open_part: null, can_add: null },
    { code: "5.1.13", title: "Отчёт куратора за семестр", state: "off", note: "Раздел платформы отключён", downloads: [], open_tab: "report", open_part: null, can_add: null },
  ],
};

function open() {
  return renderPage(<CuratorFolderPanel groupId={7} />, { role: "curator", route: "/cabinet/groups/7?tab=folder", path: "/cabinet/groups/:groupId" });
}

beforeEach(() => {
  get.mockReset();
  download.mockReset();
  download.mockResolvedValue(undefined);
  get.mockResolvedValue(FOLDER);
});

describe("CuratorFolderPanel — папка куратора", () => {
  it("показывает документы со статусом и подсказкой", async () => {
    open();
    expect(await screen.findByRole("heading", { name: "План воспитательной работы" })).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/folder/groups/7");
    expect(screen.getByText("Мероприятий в плане: 3")).toBeInTheDocument();
    expect(screen.getByText("Пустой бланк")).toBeInTheDocument();
    expect(screen.getByText("Вне платформы")).toBeInTheDocument();
    expect(screen.getByText("Раздел отключён")).toBeInTheDocument();
  });

  it("кнопка выгрузки скачивает файл по пути сервера", async () => {
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "План куратора" }));
    expect(download).toHaveBeenCalledWith("/events/groups/7/plan.docx?kind=curator", "План_куратора.docx");
  });

  it("длинный список выгрузок прячет лишние кнопки под «Показать все»", async () => {
    open();
    await screen.findByRole("heading", { name: "Отчёты о посещаемости по месяцам" });
    expect(screen.getByText("Показать все (6)")).toBeInTheDocument();
    const item = screen.getByRole("heading", { name: "Отчёты о посещаемости по месяцам" }).closest("li") as HTMLElement;
    expect(within(item).getAllByRole("button", { hidden: true })).toHaveLength(6);
  });

  it("ссылка «Открыть раздел» ведёт во вкладку, а у отключённого раздела её нет", async () => {
    open();
    await screen.findByRole("heading", { name: "Протоколы родительских собраний" });
    const links = screen.getAllByRole("link", { name: "Открыть раздел" });
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/cabinet/groups/7?tab=plan", "/cabinet/groups/7?tab=plan&part=meetings"]);
  });

  it("отказ сервера при скачивании показывает причину", async () => {
    const user = userEvent.setup();
    download.mockRejectedValue(new ApiError(409, "Паспорт недоступен: на сервере не задан ключ шифрования досье"));
    open();
    await user.click(await screen.findByRole("button", { name: "План группы" }));
    expect(await screen.findByText(/не задан ключ шифрования/)).toBeInTheDocument();
  });

  it("ошибка загрузки списка показывает сообщение", async () => {
    get.mockRejectedValue(new ApiError(403, "Это не ваша группа"));
    open();
    expect(await screen.findByText("Это не ваша группа")).toBeInTheDocument();
  });
});

describe("CuratorFolderPanel — протоколы общих собраний (5.1.10)", () => {
  const ASSEMBLIES = {
    group_id: 7, school_year: "2026-2027", students_count: 25,
    assemblies: [{ id: 3, study_group_id: 7, school_year: "2026-2027", number: 1, assembly_date: "2026-10-05", chair: null, secretary: null, present_count: 20, agenda: null, listened: null, resolved: null }],
  };

  beforeEach(() => {
    post.mockReset();
    post.mockResolvedValue({});
    get.mockImplementation(async (path: string) => {
      if (path.startsWith("/assemblies/groups/7")) return ASSEMBLIES;
      return {
        ...FOLDER,
        items: [{ code: "5.1.10", title: "Протоколы общих собраний группы", state: "filled", note: "Собраний за год: 1", downloads: [], open_tab: null, open_part: null, can_add: "assembly" }],
      };
    });
  });

  it("показывает собрания года и скачивает протокол", async () => {
    const user = userEvent.setup();
    open();
    expect(await screen.findByText("№ 1 от 05.10.2026")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Скачать" }));
    expect(download).toHaveBeenCalledWith("/assemblies/3/protocol.docx", "Протокол_общего_собрания_1.docx");
  });

  it("«Добавить протокол собрания» отправляет введённые данные и обновляет папку", async () => {
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Добавить протокол собрания" }));
    const dialog = await screen.findByRole("dialog", { name: "Общее собрание группы" });
    await user.type(within(dialog).getByLabelText("Председатель"), "Старостин Пётр");
    await user.type(within(dialog).getByLabelText("Студентов присутствовало (число)"), "22");
    await user.click(within(dialog).getByRole("button", { name: "Сохранить" }));
    expect(post).toHaveBeenCalledWith("/assemblies/groups/7", expect.objectContaining({ chair: "Старостин Пётр", present_count: 22, school_year: "2026-2027" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
