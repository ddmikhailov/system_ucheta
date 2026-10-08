import { describe, expect, it } from "vitest";
import { credentialsCsv } from "./credentialsCsv";

describe("credentialsCsv", () => {
  it("BOM, разделитель «;», кавычки экранируются", () => {
    const csv = credentialsCsv([{ full_name: 'Иванова "Маша" Ивановна', department: "Диджитал", username: "ivanova.m", password: "Ab3;xyz" }]);
    expect(csv.startsWith("﻿\"ФИО\";\"Отделение\";\"Логин\";\"Временный пароль\"\r\n")).toBe(true);
    expect(csv).toContain('"Иванова ""Маша"" Ивановна";"Диджитал";"ivanova.m";"Ab3;xyz"');
  });
});
