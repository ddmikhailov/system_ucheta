import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { api, ApiError } from "../api/client";
import { NOTE_KINDS, PROTOCOL_KINDS } from "../constants/noteKinds";
import { downloadProtocol } from "../utils/protocol";
import NoteForm from "./NoteForm";
import { formatDateRu, formatServerDateTimeFull, todayIso } from "../utils/date";
import { telHref } from "../utils/phone";
import type { Dossier, DossierAccessEntry, DossierNote, DossierProfile, DossierSpecial } from "../api/types";
import { useDossier, type DossierSectionKey, type DossierState } from "../hooks/useDossier";
import { dialogs, toast } from "../utils/feedback";
import { useUnsavedWarning } from "../hooks/useUnsavedWarning";
import StudentCardModal from "./StudentCardModal";
import TextArea from "./TextArea";


const EMPTY_SPECIAL: DossierSpecial = {
  is_orphan: false,
  under_guardianship: false,
  disability_group: null,
  has_ovz: false,
  large_family: false,
  incomplete_family: null,
  low_income: false,
  dysfunctional_family: false,
  parent_disabled: false,
  pdn_kdn: false,
  internal_record: false,
  scholarship: null,
  health_note: null,
};

type SpecialFlag =
  | "is_orphan"
  | "under_guardianship"
  | "has_ovz"
  | "large_family"
  | "low_income"
  | "dysfunctional_family"
  | "parent_disabled"
  | "pdn_kdn"
  | "internal_record";

const SPECIAL_FLAGS: [SpecialFlag, string][] = [
  ["is_orphan", "Сирота"],
  ["under_guardianship", "Под опекой"],
  ["has_ovz", "ОВЗ"],
  ["large_family", "Многодетная семья"],
  ["low_income", "Малоимущая семья"],
  ["dysfunctional_family", "Неблагополучная семья"],
  ["parent_disabled", "Родитель — инвалид"],
  ["pdn_kdn", "Учёт ПДН/КДН"],
  ["internal_record", "Внутренний учёт"],
];

/** Один раздел досье: основное и соц. статус, представители, записи индивидуальной работы
 * или журнал просмотров (последний — только администратору/тьютору). */
export function DossierSection({
  state,
  section,
  studentId,
  isAdmin,
  showMessages = true,
}: {
  state: DossierState;
  section: DossierSectionKey;
  studentId: number;
  isAdmin: boolean;
  /** Ошибки и «сохранено» над разделом; досье целиком показывает их один раз сверху. */
  showMessages?: boolean;
}) {
  const { dossier, error, notice, setDossier, setError, setNotice, load } = state;
  const [cardOpen, setCardOpen] = useState(false);
  if (section === "log") return isAdmin ? <AccessLog studentId={studentId} /> : null;
  if (error && !dossier) return <div className="error-text">{error}</div>;
  if (!dossier) return <p className="hint">Загрузка досье…</p>;

  return (
    <div>
      {showMessages && error && <div className="error-text">{error}</div>}
      {showMessages && notice && <div className="day-status submitted">{notice}</div>}
      {section === "profile" && (
        <div className="dossier-toolbar">
          <p className="hint">Заполненное показывается готовой информацией, изменить — кнопкой «Редактировать» в разделе.</p>
          <button type="button" className="btn-secondary" onClick={() => setCardOpen(true)} title="Бланк колледжа в Word: выберите, какие поля заполнить">
            Личная карточка в Word
          </button>
        </div>
      )}
      {section === "profile" && cardOpen && (
        <StudentCardModal
          endpoint={`/students/${studentId}/dossier/card`}
          heading="Личная карточка обучающегося"
          filename={`Личная_карточка_${studentId}.docx`}
          onClose={() => setCardOpen(false)}
        />
      )}
      {section === "profile" && (
        <ProfileForm
          // Форма берёт значения из досье один раз; после сохранения key пересоздаёт её.
          key={JSON.stringify([dossier.profile, dossier.special])}
          dossier={dossier}
          onSaved={(d) => {
            setDossier(d);
            setError(null);
            setNotice("Досье сохранено");
          }}
          onError={setError}
        />
      )}
      {section === "guardians" && <Guardians dossier={dossier} studentId={studentId} onChanged={load} onError={setError} />}
      {section === "notes" && <Notes dossier={dossier} studentId={studentId} onChanged={load} onError={setError} />}
    </div>
  );
}

// Досье студента целиком: контакты, представители, особые данные (шифруются на сервере),
// заметки куратора. Журнал просмотров — только администратору/тьютору.
export default function StudentDossier({ studentId, isAdmin }: { studentId: number; isAdmin: boolean }) {
  const state = useDossier(studentId);
  if (state.error && !state.dossier) return <div className="error-text">{state.error}</div>;
  if (!state.dossier) return <p className="hint">Загрузка досье…</p>;
  return (
    <div>
      {state.error && <div className="error-text">{state.error}</div>}
      {state.notice && <div className="day-status submitted">{state.notice}</div>}
      {(["profile", "guardians", "notes", "log"] as const).map((section) => (
        <DossierSection key={section} state={state} section={section} studentId={studentId} isAdmin={isAdmin} showMessages={false} />
      ))}
    </div>
  );
}

// Поле с видимой подписью сверху и необязательной подсказкой снизу: подпись всегда над полем, одной ширины с ним,
// поэтому ряды не «скачут»; плейсхолдер — только пример ввода.
function Field({ label, hint, wide, children }: { label: string; hint?: string; wide?: boolean; children: ReactNode }) {
  return (
    <label className={`dossier-field${wide ? " dossier-field--wide" : ""}`}>
      <span className="dossier-field__label">{label}</span>
      {children}
      {hint && <span className="dossier-field__hint">{hint}</span>}
    </label>
  );
}

/** Значение для режима просмотра: пустое — приглушённое «не указано», а не пустая строка. */
function Info({ label, value, wide }: { label: string; value: ReactNode; wide?: boolean }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className={`info-item${wide ? " info-item--wide" : ""}`}>
      <dt>{label}</dt>
      <dd className={empty ? "info-empty" : undefined}>{empty ? "не указано" : value}</dd>
    </div>
  );
}

/** Раздел досье с двумя режимами. Сведения заполняются один раз и меняются редко: если в разделе уже что-то
 * есть, он показывается готовой информацией с кнопкой «Редактировать»; пустой раздел сразу открыт для ввода. */
function DossierBlock({
  title,
  subtitle,
  filled,
  isPrivate,
  view,
  children,
}: {
  title: string;
  subtitle?: string;
  /** Есть ли в разделе сохранённые данные — тогда по умолчанию просмотр. */
  filled: boolean;
  isPrivate?: boolean;
  view: ReactNode;
  children: ReactNode;
}) {
  const [editing, setEditing] = useState(!filled);
  return (
    <section className={`dossier-section${isPrivate ? " dossier-section--private" : ""}${editing ? " is-editing" : ""}`}>
      <header className="dossier-section__head dossier-section__head--row">
        <div>
          <h4>{title}</h4>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {filled &&
          (editing ? (
            <button type="button" className="link-btn" onClick={() => setEditing(false)}>
              Свернуть
            </button>
          ) : (
            <button type="button" className="btn-secondary" onClick={() => setEditing(true)} aria-label={`Редактировать: ${title}`}>
              Редактировать
            </button>
          ))}
      </header>
      {editing ? children : view}
    </section>
  );
}

const GENDER_LABELS: Record<string, string> = { male: "Мужской", female: "Женский" };
const FUNDING_LABELS: Record<string, string> = { budget: "Бюджет", contract: "Договор" };
const INCOMPLETE_LABELS: Record<string, string> = {
  loss: "потеря одного из кормильцев",
  divorce: "родители в разводе",
  single_mother: "мать-одиночка",
};

function ProfileForm({
  dossier,
  onSaved,
  onError,
}: {
  dossier: Dossier;
  onSaved: (d: Dossier) => void;
  onError: (e: string | null) => void;
}) {
  const [profile, setProfile] = useState<DossierProfile>(dossier.profile);
  const [special, setSpecial] = useState<DossierSpecial | null>(dossier.special);
  const [busy, setBusy] = useState(false);
  const dirty = JSON.stringify([profile, special]) !== JSON.stringify([dossier.profile, dossier.special]);
  useUnsavedWarning(dirty);

  const set = (field: keyof DossierProfile, value: string) =>
    setProfile((p) => ({ ...p, [field]: value === "" ? null : value }) as DossierProfile);
  const patchSpecial = (patch: Partial<DossierSpecial>) => setSpecial((s) => ({ ...(s ?? EMPTY_SPECIAL), ...patch }));
  const sameAddress = !!profile.registration_address && profile.residence_address === profile.registration_address;

  // Заполненность разделов — по сохранённому досье (а не по вводу), чтобы раздел не закрывался посреди набора.
  const saved = dossier.profile;
  const savedSpecial = dossier.special ?? EMPTY_SPECIAL;
  const has = (...keys: (keyof DossierProfile)[]) => keys.some((k) => !!saved[k]);
  const flagsOn = SPECIAL_FLAGS.filter(([f]) => f !== "has_ovz" && savedSpecial[f]).map(([, label]) => label);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    onError(null);
    try {
      onSaved(await api.put<Dossier>(`/students/${dossier.student_id}/dossier/profile`, { ...profile, special }));
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Не удалось сохранить досье");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="dossier-form" onSubmit={save}>
      <DossierBlock
        title="Основные сведения"
        subtitle="Как в документах студента."
        filled={has("birth_date", "gender", "birth_place")}
        view={
          <dl className="info-grid">
            <Info label="Дата рождения" value={saved.birth_date ? formatDateRu(saved.birth_date) : null} />
            <Info label="Пол" value={saved.gender ? GENDER_LABELS[saved.gender] : null} />
            <Info label="Место рождения" value={saved.birth_place} wide />
          </dl>
        }
      >
        <div className="dossier-grid">
          <Field label="Дата рождения">
            <input type="date" value={profile.birth_date ?? ""} onChange={(e) => set("birth_date", e.target.value)} />
          </Field>
          <Field label="Пол">
            <select value={profile.gender ?? ""} onChange={(e) => set("gender", e.target.value)}>
              <option value="">не указан</option>
              <option value="male">Мужской</option>
              <option value="female">Женский</option>
            </select>
          </Field>
          <Field label="Место рождения" wide>
            <input value={profile.birth_place ?? ""} maxLength={255} placeholder="Например: г. Москва" onChange={(e) => set("birth_place", e.target.value)} />
          </Field>
        </div>
      </DossierBlock>

      <DossierBlock
        title="Контакты студента"
        subtitle="Телефон и почта нужны, чтобы связаться при пропусках."
        filled={has("phone", "email", "messenger")}
        view={
          <dl className="info-grid">
            <Info
              label="Телефон"
              value={
                saved.phone ? (
                  telHref(saved.phone) ? (
                    <a className="link-btn" href={telHref(saved.phone)!}>
                      {saved.phone}
                    </a>
                  ) : (
                    saved.phone
                  )
                ) : null
              }
            />
            <Info
              label="E-mail"
              value={
                saved.email ? (
                  <a className="link-btn" href={`mailto:${saved.email}`}>
                    {saved.email}
                  </a>
                ) : null
              }
            />
            <Info label="Мессенджер / соцсеть" value={saved.messenger} />
          </dl>
        }
      >
        <div className="dossier-grid">
          <Field label="Телефон">
            <input type="tel" inputMode="tel" value={profile.phone ?? ""} placeholder="+7 900 000-00-00" onChange={(e) => set("phone", e.target.value)} />
          </Field>
          <Field label="E-mail">
            <input type="email" inputMode="email" value={profile.email ?? ""} placeholder="name@example.ru" onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label="Мессенджер / соцсеть">
            <input value={profile.messenger ?? ""} placeholder="Ник или ссылка" onChange={(e) => set("messenger", e.target.value)} />
          </Field>
        </div>
      </DossierBlock>

      <DossierBlock
        title="Адреса"
        filled={has("registration_address", "residence_address")}
        view={
          <dl className="info-grid">
            <Info label="Адрес регистрации" value={saved.registration_address} wide />
            <Info
              label="Адрес проживания"
              value={
                saved.residence_address && saved.residence_address === saved.registration_address
                  ? "совпадает с адресом регистрации"
                  : saved.residence_address
              }
              wide
            />
          </dl>
        }
      >
        <div className="dossier-grid">
          <Field label="Адрес регистрации" wide>
            <input value={profile.registration_address ?? ""} placeholder="Город, улица, дом, квартира" onChange={(e) => set("registration_address", e.target.value)} />
          </Field>
          <Field label="Адрес проживания" wide hint={sameAddress ? "Совпадает с адресом регистрации" : undefined}>
            <input value={profile.residence_address ?? ""} placeholder="Если отличается от адреса регистрации" onChange={(e) => set("residence_address", e.target.value)} />
          </Field>
          {profile.registration_address && !sameAddress && (
            <div className="dossier-field dossier-field--wide">
              <button type="button" className="link-btn dossier-inline-action" onClick={() => set("residence_address", profile.registration_address ?? "")}>
                Проживает по адресу регистрации — скопировать
              </button>
            </div>
          )}
        </div>
      </DossierBlock>

      <DossierBlock
        title="Обучение"
        subtitle="Для личной карточки обучающегося и отчёта куратора."
        filled={has("funding", "enrollment_order", "previous_education", "additional_education")}
        view={
          <dl className="info-grid">
            <Info label="Финансирование" value={saved.funding ? FUNDING_LABELS[saved.funding] : null} />
            <Info label="Приказ о зачислении" value={saved.enrollment_order} />
            <Info label="Образование до поступления" value={saved.previous_education} wide />
            <Info label="Дополнительное образование" value={saved.additional_education} wide />
          </dl>
        }
      >
        <div className="dossier-grid">
          <Field label="Финансирование">
            <select value={profile.funding ?? ""} onChange={(e) => set("funding", e.target.value)}>
              <option value="">не указано</option>
              <option value="budget">Бюджет</option>
              <option value="contract">Договор</option>
            </select>
          </Field>
          <Field label="Приказ о зачислении (номер и дата)">
            <input value={profile.enrollment_order ?? ""} maxLength={128} placeholder="№ 15 от 25.08.2026" onChange={(e) => set("enrollment_order", e.target.value)} />
          </Field>
          <Field label="Образование до поступления (класс, год, школа)" wide>
            <input value={profile.previous_education ?? ""} maxLength={500} placeholder="9 классов, 2026, школа № 1" onChange={(e) => set("previous_education", e.target.value)} />
          </Field>
          <Field label="Дополнительное образование (кружки, секции)" wide hint="По этому полю считаются «дети в кружках» в отчёте куратора.">
            <TextArea expandTitle="Дополнительное образование" rows={2} value={profile.additional_education ?? ""} maxLength={1000} onChange={(e) => set("additional_education", e.target.value)} />
          </Field>
        </div>
      </DossierBlock>

      {!dossier.special_available ? (
        <section className="dossier-section">
          <header className="dossier-section__head">
            <h4>Социальный статус и здоровье</h4>
          </header>
          <p className="hint">Особые данные недоступны: на сервере не задан ключ шифрования (DOSSIER_ENCRYPTION_KEY).</p>
        </section>
      ) : (
        <>
          <DossierBlock
            title="Социальный статус"
            subtitle="Особые категории персональных данных: хранятся зашифрованно, каждый просмотр досье записывается в журнал."
            isPrivate
            filled={flagsOn.length > 0 || !!savedSpecial.incomplete_family || !!savedSpecial.scholarship}
            view={
              <dl className="info-grid">
                <Info
                  label="Признаки"
                  wide
                  value={
                    flagsOn.length > 0 ? (
                      <span className="info-chips">
                        {flagsOn.map((l) => (
                          <span key={l} className="info-chip">
                            {l}
                          </span>
                        ))}
                      </span>
                    ) : (
                      "нет"
                    )
                  }
                />
                <Info label="Неполная семья" value={savedSpecial.incomplete_family ? INCOMPLETE_LABELS[savedSpecial.incomplete_family] : "нет"} />
                <Info label="Стипендия / соцвыплаты" value={savedSpecial.scholarship} />
              </dl>
            }
          >
            <div className="toggle-grid" role="group" aria-label="Признаки семьи и учёта">
              {SPECIAL_FLAGS.filter(([f]) => f !== "has_ovz").map(([field, label]) => (
                <label key={field} className={`toggle-tile${special?.[field] ? " is-on" : ""}`}>
                  <input type="checkbox" checked={Boolean(special?.[field])} onChange={(e) => patchSpecial({ [field]: e.target.checked })} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            <div className="dossier-grid">
              <Field label="Неполная семья">
                <select
                  value={special?.incomplete_family ?? ""}
                  onChange={(e) => patchSpecial({ incomplete_family: (e.target.value || null) as DossierSpecial["incomplete_family"] })}
                >
                  <option value="">нет</option>
                  <option value="loss">потеря одного из кормильцев</option>
                  <option value="divorce">родители в разводе</option>
                  <option value="single_mother">мать-одиночка</option>
                </select>
              </Field>
              <Field label="Стипендия / соцвыплаты">
                <input value={special?.scholarship ?? ""} placeholder="Например: социальная стипендия" onChange={(e) => patchSpecial({ scholarship: e.target.value || null })} />
              </Field>
            </div>
          </DossierBlock>

          <DossierBlock
            title="Здоровье"
            subtitle="Только то, что нужно знать куратору; диагнозы не записываются."
            isPrivate
            filled={savedSpecial.has_ovz || !!savedSpecial.disability_group || !!savedSpecial.health_note}
            view={
              <dl className="info-grid">
                <Info label="ОВЗ" value={savedSpecial.has_ovz ? "да" : "нет"} />
                <Info label="Группа инвалидности" value={savedSpecial.disability_group} />
                <Info label="Что важно знать куратору" value={savedSpecial.health_note} wide />
              </dl>
            }
          >
            <div className="toggle-grid">
              <label className={`toggle-tile${special?.has_ovz ? " is-on" : ""}`}>
                <input type="checkbox" checked={Boolean(special?.has_ovz)} onChange={(e) => patchSpecial({ has_ovz: e.target.checked })} />
                <span>ОВЗ</span>
              </label>
            </div>
            <div className="dossier-grid">
              <Field label="Группа инвалидности">
                <input value={special?.disability_group ?? ""} placeholder="Например: 3 группа" onChange={(e) => patchSpecial({ disability_group: e.target.value || null })} />
              </Field>
              <Field label="Здоровье: что важно знать куратору" wide>
                <TextArea expandTitle="Здоровье: что важно знать куратору" rows={3} value={special?.health_note ?? ""} onChange={(e) => patchSpecial({ health_note: e.target.value || null })} />
              </Field>
            </div>
          </DossierBlock>
        </>
      )}

      {/* Панель сохранения — только когда есть что сохранять: в режиме просмотра она не нужна. */}
      {dirty && (
        <div className="dossier-savebar is-dirty">
          <span className="dossier-savebar__state" aria-live="polite">
            Есть несохранённые изменения
          </span>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Сохранение…" : "Сохранить досье"}
          </button>
        </div>
      )}
    </form>
  );
}

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

function Guardians({
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

function Notes({
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
  const base = `/students/${studentId}/dossier/notes`;

  function protocol(n: Pick<DossierNote, "id" | "occurred_on">) {
    downloadProtocol(studentId, n).catch((err) => onError(err instanceof ApiError ? err.message : "Не удалось сформировать протокол"));
  }

  async function setDone(id: number, done: boolean) {
    onError(null);
    try {
      await api.put(`${base}/${id}/follow-up`, { done });
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Не удалось изменить заметку");
    }
  }

  async function remove(id: number) {
    if (!(await dialogs.confirm("Удалить заметку?", { confirmLabel: "Удалить", danger: true }))) return;
    onError(null);
    try {
      await api.delete(`${base}/${id}`);
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Не удалось удалить заметку");
    }
  }

  return (
    <div className="dossier-form">
      <section className="dossier-section">
        <header className="dossier-section__head">
          <h4>Новая запись</h4>
          <p>Беседа, звонок, вызов родителей, договорённость — по ним можно сразу получить протокол беседы в Word.</p>
        </header>
        <NoteForm
          studentId={studentId}
          onSaved={(_note, withProtocol) => {
            onChanged();
            toast(withProtocol ? "Запись сохранена, протокол скачивается" : "Запись сохранена");
          }}
        />
      </section>

      <section className="dossier-section">
        <header className="dossier-section__head">
          <h4>
            Записи <span className="tabbar__badge">{dossier.notes.length}</span>
          </h4>
        </header>
        {dossier.notes.length === 0 ? (
          <p className="hint">Заметок пока нет.</p>
        ) : (
          <div className="note-list">
            {dossier.notes.map((n) => (
              <article key={n.id} className="note-card">
                <header className="note-card__head">
                  <span className="note-card__kind">{NOTE_KINDS[n.kind] ?? n.kind}</span>
                  <time>{n.occurred_on ? formatDateRu(n.occurred_on) : formatServerDateTimeFull(n.created_at)}</time>
                  <span className="hint">{n.author_name ?? "—"}</span>
                </header>
                <p className="note-card__text">{n.text}</p>
                {(n.goal || n.participants || n.result) && (
                  <dl className="note-card__details">
                    {n.goal && (
                      <div>
                        <dt>Цель</dt>
                        <dd>{n.goal}</dd>
                      </div>
                    )}
                    {n.participants && (
                      <div>
                        <dt>Присутствовали</dt>
                        <dd>{n.participants.split("\n").join("; ")}</dd>
                      </div>
                    )}
                    {n.result && (
                      <div>
                        <dt>Итог</dt>
                        <dd>{n.result}</dd>
                      </div>
                    )}
                  </dl>
                )}
                {n.follow_up_on && (
                  <div className={`note-card__follow${!n.follow_up_done && n.follow_up_on < todayIso() ? " is-overdue" : ""}`}>
                    {n.follow_up_done ? (
                      <span>Вернуться к вопросу: выполнено</span>
                    ) : (
                      <span>
                        Вернуться к вопросу до {formatDateRu(n.follow_up_on)}
                        {n.follow_up_on < todayIso() ? " (просрочено)" : ""}
                      </span>
                    )}
                    <button type="button" className="link-btn" onClick={() => setDone(n.id, !n.follow_up_done)}>
                      {n.follow_up_done ? "Вернуть в работу" : "Выполнено"}
                    </button>
                  </div>
                )}
                {(PROTOCOL_KINDS.includes(n.kind) || n.can_delete) && (
                  <footer className="note-card__actions">
                    {PROTOCOL_KINDS.includes(n.kind) && (
                      <button
                        type="button"
                        className="btn-secondary"
                        onClick={() => protocol(n)}
                        title="Протокол беседы по образцу колледжа — можно распечатать или править в Word"
                      >
                        Протокол беседы (Word)
                      </button>
                    )}
                    {n.can_delete && (
                      <button type="button" className="link-btn danger-link" onClick={() => remove(n.id)}>
                        Удалить
                      </button>
                    )}
                  </footer>
                )}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function AccessLog({ studentId }: { studentId: number }) {
  const [rows, setRows] = useState<DossierAccessEntry[] | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    api
      .get<DossierAccessEntry[]>(`/students/${studentId}/dossier/access-log`)
      .then(setRows)
      .catch(() => setRows([]));
  }, [open, studentId]);

  return (
    <>
      <h3 className="student-card__section">Журнал просмотров досье</h3>
      {!open ? (
        <button className="link-btn" onClick={() => setOpen(true)}>
          Показать
        </button>
      ) : rows === null ? (
        <p className="hint">Загрузка…</p>
      ) : rows.length === 0 ? (
        <p className="hint">Просмотров нет.</p>
      ) : (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Когда</th>
              <th>Кто</th>
              <th>Особые поля</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td data-label="Когда">{formatServerDateTimeFull(r.created_at)}</td>
                <td data-label="Кто">{r.user_name}</td>
                <td data-label="Особые поля">{r.included_special ? "показаны" : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
