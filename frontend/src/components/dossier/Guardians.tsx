import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { telHref } from "../../utils/phone";
import type { Dossier } from "../../api/types";
import { dialogs, toast } from "../../utils/feedback";
import { Field } from "./shared";

/** Поля представителя — одна форма для добавления и для правки. */
function GuardianFields({
  value,
  onChange,
}: {
  value: { full_name: string; relation: string; phone: string; is_primary: boolean };
  onChange: (v: { full_name: string; relation: string; phone: string; is_primary: boolean }) => void;
}) {
  return (
    <>
      <div className="dossier-grid">
        <Field label="ФИО представителя" wide>
          <input placeholder="ФИО" value={value.full_name} onChange={(e) => onChange({ ...value, full_name: e.target.value })} required />
        </Field>
        <Field label="Кем приходится">
          <input
            placeholder="Кем приходится (мать, отец, опекун…)"
            value={value.relation}
            onChange={(e) => onChange({ ...value, relation: e.target.value })}
            required
          />
        </Field>
        <Field label="Телефон представителя">
          <input type="tel" inputMode="tel" placeholder="Телефон" value={value.phone} onChange={(e) => onChange({ ...value, phone: e.target.value })} />
        </Field>
      </div>
      <label className={`toggle-tile toggle-tile--inline${value.is_primary ? " is-on" : ""}`}>
        <input type="checkbox" checked={value.is_primary} onChange={(e) => onChange({ ...value, is_primary: e.target.checked })} />
        <span>Основной представитель</span>
      </label>
    </>
  );
}

const EMPTY_GUARDIAN = { full_name: "", relation: "", phone: "", is_primary: false };

export function Guardians({
  dossier,
  studentId,
  onChanged,
  onError,
}: {
  dossier: Dossier;
  studentId: number;
  onChanged: () => void;
  onError: (e: string | null) => void;
}) {
  const [draft, setDraft] = useState(EMPTY_GUARDIAN);
  // Нет представителей — форма открыта сразу; есть — по кнопке «+ Добавить представителя».
  const [adding, setAdding] = useState(dossier.guardians.length === 0);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState(EMPTY_GUARDIAN);
  const base = `/students/${studentId}/dossier/guardians`;

  async function run(action: () => Promise<unknown>, fail: string): Promise<boolean> {
    onError(null);
    try {
      await action();
      onChanged();
      return true;
    } catch (err) {
      onError(err instanceof ApiError ? err.message : fail);
      return false;
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    const ok = await run(
      () => api.post(base, { full_name: draft.full_name, relation: draft.relation, phone: draft.phone || null, is_primary: draft.is_primary }),
      "Не удалось добавить представителя"
    );
    if (!ok) return;
    setDraft(EMPTY_GUARDIAN);
    toast("Представитель добавлен");
  }

  async function update(e: FormEvent) {
    e.preventDefault();
    if (editingId === null) return;
    const ok = await run(
      () =>
        api.put(`${base}/${editingId}`, {
          full_name: editDraft.full_name, relation: editDraft.relation, phone: editDraft.phone || null, is_primary: editDraft.is_primary,
        }),
      "Не удалось сохранить представителя"
    );
    if (ok) setEditingId(null);
  }

  return (
    <div className="dossier-form">
      <section className="dossier-section">
        <header className="dossier-section__head dossier-section__head--row">
          <div>
            <h4>Законные представители</h4>
            <p>Родители, опекуны — те, кому звонить и кого приглашать. Основной — тот, с кем связываются в первую очередь.</p>
          </div>
          {!adding && (
            <button type="button" className="btn-secondary" onClick={() => setAdding(true)}>
              + Добавить представителя
            </button>
          )}
        </header>
        {dossier.guardians.length === 0 ? (
          <p className="hint">Представители не указаны.</p>
        ) : (
          <div className="person-list">
            {dossier.guardians.map((g) =>
              editingId === g.id ? (
                <form key={g.id} className="person-card person-card--edit" onSubmit={update} aria-label={`Изменить: ${g.full_name}`}>
                  <GuardianFields value={editDraft} onChange={setEditDraft} />
                  <div className="dossier-actions">
                    <button type="button" className="btn-secondary" onClick={() => setEditingId(null)}>
                      Отмена
                    </button>
                    <button type="submit" className="btn-primary">
                      Сохранить
                    </button>
                  </div>
                </form>
              ) : (
                <article key={g.id} className="person-card">
                  <div className="person-card__main">
                    <b>{g.full_name}</b> {g.is_primary && <span className="locked-badge">основной</span>}
                    <span className="hint">{g.relation}</span>
                  </div>
                  <div className="person-card__phone">
                    {telHref(g.phone) ? (
                      <a className="btn-secondary person-card__call" href={telHref(g.phone)!} aria-label={`Позвонить: ${g.full_name}`}>
                        {g.phone}
                      </a>
                    ) : (
                      <span className="hint">{g.phone ?? "—"}</span>
                    )}
                  </div>
                  <span className="person-card__actions">
                    <button
                      type="button"
                      className="link-btn"
                      onClick={() => {
                        setEditingId(g.id);
                        setEditDraft({ full_name: g.full_name, relation: g.relation, phone: g.phone ?? "", is_primary: g.is_primary });
                      }}
                    >
                      Изменить
                    </button>
                    <button
                      type="button"
                      className="link-btn danger-link"
                      onClick={async () => {
                        if (await dialogs.confirm(`Удалить представителя «${g.full_name}»?`, { confirmLabel: "Удалить", danger: true }))
                          run(() => api.delete(`${base}/${g.id}`), "Не удалось удалить");
                      }}
                    >
                      Удалить
                    </button>
                  </span>
                </article>
              )
            )}
          </div>
        )}
      </section>

      {adding && (
        <form className="dossier-section" onSubmit={add}>
          <header className="dossier-section__head">
            <h4>Добавить представителя</h4>
          </header>
          <GuardianFields value={draft} onChange={setDraft} />
          <div className="dossier-actions">
            {dossier.guardians.length > 0 && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setAdding(false);
                  setDraft(EMPTY_GUARDIAN);
                }}
              >
                Отмена
              </button>
            )}
            <button type="submit" className="btn-primary">
              Добавить представителя
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
