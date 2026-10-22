import { useState } from "react";
import type { Dossier } from "../api/types";
import { useApi } from "./useApi";

export type DossierSectionKey = "profile" | "guardians" | "notes" | "log";

export interface DossierState {
  dossier: Dossier | null;
  error: string | null;
  notice: string | null;
  setDossier: (d: Dossier) => void;
  setError: (e: string | null) => void;
  setNotice: (n: string | null) => void;
  load: () => void;
}

/** Досье грузится один раз на карточку: вкладки «Досье», «Представители» и «Индивидуальная
 * работа» берут его отсюда, и просмотр пишется в журнал один раз, а не на каждую вкладку.
 * `enabled=false` (модуль выключен) — досье не запрашивается. */
export function useDossier(studentId: number, enabled = true): DossierState {
  const { data, error: loadError, setData, reload } = useApi<Dossier>(
    enabled ? `/students/${studentId}/dossier` : null,
    "Не удалось загрузить досье",
  );
  // Ошибки сохранения разделов; ошибка загрузки — своя, из useApi, и уходит с успешной перезагрузкой.
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  return { dossier: data, error: error ?? loadError, notice, setDossier: setData, setError, setNotice, load: reload };
}
