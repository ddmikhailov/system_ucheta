import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatusMark from "./StatusMark";
import { markKind } from "../utils/statusMark";

describe("markKind", () => {
  it("замок и итоговые статусы важнее просрочки", () => {
    expect(markKind({ status: "new", is_locked: true, is_overdue: true })).toBe("locked");
    expect(markKind({ status: "accepted", is_overdue: true })).toBe("accepted");
    expect(markKind({ status: "returned", is_overdue: true })).toBe("returned");
  });

  it("просрочка поверх рабочих статусов", () => {
    expect(markKind({ status: "in_progress", is_overdue: true })).toBe("overdue");
    expect(markKind({ status: "submitted", is_overdue: true })).toBe("overdue");
  });

  it("обычные статусы как есть, неизвестный — «не начато»", () => {
    expect(markKind({ status: "in_progress" })).toBe("in_progress");
    expect(markKind({ status: "submitted" })).toBe("submitted");
    expect(markKind({ status: "что-то новое" })).toBe("new");
  });
});

describe("StatusMark", () => {
  it("без подписи — доступное имя у значка", () => {
    render(<StatusMark kind="returned" />);
    expect(screen.getByRole("img", { name: "Возвращено" })).toBeInTheDocument();
  });

  it("с подписью — видимый текст, значок скрыт от диктора", () => {
    render(<StatusMark kind="accepted" withLabel />);
    expect(screen.getByText("Принято")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("свой текст подписи", () => {
    render(<StatusMark kind="submitted" withLabel label="На проверке (ступень 2 из 2)" />);
    expect(screen.getByText("На проверке (ступень 2 из 2)")).toBeInTheDocument();
  });
});
