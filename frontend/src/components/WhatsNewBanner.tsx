import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { APP_VERSION, WHATS_NEW } from "../constants/release";
import { whatsNewState } from "../utils/whatsNew";

/** Плашка «Что нового» над страницей: один раз после обновления, пока человек её не закроет. Отметку хранит
 * сервер, поэтому на телефоне и на компьютере она не появляется повторно. */
export default function WhatsNewBanner() {
  const { user } = useAuth();
  const [closed, setClosed] = useState(whatsNewState.closedInThisTab);
  const items = WHATS_NEW[APP_VERSION];
  if (!user || !items || closed || user.seen_release === APP_VERSION) return null;

  function close() {
    whatsNewState.closedInThisTab = true;
    setClosed(true);
    // Не дошло до сервера — плашка покажется ещё раз после перезагрузки; это лучше, чем ошибка на экране.
    api.post("/support/release-seen", { release: APP_VERSION }).catch(() => undefined);
  }

  return (
    <section className="whats-new" aria-labelledby="whats-new-title">
      <h2 id="whats-new-title" className="whats-new__title">
        Что нового в версии {APP_VERSION}
      </h2>
      <ul className="whats-new__list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <button type="button" className="btn-secondary whats-new__close" onClick={close}>
        Понятно
      </button>
    </section>
  );
}
