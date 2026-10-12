import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Dossier } from "../api/types";

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
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!enabled) return; // модуль «Досье» выключен — запроса нет
    api
      .get<Dossier>(`/students/${studentId}/dossier`)
      .then((d) => {
        setDossier(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить досье"));
  }, [studentId, enabled]);

  useEffect(load, [load]);
  return { dossier, error, notice, setDossier, setError, setNotice, load };
}
