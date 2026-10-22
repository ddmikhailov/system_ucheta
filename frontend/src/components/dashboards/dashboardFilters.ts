// Фильтры вкладок витрин: имя в памяти записи истории (useEntryState) → значение по умолчанию.
// Страница сбрасывает их все при смене отделения; сортировки и список «Группа риска/Восполнить» не сбрасываются.
export const DAY_FILTERS = { courseFilter: "all", dayQuery: "", dayStatus: "all", dayOnlyAbsent: false };

export const DYNAMICS_FILTERS = { dynOnlyData: false, dynBelow: "" };

export const RISK_FILTERS = { riskQuery: "", riskGroup: "all", riskBelow: "" };

export const DISCIPLINE_FILTERS = { discQuery: "", discCourse: "all", discOnlyMissed: false };
