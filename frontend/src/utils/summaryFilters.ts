import { toIso, todayIso } from "./date";

export type SliceMode = "both" | "all" | "pair";

export interface SummaryFilters {
  dateFrom: string;
  dateTo: string;
  departmentId: number | "all";
  course: number | "all";
  groupId: number | "all";
  pair: number;
  slice: SliceMode;
  hiddenCodes: string[];
  onlyProblems: boolean;
  threshold: number;
  hideEmpty: boolean;
}

export function daysAgoIso(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return toIso(d);
}

export function defaultSummaryFilters(): SummaryFilters {
  return {
    dateFrom: daysAgoIso(14),
    dateTo: todayIso(),
    departmentId: "all",
    course: "all",
    groupId: "all",
    pair: 1,
    slice: "both",
    hiddenCodes: [],
    onlyProblems: false,
    threshold: 90,
    hideEmpty: true,
  };
}

/** Параметры выгрузки Excel: те же период, отделение, курс, группа и пара, что
 * выбраны на экране (столбцы, пороги и сортировка действуют только на экране). */
export function summaryExportParams(f: SummaryFilters, canFilterDepartment: boolean): string {
  const parts = [`date_from=${f.dateFrom}`, `date_to=${f.dateTo}`, `pair=${f.pair}`];
  if (canFilterDepartment && f.departmentId !== "all") parts.push(`department_id=${f.departmentId}`);
  if (f.course !== "all") parts.push(`course=${f.course}`);
  if (f.groupId !== "all") parts.push(`study_group_id=${f.groupId}`);
  return parts.join("&");
}
