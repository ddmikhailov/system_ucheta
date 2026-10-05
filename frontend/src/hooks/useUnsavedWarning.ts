import { useEffect } from "react";

/** Пока есть несохранённые изменения, браузер переспросит при закрытии вкладки, перезагрузке
 * или переходе по внешней ссылке. Переходы внутри приложения страница проверяет сама. */
export function useUnsavedWarning(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    function handler(e: BeforeUnloadEvent) {
      e.preventDefault();
      // Старые браузеры показывают диалог только при заданном returnValue.
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);
}
