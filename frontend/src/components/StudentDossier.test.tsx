import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, downloadFile } from "../api/client";
import type { Dossier, DossierSpecial } from "../api/types";
import { todayIso } from "../utils/date";
import StudentDossier from "./StudentDossier";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return { ...actual, api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }, downloadFile: vi.fn() };
});

const get = vi.mocked(api.get);
const put = vi.mocked(api.put);
const post = vi.mocked(api.post);
const del = vi.mocked(api.delete);
const download = vi.mocked(downloadFile);

const SPECIAL: DossierSpecial = {
  is_orphan: false, under_guardianship: false, disability_group: null, has_ovz: false, large_family: false, incomplete_family: null, dysfunctional_family: false, parent_disabled: false,
  low_income: false, pdn_kdn: false, internal_record: false, scholarship: null, health_note: null,
};

function dossier(over: Partial<Dossier> = {}): Dossier {
  return {
    student_id: 10,
    profile: {
      birth_date: null, gender: null, funding: null, phone: null, email: null, messenger: null,
      registration_address: null, residence_address: null, additional_education: null, birth_place: null, previous_education: null, enrollment_order: null,
    },
    special: { ...SPECIAL },
    special_available: true,
    guardians: [],
    notes: [],
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
  it("загружает досье: заполненный раздел — готовой информацией, правка по кнопке «Редактировать»", async () => {
    const user = userEvent.setup();
    open(dossier({ profile: { ...dossier().profile, phone: "+7 900 000-00-00", email: "st@example.ru" } }));
    expect(await screen.findByRole("link", { name: "+7 900 000-00-00" })).toHaveAttribute("href", "tel:+79000000000");
    expect(screen.getByRole("link", { name: "st@example.ru" })).toHaveAttribute("href", "mailto:st@example.ru");
    expect(screen.queryByLabelText("Телефон")).not.toBeInTheDocument(); // не поле ввода
    expect(screen.getAllByText("не указано").length).toBeGreaterThan(0); // мессенджер пуст
    expect(get).toHaveBeenCalledWith("/students/10/dossier");

    await user.click(screen.getByRole("button", { name: "Редактировать: Контакты студента" }));
    expect(screen.getByLabelText("Телефон")).toHaveValue("+7 900 000-00-00");
    await user.click(screen.getByRole("button", { name: "Свернуть" }));
    expect(screen.queryByLabelText("Телефон")).not.toBeInTheDocument();
  });

  it("пустые разделы сразу открыты для ввода; «Сохранить досье» появляется, только когда есть что сохранять", async () => {
    const user = userEvent.setup();
    open(dossier());
    expect(await screen.findByLabelText("Телефон")).toHaveValue("");
    expect(screen.queryByRole("button", { name: /Редактировать/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сохранить досье" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Телефон"), "1");
    expect(screen.getByRole("button", { name: "Сохранить досье" })).toBeInTheDocument();
    expect(screen.getByText("Есть несохранённые изменения")).toBeInTheDocument();
  });

  it("сохраняет контакты и особые данные одним запросом", async () => {
    const user = userEvent.setup();
    open(dossier());
    await user.type(await screen.findByLabelText("Телефон"), "+7 911");
    await user.selectOptions(screen.getByLabelText("Финансирование"), "budget");
    await user.click(screen.getByLabelText("Сирота"));
    await user.type(screen.getByLabelText("Группа инвалидности"), "3");
    await user.type(screen.getByLabelText("Здоровье: что важно знать куратору"), "астма");
    await user.type(screen.getByLabelText(/Дополнительное образование/), "Футбол, шахматы");

    put.mockResolvedValue(dossier());
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(put).toHaveBeenCalledWith("/students/10/dossier/profile", expect.objectContaining({
      phone: "+7 911",
      funding: "budget",
      additional_education: "Футбол, шахматы",
      special: expect.objectContaining({ is_orphan: true, disability_group: "3", health_note: "астма" }),
    }));
    expect(await screen.findByText("Досье сохранено")).toBeInTheDocument();
  });

  it("признаки семьи для социального паспорта: неполная семья выбирается из списка, «нет» — null", async () => {
    const user = userEvent.setup();
    open(dossier());
    await user.selectOptions(await screen.findByLabelText("Неполная семья"), "divorce");
    await user.click(screen.getByLabelText("Неблагополучная семья"));
    await user.click(screen.getByLabelText("Родитель — инвалид"));
    put.mockResolvedValue(dossier());
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect((put.mock.calls[0][1] as { special: object }).special).toMatchObject({ incomplete_family: "divorce", dysfunctional_family: true, parent_disabled: true });

    await user.selectOptions(screen.getByLabelText("Неполная семья"), "");
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect((put.mock.calls[1][1] as { special: { incomplete_family: unknown } }).special.incomplete_family).toBeNull();
  });

  it("поля личной карточки сохраняются в досье, а кнопка открывает окно выбора полей карточки", async () => {
    const user = userEvent.setup();
    open(dossier());
    await user.type(await screen.findByLabelText("Место рождения"), "г. Тестоград");
    await user.type(screen.getByLabelText(/Приказ о зачислении/), "№ 5 от 25.08.2025");
    await user.type(screen.getByLabelText(/Образование до поступления/), "11 классов, 2025 год");
    put.mockResolvedValue(dossier());
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(put).toHaveBeenCalledWith("/students/10/dossier/profile", expect.objectContaining({
      birth_place: "г. Тестоград", enrollment_order: "№ 5 от 25.08.2025", previous_education: "11 классов, 2025 год",
    }));

    await user.click(await screen.findByRole("button", { name: "Личная карточка в Word" }));
    expect(await screen.findByRole("dialog", { name: "Личная карточка в Word" })).toBeInTheDocument();
  });

  it("пол: показывается сохранённый, выбирается из двух значений и уходит на сервер; «не указан» — null", async () => {
    const user = userEvent.setup();
    open(dossier({ profile: { ...dossier().profile, gender: "female" } }));
    expect(await screen.findByText("Женский")).toBeInTheDocument(); // сохранённый — готовой информацией
    await user.click(screen.getByRole("button", { name: "Редактировать: Основные сведения" }));
    const select = screen.getByLabelText("Пол");
    expect(select).toHaveValue("female");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["не указан", "Мужской", "Женский"]);

    // Сервер вернул сохранённое — раздел снова показывается готовой информацией.
    put.mockResolvedValue(dossier({ profile: { ...dossier().profile, gender: "male" } }));
    await user.selectOptions(select, "male");
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(put.mock.calls[0][1]).toMatchObject({ gender: "male" });
    expect(await screen.findByText("Мужской")).toBeInTheDocument();
    expect(screen.queryByLabelText("Пол")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Редактировать: Основные сведения" }));
    put.mockResolvedValue(dossier());
    await user.selectOptions(screen.getByLabelText("Пол"), "");
    await user.click(screen.getByRole("button", { name: "Сохранить досье" }));
    expect(put.mock.calls[1][1]).toMatchObject({ gender: null });
  });

  it("очищенное поле уходит как null, а не пустая строка", async () => {
    const user = userEvent.setup();
    open(dossier({ profile: { ...dossier().profile, phone: "123" } }));
    await user.click(await screen.findByRole("button", { name: "Редактировать: Контакты студента" }));
    await user.clear(screen.getByLabelText("Телефон"));
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
    await user.click(within(guardianForm()).getByRole("button", { name: "Добавить представителя" }));
    expect(post).toHaveBeenCalledWith("/students/10/dossier/guardians", {
      full_name: "Иванова А.", relation: "мать", phone: "+7 900 111", is_primary: true,
    });
    await waitFor(() => expect(screen.getByPlaceholderText("ФИО")).toHaveValue(""));
  });

  it("телефон представителя — ссылка «позвонить»; без номера или с мусором вместо номера ссылки нет", async () => {
    open(dossier({
      guardians: [
        { id: 1, full_name: "Иванова А.", relation: "мать", phone: "+7 (900) 111-22-33", is_primary: true },
        { id: 2, full_name: "Иванов Б.", relation: "отец", phone: "не знаю", is_primary: false },
        { id: 3, full_name: "Петрова В.", relation: "бабушка", phone: null, is_primary: false },
      ],
    }));
    const call = await screen.findByRole("link", { name: "Позвонить: Иванова А." });
    expect(call).toHaveAttribute("href", "tel:+79001112233");
    expect(call).toHaveTextContent("+7 (900) 111-22-33");
    expect(screen.getAllByRole("link", { name: /Позвонить/ })).toHaveLength(1);
    expect(screen.getByText("не знаю")).toBeInTheDocument();
    expect((screen.getByText("Петрова В.").closest("article") as HTMLElement)).toHaveTextContent("—");
  });

  it("при ошибке сервера введённое не теряется", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Представители не указаны.");
    await user.type(screen.getByPlaceholderText("ФИО"), "Иванова А.");
    await user.type(screen.getByPlaceholderText(/Кем приходится/), "мать");
    post.mockRejectedValue(new ApiError(404, "Студент не найден"));
    await user.click(within(guardianForm()).getByRole("button", { name: "Добавить представителя" }));
    expect(await screen.findByText("Студент не найден")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("ФИО")).toHaveValue("Иванова А.");
  });

  it("есть представители — форма добавления по кнопке; «Изменить» правит карточку", async () => {
    const user = userEvent.setup();
    open(dossier({ guardians: [{ id: 4, full_name: "Иванов Б.", relation: "отец", phone: null, is_primary: false }] }));
    const card = (await screen.findByText("Иванов Б.")).closest("article") as HTMLElement;
    expect(screen.queryByRole("button", { name: "Добавить представителя" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "+ Добавить представителя" }));
    expect(screen.getByRole("button", { name: "Добавить представителя" })).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Изменить" }));
    const form = screen.getByRole("form", { name: "Изменить: Иванов Б." });
    const phone = within(form).getByLabelText("Телефон представителя");
    await user.type(phone, "+7 900 222-33-44");
    put.mockResolvedValue({});
    await user.click(within(form).getByRole("button", { name: "Сохранить" }));
    expect(put).toHaveBeenCalledWith("/students/10/dossier/guardians/4", {
      full_name: "Иванов Б.", relation: "отец", phone: "+7 900 222-33-44", is_primary: false,
    });
  });

  it("удаляет представителя только после подтверждения", async () => {
    const user = userEvent.setup();
    open(dossier({ guardians: [{ id: 4, full_name: "Иванов Б.", relation: "отец", phone: null, is_primary: true }] }));
    const row = (await screen.findByText("Иванов Б.")).closest("article") as HTMLElement;
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
  const NOTE = { id: 9, kind: "call", text: "Звонок маме", author_id: 2, author_name: "Куратор К.", created_at: "2026-10-01T09:00:00", can_delete: true, occurred_on: null, follow_up_on: null, follow_up_done: false, goal: null, participants: null, result: null };

  it("добавляет заметку выбранного типа", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Заметок пока нет.");
    await user.selectOptions(within(noteForm()).getByRole("combobox"), "incident");
    await user.type(screen.getByPlaceholderText(/Что произошло/), "Конфликт на паре");
    post.mockResolvedValue({});
    await user.click(within(noteForm()).getByRole("button", { name: "Сохранить запись" }));
    expect(post).toHaveBeenCalledWith("/students/10/dossier/notes", { kind: "incident", text: "Конфликт на паре", occurred_on: todayIso() });
  });

  it("новые виды записей и «вернуться к вопросу» уходят на сервер", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Заметок пока нет.");
    const form = noteForm();
    expect(within(form).getByRole("option", { name: "Вызов родителей" })).toBeInTheDocument();
    expect(within(form).getByRole("option", { name: "Совет профилактики" })).toBeInTheDocument();
    expect(within(form).getByRole("option", { name: "Визит домой" })).toBeInTheDocument();
    await user.selectOptions(within(form).getByRole("combobox"), "parent_invited");
    await user.type(screen.getByPlaceholderText(/Что произошло/), "Пригласили маму");
    fireEvent.change(within(form).getByLabelText("Дата"), { target: { value: "2026-10-02" } });
    fireEvent.change(within(form).getByLabelText(/Вернуться к вопросу/), { target: { value: "2026-10-09" } });
    post.mockResolvedValue({});
    await user.click(within(form).getByRole("button", { name: "Сохранить запись" }));
    expect(post).toHaveBeenCalledWith("/students/10/dossier/notes", {
      kind: "parent_invited", text: "Пригласили маму", occurred_on: "2026-10-02", follow_up_on: "2026-10-09",
    });
  });

  it("для беседы можно указать цель, присутствовавших и итог — они уходят на сервер; для инцидента этих полей нет", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Заметок пока нет.");
    const form = noteForm();
    await user.selectOptions(within(form).getByRole("combobox"), "incident");
    expect(within(form).queryByText(/Для протокола беседы/)).not.toBeInTheDocument();
    await user.selectOptions(within(form).getByRole("combobox"), "conversation");
    expect(within(form).getByRole("heading", { name: "Для протокола беседы в Word" })).toBeInTheDocument(); // поля видны сразу
    await user.type(screen.getByPlaceholderText(/Что произошло/), "Обсудили пропуски");
    await user.type(within(form).getByLabelText("Цель беседы"), "Выяснить причины");
    await user.type(within(form).getByLabelText(/Присутствовали/), "Мать, Иванова М.{Enter}Куратор");
    await user.type(within(form).getByLabelText("Итог беседы"), "Договорились");
    post.mockResolvedValue({});
    await user.click(within(form).getByRole("button", { name: "Сохранить запись" }));
    expect(post).toHaveBeenCalledWith("/students/10/dossier/notes", {
      kind: "conversation", text: "Обсудили пропуски", occurred_on: todayIso(),
      goal: "Выяснить причины", participants: "Мать, Иванова М.\nКуратор", result: "Договорились",
    });
  });

  it("«Протокол беседы (Word)» есть у беседы и скачивает файл; у инцидента кнопки нет", async () => {
    const user = userEvent.setup();
    download.mockResolvedValue(undefined);
    const talk = { ...NOTE, id: 21, kind: "conversation", text: "Беседа с мамой", occurred_on: "2026-10-01", goal: "Пропуски", participants: "Мать\nКуратор", result: "Справки" };
    const incident = { ...NOTE, id: 22, kind: "incident", text: "Конфликт", occurred_on: "2026-10-02" };
    open(dossier({ notes: [talk, incident] }));
    const row = (await screen.findByText("Беседа с мамой")).closest("article") as HTMLElement;
    expect(within(row).getByText("Цель").nextSibling).toHaveTextContent("Пропуски");
    expect(within(row).getByText("Присутствовали").nextSibling).toHaveTextContent("Мать; Куратор");
    expect(within(row).getByText("Итог").nextSibling).toHaveTextContent("Справки");
    await user.click(within(row).getByRole("button", { name: "Протокол беседы (Word)" }));
    expect(download).toHaveBeenCalledWith("/students/10/dossier/notes/21/protocol", "Протокол_беседы_2026-10-01.docx");
    const incidentRow = screen.getByText("Конфликт").closest("article") as HTMLElement;
    expect(within(incidentRow).queryByRole("button", { name: /Протокол/ })).not.toBeInTheDocument();
  });

  it("«Сохранить и скачать протокол»: запись сохраняется, затем сразу скачивается её протокол", async () => {
    const user = userEvent.setup();
    download.mockResolvedValue(undefined);
    open(dossier());
    await screen.findByText("Заметок пока нет.");
    const form = noteForm();
    await user.type(screen.getByPlaceholderText(/Что произошло/), "Беседа с мамой о пропусках");
    post.mockResolvedValue({ ...NOTE, id: 31, kind: "conversation", occurred_on: todayIso() });
    await user.click(within(form).getByRole("button", { name: "Сохранить и скачать протокол" }));
    expect(post).toHaveBeenCalledWith("/students/10/dossier/notes", { kind: "conversation", text: "Беседа с мамой о пропусках", occurred_on: todayIso() });
    await waitFor(() => expect(download).toHaveBeenCalledWith("/students/10/dossier/notes/31/protocol", `Протокол_беседы_${todayIso()}.docx`));
  });

  it("без содержания запись не отправляется (поле обязательное)", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Заметок пока нет.");
    await user.click(within(noteForm()).getByRole("button", { name: "Сохранить и скачать протокол" }));
    expect(post).not.toHaveBeenCalled();
  });

  it("у инцидента кнопки протокола в форме нет", async () => {
    const user = userEvent.setup();
    open(dossier());
    await screen.findByText("Заметок пока нет.");
    await user.selectOptions(within(noteForm()).getByRole("combobox"), "incident");
    expect(within(noteForm()).queryByRole("button", { name: "Сохранить и скачать протокол" })).not.toBeInTheDocument();
  });

  it("в списке: дата события, срок возврата с пометкой просрочки, «Выполнено» и «Вернуть в работу»", async () => {
    const user = userEvent.setup();
    const overdue = { ...NOTE, id: 11, text: "Беседа", kind: "conversation", occurred_on: "2026-09-20", follow_up_on: "2026-09-27" };
    const done = { ...NOTE, id: 12, text: "Совет", kind: "prevention_council", occurred_on: "2026-09-21", follow_up_on: "2026-09-30", follow_up_done: true };
    open(dossier({ notes: [overdue, done] }));
    const row = (await screen.findByText("20.09.2026")).closest("article") as HTMLElement;
    expect(within(row).getByText("20.09.2026")).toBeInTheDocument();
    expect(within(row).getByText(/Вернуться к вопросу до 27\.09\.2026 \(просрочено\)/)).toBeInTheDocument();
    put.mockResolvedValue({});
    await user.click(within(row).getByRole("button", { name: "Выполнено" }));
    expect(put).toHaveBeenCalledWith("/students/10/dossier/notes/11/follow-up", { done: true });
    const doneRow = screen.getByText("21.09.2026").closest("article") as HTMLElement;
    expect(within(doneRow).getByText(/выполнено/)).toBeInTheDocument();
    await user.click(within(doneRow).getByRole("button", { name: "Вернуть в работу" }));
    expect(put).toHaveBeenCalledWith("/students/10/dossier/notes/12/follow-up", { done: false });
  });

  it("кнопка «Удалить» у заметки только там, где разрешено", async () => {
    open(dossier({ notes: [NOTE, { ...NOTE, id: 10, text: "Чужая заметка", can_delete: false }] }));
    const own = (await screen.findByText("Звонок маме")).closest("article") as HTMLElement;
    const foreign = screen.getByText("Чужая заметка").closest("article") as HTMLElement;
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
