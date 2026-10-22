/** Ошибка и «Загрузка…» вкладки — над её фильтрами. */
export default function LoadState({ error, loading }: { error: string | null; loading: boolean }) {
  return (
    <>
      {error && <div className="error-text">{error}</div>}
      {loading && <p className="hint">Загрузка…</p>}
    </>
  );
}
