import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import { renderPage } from "../../test/utils";
import DepartmentsTab from "./DepartmentsTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const post = vi.mocked(api.post);
const patch = vi.mocked(api.patch);

const DEPARTMENTS = [
  { id: 1, name: "Диджитал", is_active: true },
  { id: 2, name: "Моссовет", is_active: false },
];

beforeEach(() => {
  for (const fn of [get, post, patch]) fn.mockReset();
  get.mockResolvedValue(DEPARTMENTS);
});

const row = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;

describe("DepartmentsTab", () => {
  it("показывает отделения и признак активности", async () => {
    renderPage(<DepartmentsTab canEdit />);
    expect(await screen.findByText("Диджитал")).toBeInTheDocument();
    expect(within(row("Диджитал")).getByText("да")).toBeInTheDocument();
    expect(within(row("Моссовет")).getByText("нет")).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith("/admin/departments");
  });

  it("создаёт отделение, очищает поле и перезагружает список", async () => {
    const user = userEvent.setup();
    post.mockResolvedValue({});
    renderPage(<DepartmentsTab canEdit />);
    await screen.findByText("Диджитал");
    await user.type(screen.getByPlaceholderText("Новое отделение"), "Кибер");
    await user.click(screen.getByRole("button", { name: "Добавить" }));
    expect(post).toHaveBeenCalledWith("/admin/departments", { name: "Кибер" });
    await waitFor(() => expect(screen.getByPlaceholderText("Новое отделение")).toHaveValue(""));
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("повтор названия — сообщение сервера, введённое остаётся", async () => {
    const user = userEvent.setup();
    post.mockRejectedValue(new ApiError(409, "Отделение с таким названием уже существует"));
    renderPage(<DepartmentsTab canEdit />);
    await screen.findByText("Диджитал");
    await user.type(screen.getByPlaceholderText("Новое отделение"), "Диджитал");
    await user.click(screen.getByRole("button", { name: "Добавить" }));
    expect(await screen.findByText("Отделение с таким названием уже существует")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Новое отделение")).toHaveValue("Диджитал");
  });

  it("переименование: правка на месте, «Отмена» ничего не отправляет", async () => {
    const user = userEvent.setup();
    patch.mockResolvedValue({});
    renderPage(<DepartmentsTab canEdit />);
    await screen.findByText("Диджитал");
    await user.click(within(row("Диджитал")).getByRole("button", { name: "Переименовать" }));
    const input = screen.getByDisplayValue("Диджитал");
    await user.clear(input);
    await user.type(input, "Digital");
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(patch).not.toHaveBeenCalled();

    await user.click(within(row("Диджитал")).getByRole("button", { name: "Переименовать" }));
    const again = screen.getByDisplayValue("Диджитал");
    await user.clear(again);
    await user.type(again, "Digital");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(patch).toHaveBeenCalledWith("/admin/departments/1", { name: "Digital" });
  });

  it("архивация спрашивает подтверждение, возврат из архива — нет", async () => {
    const user = userEvent.setup();
    patch.mockResolvedValue({});
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    renderPage(<DepartmentsTab canEdit />);
    await screen.findByText("Диджитал");
    await user.click(within(row("Диджитал")).getByRole("button", { name: "В архив" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("«Диджитал»"));
    expect(patch).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    await user.click(within(row("Диджитал")).getByRole("button", { name: "В архив" }));
    expect(patch).toHaveBeenCalledWith("/admin/departments/1", { is_active: false });

    confirm.mockClear();
    await user.click(within(row("Моссовет")).getByRole("button", { name: "Вернуть из архива" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(patch).toHaveBeenLastCalledWith("/admin/departments/2", { is_active: true });
  });

  it("без права правки — только таблица", async () => {
    renderPage(<DepartmentsTab canEdit={false} />, { role: "edu_department" });
    await screen.findByText("Диджитал");
    expect(screen.queryByPlaceholderText("Новое отделение")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Переименовать" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Управление" })).not.toBeInTheDocument();
  });

  it("ошибка загрузки показывается", async () => {
    get.mockRejectedValue(new ApiError(403, "Недостаточно прав"));
    renderPage(<DepartmentsTab canEdit />);
    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
  });
});
