import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { Dossier, DossierSpecial } from "../api/types";
import StudentDossier from "./StudentDossier";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const get = vi.mocked(api.get);
const put = vi.mocked(api.put);
const post = vi.mocked(api.post);
const del = vi.mocked(api.delete);

const SPECIAL: DossierSpecial = {
  is_orphan: false, under_guardianship: false, disability_group: null, has_ovz: false, large_family: false,
  low_income: false, pdn_kdn: false, internal_record: false, scholarship: null, health_note: null,
};

function dossier(over: Partial<Dossier> = {}): Dossier {
  return {
    student_id: 10,
    profile: {
      birth_date: null, funding: null, phone: null, email: null, messenger: null,
      registration_address: null, residence_address: null,
    },
    special: { ...SPECIAL },
    special_available: true,
    guardians: [],
    notes: [],
    can_edit: true,
    ...over,
  };
}

// В блоках представителей и заметок обе кнопки называются «Добавить» — ищем внутри своей формы.
const guardianForm = () => screen.getByPlaceholderText("ФИО").closest("form") as HTMLElement;
const noteForm = () => screen.getByPlaceholderText(/Что произошло/).closest("form") as HTMLElement;

function open(d: Dossier, isAdmin = false) {
  get.mockImplementation(async (path: string) => {
    if (path.endsWith("/dossier")) return d;
    if (path.endsWith("/access-log")) return [{ user_id: 1, user_name: "Петров П.", included_special: true, created_at: "2026-10-01T09:30:00" }];
    throw new Error(`неожиданный запрос ${path}`);
  });
  return render(<StudentDossier studentId={10} isAdmin={isAdmin} />);
}

beforeEach(() => {
  for (const fn of [get, put, post, del]) fn.mockReset();
});

describe("StudentDossier — профиль", () => {
  it("загружает досье студента", async () => {
    open(dossier({ profile: { ...dossier().profile, phone: "+7 900 000" } }));
    expect(await screen.findByLabelText("Телефон")).toHaveValue("+7 900 000");
    expect(get).toHaveBeenCalledWith("/students/10/dossier");
  });

  it("сохраняет контакты и особые данные одним запросом", async () => {
    const user = userEvent.setup();
    open(dossier());
    await user.type(await screen.findByLabelText("Телефон"), "+7 911");
    await user.selectOptions(screen.getByLabelText("Финансирование"), "budget");
    await user.click(screen.getByLabelText("Сирота"));
    await user.type(screen.getByLabelText("Группа инвалидности"), "3");
    await user.type(screen.getByLabelText("Здоровье: что важно знать куратору"), "астма");

    put.mockResolvedValue(dossier());
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(put).toHaveBeenCalledWith("/students/10/dossier/profile", expect.objectContaining({
      phone: "+7 911",
      funding: "budget",
      special: expect.objectContaining({ is_orphan: true, disability_group: "3", health_note: "астма" }),
    }));
    expect(await screen.findByText("Досье сохранено")).toBeInTheDocument();
  });

  it("очищенное поле уходит как null, а не пустая строка", async () => {
    const user = userEvent.setup();
    open(dossier({ profile: { ...dossier().profile, phone: "123" } }));
    await user.clear(await screen.findByLabelText("Телефон"));
    put.mockResolvedValue(dossier());
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(put.mock.calls[0][1]).toMatchObject({ phone: null });
  });

  it("без ключа шифрования особые поля скрыты, а контакты сохраняются без блока special", async () => {
    const user = userEvent.setup();
    open(dossier({ special: null, special_available: false }));
    expect(await screen.findByText(/не задан ключ шифрования/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Сирота")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Телефон"), "1");
    put.mockResolvedValue(dossier({ special: null, special_available: false }));
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(put.mock.calls[0][1]).toMatchObject({ phone: "1", special: null });
  });

  it("ошибка сохранения показывается, форма остаётся", async () => {
    const user = userEvent.setup();
    open(dossier());
    await user.type(await screen.findByLabelText("Телефон"), "1");
    put.mockRejectedValue(new ApiError(503, "Особые поля недоступны: ключ не подходит"));
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(await screen.findByText(/ключ не подходит/)).toBeInTheDocument();
    expect(screen.getByLabelText("Телефон")).toHaveValue("1");
  });

  it("ошибку загрузки (нет доступа) показывает вместо формы", async () => {
    get.mockRejectedValue(new ApiError(403, "Это не ваша группа"));
    render(<StudentDossier studentId={10} isAdmin={false} />);
    expect(await screen.findByText("Это не ваша группа")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сохранить досье" })).not.toBeInTheDocument();
  });
});

describe("StudentDossier — представители", () => {
  it("добавляет представителя и очищает форму", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Представители не указаны.");
    await user.type(screen.getByPlaceholderText("ФИО"), "Иванова А.");
    await user.type(screen.getByPlaceholderText(/Кем приходится/), "мать");
    await user.type(screen.getByPlaceholderText("Телефон"), "+7 900 111");
    await user.click(screen.getByLabelText(/Основной/));
    post.mockResolvedValue({});
    await user.click(within(guardianForm()).getByRole("button", { name: "Добавить" }));
    expect(post).toHaveBeenCalledWith("/students/10/dossier/guardians", {
      full_name: "Иванова А.", relation: "мать", phone: "+7 900 111", is_primary: true,
    });
    await waitFor(() => expect(screen.getByPlaceholderText("ФИО")).toHaveValue(""));
  });

  it("при ошибке сервера введённое не теряется", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Представители не указаны.");
    await user.type(screen.getByPlaceholderText("ФИО"), "Иванова А.");
    await user.type(screen.getByPlaceholderText(/Кем приходится/), "мать");
    post.mockRejectedValue(new ApiError(404, "Студент не найден"));
    await user.click(within(guardianForm()).getByRole("button", { name: "Добавить" }));
    expect(await screen.findByText("Студент не найден")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("ФИО")).toHaveValue("Иванова А.");
  });

  it("удаляет представителя только после подтверждения", async () => {
    const user = userEvent.setup();
    open(dossier({ guardians: [{ id: 4, full_name: "Иванов Б.", relation: "отец", phone: null, is_primary: true }] }));
    const row = (await screen.findByText("Иванов Б.")).closest("tr") as HTMLElement;
    expect(within(row).getByText("основной")).toBeInTheDocument();

    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false);
    await user.click(within(row).getByRole("button", { name: "Удалить" }));
    expect(del).not.toHaveBeenCalled();

    confirm.mockReturnValueOnce(true);
    del.mockResolvedValue(undefined);
    await user.click(within(row).getByRole("button", { name: "Удалить" }));
    expect(del).toHaveBeenCalledWith("/students/10/dossier/guardians/4");
  });
});

describe("StudentDossier — заметки и журнал", () => {
  const NOTE = { id: 9, kind: "call", text: "Звонок маме", author_id: 2, author_name: "Куратор К.", created_at: "2026-10-01T09:00:00", can_delete: true };

  it("добавляет заметку выбранного типа", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Заметок пока нет.");
    await user.selectOptions(within(noteForm()).getByRole("combobox"), "incident");
    await user.type(screen.getByPlaceholderText(/Что произошло/), "Конфликт на паре");
    post.mockResolvedValue({});
    await user.click(within(noteForm()).getByRole("button", { name: "Добавить" }));
    expect(post).toHaveBeenCalledWith("/students/10/dossier/notes", { kind: "incident", text: "Конфликт на паре" });
  });

  it("кнопка «Удалить» у заметки только там, где разрешено", async () => {
    open(dossier({ notes: [NOTE, { ...NOTE, id: 10, text: "Чужая заметка", can_delete: false }] }));
    const own = (await screen.findByText("Звонок маме")).closest("tr") as HTMLElement;
    const foreign = screen.getByText("Чужая заметка").closest("tr") as HTMLElement;
    expect(within(own).getByRole("button", { name: "Удалить" })).toBeInTheDocument();
    expect(within(foreign).queryByRole("button", { name: "Удалить" })).not.toBeInTheDocument();
    expect(within(own).getByText("Звонок")).toBeInTheDocument();
  });

  it("журнал просмотров только для администратора и грузится по клику", async () => {
    const user = userEvent.setup();
    const { unmount } = open(dossier(), false);
    await screen.findByLabelText("Телефон");
    expect(screen.queryByText("Журнал просмотров досье")).not.toBeInTheDocument();
    unmount();

    open(dossier(), true);
    await screen.findByText("Журнал просмотров досье");
    expect(get).not.toHaveBeenCalledWith("/students/10/dossier/access-log");
    await user.click(screen.getByRole("button", { name: "Показать" }));
    expect(await screen.findByText("Петров П.")).toBeInTheDocument();
    expect(screen.getByText("показаны")).toBeInTheDocument();
  });
});
