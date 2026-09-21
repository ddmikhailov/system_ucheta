import { useState } from "react";
import { api, ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { TelegramLinkResponse } from "../api/types";

export default function TelegramStatus() {
  const { user, refresh } = useAuth();
  const [open, setOpen] = useState(false);
  const [deepLink, setDeepLink] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  async function startLink() {
    setError(null);
    setBusy(true);
    try {
      const res = await api.post<TelegramLinkResponse>("/auth/telegram/link");
      setDeepLink(res.deep_link);
      setOpen(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось получить ссылку");
      setOpen(true);
    } finally {
      setBusy(false);
    }
  }

  async function checkStatus() {
    setBusy(true);
    await refresh();
    setBusy(false);
  }

  async function doUnlink() {
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/telegram/unlink");
      await refresh();
      setOpen(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось отключить");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="telegram-badge" onClick={() => (user.telegram_linked ? setOpen(true) : startLink())}>
        {user.telegram_linked ? "Telegram подключён" : "Подключить Telegram"}
      </button>

      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Telegram-уведомления</h3>

            {error && <div className="error-text">{error}</div>}

            {user.telegram_linked ? (
              <>
                <p>Подключён. Напоминания и сводки будут приходить в Telegram.</p>
                <div className="actions">
                  <button onClick={() => setOpen(false)}>Закрыть</button>
                  <button onClick={doUnlink} disabled={busy}>
                    Отключить
                  </button>
                </div>
              </>
            ) : deepLink ? (
              <>
                <p>
                  Перейдите по ссылке в Telegram и нажмите «Старт» — бот сам написать первым не может,
                  пока вы не начали диалог.
                </p>
                <p>
                  <a href={deepLink} target="_blank" rel="noreferrer">
                    Открыть Telegram
                  </a>
                </p>
                <div className="actions">
                  <button onClick={() => setOpen(false)}>Закрыть</button>
                  <button onClick={checkStatus} disabled={busy}>
                    Я подключил — проверить
                  </button>
                </div>
              </>
            ) : (
              <div className="actions">
                <button onClick={() => setOpen(false)}>Закрыть</button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
