import type { UserActivityEntry } from "../api/types";
import { auditActionLabel } from "../constants/auditActions";
import { formatServerDateTimeFull } from "./date";

/** Месяц журнала действий — CSV для Excel (UTF-8 с BOM, разделитель «;»), собирается в браузере. «Было/стало»
 * сервер не отдаёт, поэтому в файле только факт: когда, что сделано и над чем. */
export function activityCsv(entries: UserActivityEntry[]): string {
  const cell = (v: string) => `"${v.replace(/"/g, '""')}"`;
  const lines = [
    ["Когда", "Действие", "Объект", "Номер объекта"],
    ...entries.map((e) => [formatServerDateTimeFull(e.created_at), auditActionLabel(e.action), e.entity_type, e.entity_id]),
  ];
  return "﻿" + lines.map((l) => l.map(cell).join(";")).join("\r\n");
}
