import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { reportClientError } from "../utils/errorReporting";

// Ошибка при загрузке куска интерфейса (после обновления старые файлы удалены, а вкладка открыта давно).
const STALE_BUNDLE = /dynamically imported module|Importing a module script failed|error loading dynamically imported/i;

interface State {
  error: Error | null;
}

/** Сбой отрисовки раздела: вместо белого экрана — понятное сообщение и кнопка «Обновить страницу»,
 * а ошибка уходит на сервер. Меню вокруг раздела остаётся рабочим. */
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (info.componentStack && !error.stack?.includes(info.componentStack)) {
      error.stack = `${error.stack ?? ""}\nКомпоненты:${info.componentStack}`;
    }
    reportClientError(error);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const stale = STALE_BUNDLE.test(error.message);
    return (
      <div className="error-boundary" role="alert">
        <h2>{stale ? "Платформа обновилась" : "Что-то пошло не так"}</h2>
        <p>
          {stale
            ? "Чтобы продолжить, обновите страницу — несохранённые данные на этой странице могут потеряться."
            : "Раздел не открылся из-за ошибки. Обновите страницу; если ошибка повторится, напишите через «Сообщить о проблеме» в меню под вашим именем."}
        </p>
        <button type="button" className="btn-primary" onClick={() => window.location.reload()}>
          Обновить страницу
        </button>
      </div>
    );
  }
}
