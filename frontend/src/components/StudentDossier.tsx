import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { api, ApiError } from "../api/client";
import { formatDateRu, formatServerDateTimeFull, todayIso } from "../utils/date";
import type { Dossier, DossierAccessEntry, DossierProfile, DossierSpecial } from "../api/types";

const NOTE_KINDS: Record<string, string> = {
  conversation: "Беседа",
  call: "Звонок",
  parent_invited: "Вызов родителей",
  prevention_council: "Совет профилактики",
  home_visit: "Визит домой",
  incident: "Инцидент",
  agreement: "Договорённость",
  other: "Другое",
};

const EMPTY_SPECIAL: DossierSpecial = {
  is_orphan: false,
  under_guardianship: false,
  disability_group: null,
  has_ovz: false,
  large_family: false,
  low_income: false,
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
  | "pdn_kdn"
  | "internal_record";

const SPECIAL_FLAGS: [SpecialFlag, string][] = [
  ["is_orphan", "Сирота"],
  ["under_guardianship", "Под опекой"],
  ["has_ovz", "ОВЗ"],
  ["large_family", "Многодетная семья"],
  ["low_income", "Малоимущая семья"],
  ["pdn_kdn", "Учёт ПДН/КДН"],
  ["internal_record", "Внутренний учёт"],
];

// Досье студента: контакты, представители, особые данные (шифруются на сервере),
// заметки куратора. Журнал просмотров — только администратору/тьютору.
export default function StudentDossier({ studentId, isAdmin }: { studentId: number; isAdmin: boolean }) {
  const [dossier, setDossier] = useState<Dossier | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .get<Dossier>(`/students/${studentId}/dossier`)
      .then((d) => {
        setDossier(d);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Не удалось загрузить досье"));
  }, [studentId]);

  useEffect(load, [load]);

  if (error && !dossier) return <div className="error-text">{error}</div>;
  if (!dossier) return <p className="hint">Загрузка досье…</p>;

  return (
    <div>
      {error && <div className="error-text">{error}</div>}
      {notice && <div className="day-status submitted">{notice}</div>}
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
      <Guardians dossier={dossier} studentId={studentId} onChanged={load} onError={setError} />
      <Notes dossier={dossier} studentId={studentId} onChanged={load} onError={setError} />
      {isAdmin && <AccessLog studentId={studentId} />}
    </div>
  );
}

// Поле с видимой подписью: плейсхолдер исчезает при вводе и не читается скринридером как название.
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="form-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

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

  const set = (field: keyof DossierProfile, value: string) =>
    setProfile((p) => ({ ...p, [field]: value === "" ? null : value }) as DossierProfile);
  const patchSpecial = (patch: Partial<DossierSpecial>) => setSpecial((s) => ({ ...(s ?? EMPTY_SPECIAL), ...patch }));

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
    <form className="add-block" onSubmit={save}>
      <p className="add-block__title">Основное и контакты</p>
      <div className="inline-form form-fields">
        <Field label="Дата рождения">
          <input type="date" value={profile.birth_date ?? ""} onChange={(e) => set("birth_date", e.target.value)} />
        </Field>
        <Field label="Финансирование">
          <select value={profile.funding ?? ""} onChange={(e) => set("funding", e.target.value)}>
            <option value="">не указано</option>
            <option value="budget">Бюджет</option>
            <option value="contract">Договор</option>
          </select>
        </Field>
        <Field label="Телефон">
          <input value={profile.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />
        </Field>
        <Field label="E-mail">
          <input type="email" value={profile.email ?? ""} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Мессенджер / соцсеть">
          <input value={profile.messenger ?? ""} onChange={(e) => set("messenger", e.target.value)} />
        </Field>
      </div>
      <div className="inline-form form-fields">
        <Field label="Адрес регистрации">
          <input value={profile.registration_address ?? ""} onChange={(e) => set("registration_address", e.target.value)} />
        </Field>
        <Field label="Адрес проживания">
          <input value={profile.residence_address ?? ""} onChange={(e) => set("residence_address", e.target.value)} />
        </Field>
      </div>
      <div className="inline-form form-fields">
        <Field label="Дополнительное образование (кружки, секции)">
          <input
            value={profile.additional_education ?? ""}
            maxLength={1000}
            onChange={(e) => set("additional_education", e.target.value)}
          />
        </Field>
      </div>

      <p className="add-block__title">Социальный статус и здоровье</p>
      {!dossier.special_available ? (
        <p className="hint">Особые данные недоступны: на сервере не задан ключ шифрования (DOSSIER_ENCRYPTION_KEY).</p>
      ) : (
        <>
          <p className="hint">
            Особые категории персональных данных: хранятся в зашифрованном виде, каждый просмотр досье журналируется.
          </p>
          <div className="inline-form">
            {SPECIAL_FLAGS.map(([field, label]) => (
              <label key={field}>
                <input
                  type="checkbox"
                  checked={Boolean(special?.[field])}
                  onChange={(e) => patchSpecial({ [field]: e.target.checked })}
                />{" "}
                {label}
              </label>
            ))}
          </div>
          <div className="inline-form form-fields">
            <Field label="Группа инвалидности">
              <input
                value={special?.disability_group ?? ""}
                onChange={(e) => patchSpecial({ disability_group: e.target.value || null })}
              />
            </Field>
            <Field label="Стипендия / соцвыплаты">
              <input
                value={special?.scholarship ?? ""}
                onChange={(e) => patchSpecial({ scholarship: e.target.value || null })}
              />
            </Field>
          </div>
          <Field label="Здоровье: что важно знать куратору">
            <textarea
              rows={2}
              style={{ width: "100%" }}
              value={special?.health_note ?? ""}
              onChange={(e) => patchSpecial({ health_note: e.target.value || null })}
            />
          </Field>
        </>
      )}
      <p>
        <button type="submit" disabled={busy}>
          Сохранить досье
        </button>
      </p>
    </form>
  );
}

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
  const [name, setName] = useState("");
  const [relation, setRelation] = useState("");
  const [phone, setPhone] = useState("");
  const [primary, setPrimary] = useState(false);
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
      () => api.post(base, { full_name: name, relation, phone: phone || null, is_primary: primary }),
      "Не удалось добавить представителя"
    );
    if (!ok) return;
    setName("");
    setRelation("");
    setPhone("");
    setPrimary(false);
  }

  return (
    <>
      <h3 className="student-card__section">Законные представители</h3>
      {dossier.guardians.length === 0 ? (
        <p className="hint">Представители не указаны.</p>
      ) : (
        <table className="dash-table">
          <thead>
            <tr>
              <th>ФИО</th>
              <th>Кем приходится</th>
              <th>Телефон</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {dossier.guardians.map((g) => (
              <tr key={g.id}>
                <td data-label="ФИО">
                  {g.full_name} {g.is_primary && <span className="locked-badge">основной</span>}
                </td>
                <td data-label="Кем приходится">{g.relation}</td>
                <td data-label="Телефон">{g.phone ?? "—"}</td>
                <td>
                  <button
                    className="link-btn"
                    onClick={() => {
                      if (window.confirm(`Удалить представителя «${g.full_name}»?`))
                        run(() => api.delete(`${base}/${g.id}`), "Не удалось удалить");
                    }}
                  >
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form className="add-block" onSubmit={add}>
        <div className="inline-form">
          <input placeholder="ФИО" value={name} onChange={(e) => setName(e.target.value)} required />
          <input
            placeholder="Кем приходится (мать, отец, опекун…)"
            value={relation}
            onChange={(e) => setRelation(e.target.value)}
            required
          />
          <input placeholder="Телефон" value={phone} onChange={(e) => setPhone(e.target.value)} />
          <label>
            <input type="checkbox" checked={primary} onChange={(e) => setPrimary(e.target.checked)} /> Основной
          </label>
          <button type="submit">Добавить</button>
        </div>
      </form>
    </>
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
  const [kind, setKind] = useState("conversation");
  const [text, setText] = useState("");
  const [occurredOn, setOccurredOn] = useState(todayIso());
  const [followUpOn, setFollowUpOn] = useState("");
  const base = `/students/${studentId}/dossier/notes`;

  async function add(e: FormEvent) {
    e.preventDefault();
    onError(null);
    try {
      await api.post(base, { kind, text, occurred_on: occurredOn || null, ...(followUpOn ? { follow_up_on: followUpOn } : {}) });
      setText("");
      setFollowUpOn("");
      setOccurredOn(todayIso());
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Не удалось добавить заметку");
    }
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
    if (!window.confirm("Удалить заметку?")) return;
    onError(null);
    try {
      await api.delete(`${base}/${id}`);
      onChanged();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Не удалось удалить заметку");
    }
  }

  return (
    <>
      <h3 className="student-card__section">Индивидуальная работа и заметки</h3>
      <form className="add-block" onSubmit={add}>
        <div className="inline-form">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            {Object.entries(NOTE_KINDS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <label>
            Дата{" "}
            <input type="date" value={occurredOn} max={todayIso()} onChange={(e) => setOccurredOn(e.target.value)} />
          </label>
          <input
            placeholder="Что произошло, о чём договорились"
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
            style={{ flex: 1, minWidth: 200 }}
          />
          <label title="Когда напомнить вернуться к вопросу (необязательно)">
            Вернуться к вопросу{" "}
            <input type="date" value={followUpOn} min={occurredOn || todayIso()} onChange={(e) => setFollowUpOn(e.target.value)} />
          </label>
          <button type="submit">Добавить</button>
        </div>
      </form>
      {dossier.notes.length === 0 ? (
        <p className="hint">Заметок пока нет.</p>
      ) : (
        <table className="dash-table">
          <thead>
            <tr>
              <th>Дата</th>
              <th>Тип</th>
              <th>Заметка</th>
              <th>Автор</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {dossier.notes.map((n) => (
              <tr key={n.id}>
                <td data-label="Дата">{n.occurred_on ? formatDateRu(n.occurred_on) : formatServerDateTimeFull(n.created_at)}</td>
                <td data-label="Тип">{NOTE_KINDS[n.kind] ?? n.kind}</td>
                <td data-label="Заметка" style={{ whiteSpace: "pre-wrap" }}>
                  {n.text}
                  {n.follow_up_on && (
                    <div className="hint">
                      {n.follow_up_done ? (
                        <>Вернуться к вопросу: выполнено </>
                      ) : (
                        <b className={n.follow_up_on < todayIso() ? "error-text" : undefined}>
                          Вернуться к вопросу до {formatDateRu(n.follow_up_on)}
                          {n.follow_up_on < todayIso() ? " (просрочено)" : ""}{" "}
                        </b>
                      )}
                      <button className="link-btn" onClick={() => setDone(n.id, !n.follow_up_done)}>
                        {n.follow_up_done ? "Вернуть в работу" : "Выполнено"}
                      </button>
                    </div>
                  )}
                </td>
                <td data-label="Автор">{n.author_name ?? "—"}</td>
                <td>
                  {n.can_delete && (
                    <button className="link-btn" onClick={() => remove(n.id)}>
                      Удалить
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
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
