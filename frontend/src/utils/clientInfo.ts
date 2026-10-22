// Сведения о браузере, которые интерфейс прикладывает к сообщению о проблеме и к ошибке: человеку не нужно
// объяснять, где и в чём он работал. Только адрес страницы без параметров (в них бывают номера и поиск по ФИО).

const BROWSERS: [RegExp, string][] = [
  [/YaBrowser\/(\d+)/, "Яндекс Браузер"],
  [/Edg\/(\d+)/, "Edge"],
  [/OPR\/(\d+)/, "Opera"],
  [/Firefox\/(\d+)/, "Firefox"],
  [/Chrome\/(\d+)/, "Chrome"],
  [/Version\/(\d+)[\d.]* .*Safari/, "Safari"],
];

const SYSTEMS: [RegExp, string][] = [
  [/Android/, "Android"],
  [/iPhone|iPad|iPod/, "iOS"],
  [/Windows/, "Windows"],
  [/Mac OS X/, "macOS"],
  [/Linux/, "Linux"],
];

/** «Chrome 141 · Android» из строки User-Agent; незнакомый браузер — первые символы строки как есть. */
export function describeBrowser(userAgent: string): string {
  const browser = BROWSERS.map(([re, name]) => {
    const m = userAgent.match(re);
    return m ? `${name} ${m[1]}` : null;
  }).find(Boolean);
  const system = SYSTEMS.find(([re]) => re.test(userAgent))?.[1];
  if (!browser) return userAgent.slice(0, 120);
  return system ? `${browser} · ${system}` : browser;
}

export interface ClientContext {
  page: string;
  version: string;
  browser: string;
  screen: string;
}

export function clientContext(version: string): ClientContext {
  return {
    page: window.location.pathname,
    version,
    browser: describeBrowser(navigator.userAgent),
    screen: `${window.innerWidth}×${window.innerHeight}`,
  };
}
