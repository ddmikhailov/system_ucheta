// Поиск по началу слова в длинных списках (группы, кураторы): человек вводит «GD»,
// «ГД» или забыл переключить раскладку — во всех случаях остаются «ГД116», «ГД136»…

const QWERTY = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`";
const JCUKEN = "йцукенгшщзхъфывапролджэячсмитьбюё";

// Те же клавиши, но в русской раскладке: «ghbdtn» → «привет».
function fromWrongLayout(text: string): string {
  return Array.from(text)
    .map((ch) => {
      const i = QWERTY.indexOf(ch);
      return i === -1 ? ch : JCUKEN[i];
    })
    .join("");
}

const LATIN_TO_CYRILLIC: Record<string, string> = {
  a: "а", b: "б", v: "в", g: "г", d: "д", e: "е", z: "з", i: "и", k: "к", l: "л", m: "м",
  n: "н", o: "о", p: "п", r: "р", s: "с", t: "т", u: "у", f: "ф", h: "х", c: "ц", y: "ы",
  j: "й", x: "кс", q: "к", w: "в",
};

// По звучанию: «GD» → «гд», «SA» → «са», «ISP» → «исп».
function transliterate(text: string): string {
  return Array.from(text)
    .map((ch) => LATIN_TO_CYRILLIC[ch] ?? ch)
    .join("");
}

const fold = (text: string) => text.toLowerCase().replace(/ё/g, "е");

/** Все варианты, как запрос мог бы выглядеть в тексте списка. */
export function queryVariants(query: string): string[] {
  const q = fold(query.trim());
  if (!q) return [];
  return Array.from(new Set([q, fold(transliterate(q)), fold(fromWrongLayout(q))]));
}

/** Оставляет подходящие варианты: сначала те, что начинаются с запроса (или со слова
 * внутри названия), а если таких нет — те, где запрос встречается где угодно. Порядок
 * исходного списка сохраняется, первым идёт самое точное совпадение. */
export function filterByQuery<T>(items: T[], query: string, label: (item: T) => string): T[] {
  const variants = queryVariants(query);
  if (variants.length === 0) return items;

  const labels = items.map((item) => fold(label(item)));
  const startsWith = (text: string) =>
    variants.some((v) => text.startsWith(v) || text.split(/[\s\-.,()]+/).some((word) => word.startsWith(v)));
  const prefix = items.filter((_, i) => startsWith(labels[i]));
  if (prefix.length > 0) {
    // Совпадение с самого начала названия — выше, чем со слова внутри него.
    const fromStart = (i: T) => variants.some((v) => fold(label(i)).startsWith(v));
    return [...prefix.filter(fromStart), ...prefix.filter((i) => !fromStart(i))];
  }
  return items.filter((_, i) => variants.some((v) => labels[i].includes(v)));
}
