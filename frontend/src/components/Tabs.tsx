import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";

export interface TabItem {
  key: string;
  label: string;
  /** Короткое число или пометка справа от названия (например, число записей). */
  badge?: ReactNode;
}

/** Полоса вкладок по образцу WAI-ARIA: стрелки ←/→, Home/End переключают вкладку,
 * в порядке Tab — только активная. На телефоне полоса прокручивается вбок. */
export function TabBar({
  tabs,
  active,
  onChange,
  label,
  idPrefix,
}: {
  tabs: TabItem[];
  active: string;
  onChange: (key: string) => void;
  label: string;
  idPrefix: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  // На телефоне полоса прокручивается: открытая по ссылке вкладка не должна оказаться за краем.
  useEffect(() => {
    // Двигаем только саму полосу, не страницу.
    const tab = refs.current[active];
    const bar = tab?.parentElement;
    if (!tab || !bar || bar.scrollWidth <= bar.clientWidth) return;
    const left = tab.offsetLeft - bar.offsetLeft;
    if (left < bar.scrollLeft || left + tab.offsetWidth > bar.scrollLeft + bar.clientWidth) {
      bar.scrollLeft = Math.max(0, left - 16);
    }
  }, [active]);

  function onKeyDown(e: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = -1;
    if (e.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    e.preventDefault();
    const key = tabs[next].key;
    onChange(key);
    refs.current[key]?.focus();
  }

  return (
    <div className="tabbar" role="tablist" aria-label={label}>
      {tabs.map((t, i) => {
        const selected = t.key === active;
        return (
          <button
            key={t.key}
            ref={(el) => {
              refs.current[t.key] = el;
            }}
            type="button"
            role="tab"
            id={`${idPrefix}-tab-${t.key}`}
            aria-selected={selected}
            aria-controls={`${idPrefix}-panel-${t.key}`}
            tabIndex={selected ? 0 : -1}
            className={`tabbar__tab${selected ? " is-active" : ""}`}
            onClick={() => onChange(t.key)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {t.label}
            {t.badge !== undefined && t.badge !== null && <span className="tabbar__badge">{t.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Панель вкладки. Создаётся при первом открытии и дальше только прячется — несохранённый
 * ввод в формах не теряется при переходе между вкладками, а данные не грузятся заново. */
export function TabPanel({
  idPrefix,
  tabKey,
  active,
  children,
}: {
  idPrefix: string;
  tabKey: string;
  active: string;
  children: ReactNode;
}) {
  const isActive = tabKey === active;
  const [visited, setVisited] = useState(isActive);
  if (isActive && !visited) setVisited(true);
  if (!visited) return null;
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${tabKey}`}
      aria-labelledby={`${idPrefix}-tab-${tabKey}`}
      hidden={!isActive}
      className="tabpanel"
    >
      {children}
    </div>
  );
}
