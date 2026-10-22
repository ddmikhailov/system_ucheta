import { useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "../../api/client";
import { formatDateRu } from "../../utils/date";
import { telHref } from "../../utils/phone";
import type { Dossier, DossierProfile, DossierSpecial } from "../../api/types";
import { useUnsavedWarning } from "../../hooks/useUnsavedWarning";
import TextArea from "../TextArea";
import { DossierBlock, Field, Info } from "./shared";

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

const GENDER_LABELS: Record<string, string> = { male: "Мужской", female: "Женский" };
const FUNDING_LABELS: Record<string, string> = { budget: "Бюджет", contract: "Договор" };
const INCOMPLETE_LABELS: Record<string, string> = {
  loss: "потеря одного из кормильцев",
  divorce: "родители в разводе",
  single_mother: "мать-одиночка",
};

export function ProfileForm({
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
