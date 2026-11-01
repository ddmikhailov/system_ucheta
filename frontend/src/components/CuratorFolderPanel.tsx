import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, downloadFile } from "../api/client";
import type { CuratorFolder, FolderItem, FolderItemState } from "../api/types";
import GroupAssemblies from "./GroupAssemblies";

const STATE_LABEL: Record<FolderItemState, string> = {
  filled: "Есть данные",
  blank: "Пустой бланк",
  outside: "Вне платформы",
  off: "Раздел отключён",
};
// Сколько кнопок выгрузки видно сразу; остальные (беседы, месяцы) — под «Показать все».
const VISIBLE_DOWNLOADS = 4;

function openLink(item: FolderItem): string | null {
  if (!item.open_tab) return null;
  return `?tab=${item.open_tab}${item.open_part ? `&part=${item.open_part}` : ""}`;
}

/** «Папка куратора»: 16 документов п. 5.1 положения о кураторе. У каждого — что есть в платформе и кнопки выгрузки,
 * чтобы куратор в любой момент забрал нужный документ сам (проверка комплекта заведующим в платформе не ведётся). */
export default function CuratorFolderPanel({ groupId }: { groupId: number }) {
  const [folder, setFolder] = useState<CuratorFolder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .get<CuratorFolder>(`/folder/groups/${groupId}`)
      .then((f) => {
        if (cancelled) return;
        setFolder(f);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Не удалось загрузить папку куратора");
      });
    return () => {
      cancelled = true;
    };
  }, [groupId, reload]);

  async function download(path: string, filename: string) {
    setBusy(path);
    try {
      await downloadFile(path, filename);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось скачать документ");
    } finally {
      setBusy(null);
    }
  }

  function button(d: FolderItem["downloads"][number]) {
    return (
      <button key={d.path} type="button" className="btn-secondary" disabled={busy === d.path} onClick={() => download(d.path, d.filename)}>
        {busy === d.path ? "Готовлю…" : d.label}
      </button>
    );
  }

  if (!folder) return error ? <div className="error-text">{error}</div> : <p className="hint">Загрузка…</p>;
  return (
    <section className="folder" aria-label="Папка куратора">
      <p className="hint folder__intro">
        Комплект документов куратора за {folder.school_year} учебный год (пункт 5.1 положения). Скачивайте нужное сами: платформа
        собирает документ из ваших данных, а где данных нет, даёт пустой бланк.
      </p>
      {error && <div className="error-text">{error}</div>}
      <ul className="folder__list">
        {folder.items.map((item) => {
          const head = item.downloads.slice(0, VISIBLE_DOWNLOADS);
          const rest = item.downloads.slice(VISIBLE_DOWNLOADS);
          const link = openLink(item);
          return (
            <li key={item.code} className={`folder-item folder-item--${item.state}`}>
              <div className="folder-item__head">
                <span className="folder-item__code">{item.code}</span>
                <h3 className="folder-item__title">{item.title}</h3>
                <span className={`folder-item__state folder-item__state--${item.state}`}>{STATE_LABEL[item.state]}</span>
              </div>
              <p className="folder-item__note">{item.note}</p>
              {item.can_add === "assembly" && (
                <GroupAssemblies groupId={groupId} year={folder.school_year} onChanged={() => setReload((n) => n + 1)} />
              )}
              {item.can_add !== "assembly" && item.downloads.length > 0 && (
                <div className="folder-item__actions">
                  {head.map(button)}
                  {rest.length > 0 && (
                    <details className="folder-item__more">
                      <summary>Показать все ({item.downloads.length})</summary>
                      <div className="folder-item__actions">{rest.map(button)}</div>
                    </details>
                  )}
                </div>
              )}
              {link && item.state !== "off" && (
                <Link className="folder-item__open" to={link}>
                  Открыть раздел
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
