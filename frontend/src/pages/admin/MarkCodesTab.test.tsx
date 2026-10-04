import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../../api/client";
import { renderPage } from "../../test/utils";
import MarkCodesTab from "./MarkCodesTab";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const patch = vi.mocked(api.patch);

const CODES = [
  { id: 1, code: "н", name: "Неуважительная причина", counts_as_present: false, is_excused: false, requires_document: false, is_active: true },
  { id: 2, code: "б", name: "Больничный лист", counts_as_present: false, is_excused: true, requires_document: true, is_active: true },
];

beforeEach(() => {
  get.mockReset();
  patch.mockReset();
  get.mockResolvedValue(CODES);
});

const row = (name: string) => screen.getByText(name).closest("tr") as HTMLElement;
// порядок столбцов: считается присутствием, уважительная, требует документа, активен
const flag = (name: string, index: number) => within(row(name)).getAllByRole("checkbox")[index];

describe("MarkCodesTab", () => {
  it("показывает коды и флаги", async () => {
    renderPage(<MarkCodesTab canEdit />);
    await screen.findByText("Больничный лист");
    expect(flag("Больничный лист", 0)).not.toBeChecked();
    expect(flag("Больничный лист", 1)).toBeChecked();
    expect(flag("Больничный лист", 2)).toBeChecked();
    expect(flag("Неуважительная причина", 1)).not.toBeChecked();
    expect(screen.getByText(/пересчитывают всю отчётность/)).toBeInTheDocument();
  });

  it("смена флага отправляется только после подтверждения с понятным вопросом", async () => {
    const user = userEvent.setup();
    patch.mockResolvedValue({});
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    renderPage(<MarkCodesTab canEdit />);
    await screen.findByText("Неуважительная причина");

    await user.click(flag("Неуважительная причина", 1));
    expect(confirm).toHaveBeenCalledWith(expect.stringMatching(/«уважительная» у кода «н» на «да».*задним числом/));
    expect(patch).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    await user.click(flag("Неуважительная причина", 1));
    expect(patch).toHaveBeenCalledWith("/admin/mark-codes/1", { is_excused: true });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2)); // таблица перезагружена
  });

  it("снятие флага: в вопросе значение «нет»", async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage(<MarkCodesTab canEdit />);
    await screen.findByText("Больничный лист");
    await user.click(flag("Больничный лист", 2));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("«требует документа» у кода «б» на «нет»"));
  });

  it("ошибка сохранения показывается", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    patch.mockRejectedValue(new ApiError(403, "Недостаточно прав"));
    renderPage(<MarkCodesTab canEdit />);
    await screen.findByText("Неуважительная причина");
    await user.click(flag("Неуважительная причина", 0));
    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
  });

  it("без права правки все флаги заблокированы", async () => {
    renderPage(<MarkCodesTab canEdit={false} />, { role: "dept_head" });
    await screen.findByText("Больничный лист");
    for (const cb of screen.getAllByRole("checkbox")) expect(cb).toBeDisabled();
  });
});
