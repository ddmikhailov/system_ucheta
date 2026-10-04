/** Заглушка страницы для тестов маршрутизации: `vi.mock("./pages/X", () => stubPage("x"))`. */
export function stubPage(name: string) {
  return { default: () => <div>страница: {name}</div> };
}
