import type { PracticeState } from "../api/types";

/** Подпись состояния практики для куратора и сводки заведующего. */
export const PRACTICE_STATE_LABEL: Record<Exclude<PracticeState, null>, string> = {
  active: "Идёт сейчас",
  soon: "Скоро начнётся",
  no_review: "Нет характеристики",
};
