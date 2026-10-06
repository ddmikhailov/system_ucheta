export interface MeGroupInfo {
  id: number;
  code: string;
  course: number;
}

export interface DossierProfile {
  birth_date: string | null;
  gender: "male" | "female" | null;
  funding: "budget" | "contract" | null;
  phone: string | null;
  email: string | null;
  messenger: string | null;
  registration_address: string | null;
  residence_address: string | null;
  additional_education: string | null;
  birth_place: string | null;
  previous_education: string | null;
  enrollment_order: string | null;
}

export interface DossierSpecial {
  is_orphan: boolean;
  under_guardianship: boolean;
  disability_group: string | null;
  has_ovz: boolean;
  large_family: boolean;
  incomplete_family: "loss" | "divorce" | "single_mother" | null;
  low_income: boolean;
  dysfunctional_family: boolean;
  parent_disabled: boolean;
  pdn_kdn: boolean;
  internal_record: boolean;
  scholarship: string | null;
  health_note: string | null;
}

export interface DossierGuardian {
  id: number;
  full_name: string;
  relation: string;
  phone: string | null;
  is_primary: boolean;
}

export interface DossierNote {
  id: number;
  kind: string;
  text: string;
  author_id: number | null;
  author_name: string | null;
  created_at: string;
  can_delete: boolean;
  occurred_on: string | null;
  follow_up_on: string | null;
  follow_up_done: boolean;
  goal: string | null;
  participants: string | null;
  result: string | null;
}

export interface IndividualWorkRow {
  student_id: number;
  full_name: string;
  risk_streak: number;
  is_risk: boolean;
  attendance_percent: number | null;
  work_count: number;
  last_work_on: string | null;
  next_follow_up_on: string | null;
  follow_up_overdue: boolean;
  needs_attention: boolean;
}

export interface IndividualWorkGroup {
  group_id: number;
  group_code: string;
  no_work_days: number;
  rows: IndividualWorkRow[];
}

export interface MyDayGroup {
  id: number;
  code: string;
  course: number;
  today_status: "submitted" | "pending" | "no_study_day";
  is_on_time: boolean | null;
  missed_dates: string[];
  missed_total: number;
  /** Последние три недели по дням, от старых к новым. */
  rhythm?: MyDayRhythmDay[];
}

export interface MyDayRhythmDay {
  date: string;
  kind: "off" | "missing" | "absent" | "ok";
  absent: number;
}

export interface MyDayTask {
  assignment_id: number;
  title: string;
  group_code: string;
  due_date: string;
  kind: "overdue" | "returned" | "due_soon";
  status: string;
  days_left: number;
}

export interface MyDayAttention {
  student_id: number;
  full_name: string;
  group_code: string;
  risk_streak: number;
  attendance_percent: number | null;
  needs_work: boolean;
  last_work_on: string | null;
  follow_up_on: string | null;
  follow_up_overdue: boolean;
  follow_up_today: boolean;
}

export interface MyDayBirthday {
  student_id: number;
  full_name: string;
  group_code: string;
  date: string;
  days_until: number;
  turns: number;
}

export interface MyDay {
  today: string;
  leads_groups: boolean;
  groups: MyDayGroup[];
  tasks: MyDayTask[];
  attention: MyDayAttention[];
  attention_total: number;
  no_work_days: number;
  birthdays: MyDayBirthday[];
  review_waiting: { count: number; oldest_submitted_at: string | null } | null;
}

export interface AbsenceMessage {
  days: number;
  absences: { date: string; code: string; name: string }[];
  text: string;
}

export interface Dossier {
  student_id: number;
  profile: DossierProfile;
  special: DossierSpecial | null;
  special_available: boolean;
  guardians: DossierGuardian[];
  notes: DossierNote[];
}

export interface DossierAccessEntry {
  user_id: number;
  user_name: string;
  included_special: boolean;
  created_at: string;
}

export interface MeResponse {
  id: number;
  full_name: string;
  role: string;
  display_title: string | null;
  department_name: string | null;
  groups: MeGroupInfo[];
  dept_head_name: string | null;
  must_change_password: boolean;
  // Заполнено только в ответе POST /auth/change-password.
  access_token?: string | null;
}

export interface RosterEntry {
  student_id: number;
  full_name: string;
  mark_code: string | null;
  mark_name: string | null;
  comment: string | null;
  basis_reference: string | null;
  is_draft_suggestion: boolean;
  is_locked: boolean;
  risk_streak: number;
  attendance_percent: number | null;
  is_risk: boolean;
  last_edited_by: string | null;
  last_edited_at: string | null;
}

export interface RosterResponse {
  study_group_id: number;
  date: string;
  is_submitted: boolean;
  submitted_at: string | null;
  is_on_time: boolean | null;
  first_period: number | null;
  entries: RosterEntry[];
  /** Кто сдал день. */
  submitted_by_name?: string | null;
  /** Правка этого дня текущим пользователем уходит на проверку зав. отделением. */
  edit_requires_review?: boolean;
  pending_change?: AttendanceChange | null;
  last_change?: AttendanceChange | null;
}

/** Что меняется у студента в запросе на исправление: код было → станет (null — присутствовал). */
export interface MarkChange {
  student_id: number;
  full_name: string;
  from_code: string | null;
  to_code: string | null;
  details_changed: boolean;
}

/** Исправление прошлого сданного дня куратором — на проверке у зав. отделением. */
export interface AttendanceChange {
  id: number;
  study_group_id: number;
  group_code: string;
  date: string;
  requested_by_id: number;
  requested_by_name: string;
  created_at: string;
  reason: string;
  status: "pending" | "approved" | "rejected" | "cancelled";
  reviewed_by_name: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
  first_period: number | null;
  changes: MarkChange[];
}

export interface GroupSummary {
  id: number;
  code: string;
  course: number;
  is_submitted_today: boolean;
  students_count: number;
  risk_count: number;
  role_type: "curator" | "deputy" | null;
}

export interface MonthDayStatus {
  date: string;
  day_type: string;
  is_submitted: boolean | null;
  is_on_time: boolean | null;
}

export interface MarkCodeOption {
  id: number;
  code: string;
  name: string;
  counts_as_present: boolean;
  is_excused: boolean;
  requires_document: boolean;
  is_active: boolean;
}

export interface DayOverviewRow {
  study_group_id: number;
  code: string;
  course: number;
  responsible_name: string | null;
  in_list: number | null;
  present: number | null;
  late: number | null;
  absent_excused: number | null;
  absent_unexcused: number | null;
  percent: number | null;
  is_submitted: boolean;
  is_on_time: boolean | null;
}

export interface DynamicsPoint {
  date: string;
  percent: number | null;
  in_list: number | null;
  present: number | null;
}

export interface RiskStudentRow {
  student_id: number;
  full_name: string;
  study_group_id: number;
  group_code: string;
  streak: number;
  attendance_percent: number;
  days: number;
  absent: number;
}

export interface CuratorDisciplineRow {
  study_group_id: number;
  code: string;
  course: number;
  responsible_name: string | null;
  on_time: number;
  late: number;
  missed: number;
  total_study_days: number;
}

// --- Admin ---

export interface DepartmentAdmin {
  id: number;
  name: string;
  is_active: boolean;
}

export interface StudyGroupAdmin {
  id: number;
  code: string;
  course: number;
  department_id: number;
  study_form: string | null;
  is_active: boolean;
  curator_name: string | null;
  curator_assignment_id: number | null;
  deputy_name: string | null;
  deputy_assignment_id: number | null;
}

export interface DeleteResult {
  deleted: boolean;
  anonymized: boolean;
  detail: string;
}

export interface StudentAdmin {
  id: number;
  full_name: string;
  last_name: string;
  first_name: string;
  middle_name: string | null;
  study_group_id: number;
  status: string;
  enrolled_at: string;
  left_at: string | null;
}

export interface MarkCodeAdmin {
  id: number;
  code: string;
  name: string;
  counts_as_present: boolean;
  is_excused: boolean;
  requires_document: boolean;
  is_active: boolean;
}

export interface UserAdmin {
  id: number;
  username: string;
  full_name: string;
  role: string;
  display_title: string | null;
  department_id: number | null;
  is_active: boolean;
  has_password: boolean;
  must_change_password: boolean;
  is_locked: boolean;
}

export interface SetPasswordResult {
  username: string;
  password: string;
}


export interface CalendarDay {
  date: string;
  day_type: string;
}

export interface GroupCalendarOverride {
  study_group_id: number;
  date: string;
  day_type: string;
}

export interface NotificationItem {
  id: number;
  kind: string;
  message: string;
  entity_type: string | null;
  entity_id: string | null;
  created_at: string;
  read_at: string | null;
}

export interface GroupDeletionPreview {
  code: string;
  students: number;
  attendance_marks: number;
  day_submissions: number;
  absence_periods: number;
  curator_assignments: number;
}

export interface StudentCardGroup {
  id: number;
  code: string;
  course: number;
  study_form: string | null;
  is_active: boolean;
  department_id: number;
  department_name: string;
}

export interface StudentCardMembership {
  group_id: number;
  group_code: string;
  start_date: string;
  end_date: string | null;
}

export interface StudentCardMark {
  date: string;
  code: string;
  name: string;
  comment: string | null;
  basis_reference: string | null;
}

export interface StudentCardStats {
  date_from: string;
  date_to: string;
  in_list: number;
  present: number;
  absent_total: number;
  absent_excused: number;
  absent_unexcused: number;
  late: number;
  percent: number;
  by_code: Record<string, number>;
}

export interface StudentCard {
  id: number;
  full_name: string;
  last_name: string;
  first_name: string;
  middle_name: string | null;
  status: string;
  enrolled_at: string;
  left_at: string | null;
  group: StudentCardGroup;
  curator_name: string | null;
  deputy_name: string | null;
  group_history: StudentCardMembership[];
  stats: StudentCardStats;
  recent_marks: StudentCardMark[];
}

export interface SummaryCode {
  code: string;
  name: string;
  counts_as_present: boolean;
}

export interface SummaryLine {
  date: string | null;
  department: string;
  slice_name: string;
  groups: number;
  groups_submitted: number;
  headcount: number;
  counted: number;
  present: number;
  absent: number;
  percent: number | null;
  by_code: Record<string, number>;
}

export interface SummaryGroupDay {
  date: string;
  department: string;
  group_id: number;
  group_code: string;
  course: number;
  headcount: number;
  is_submitted: boolean;
  present: number | null;
  absent: number | null;
  percent: number | null;
  first_period: number | null;
  by_code: Record<string, number>;
}

export interface AttendanceSummary {
  codes: SummaryCode[];
  daily: SummaryLine[];
  period: SummaryLine[];
  group_days: SummaryGroupDay[];
}

export interface StudentDayAttendance {
  date: string;
  day_type: string;
  status: string;
  group_code: string | null;
  mark_code: string | null;
  mark_name: string | null;
  counts_as_present: boolean | null;
  is_excused: boolean | null;
  comment: string | null;
  basis_reference: string | null;
}

export interface StudentMonthSummary {
  study_days: number;
  present: number;
  absent: number;
  absent_excused: number;
  absent_unexcused: number;
  late: number;
  not_submitted: number;
  percent: number | null;
  by_code: Record<string, number>;
}

export interface StudentMonthAttendance {
  student_id: number;
  year: number;
  month: number;
  first_month: string;
  summary: StudentMonthSummary;
  days: StudentDayAttendance[];
}

export interface CuratorDayRow {
  date: string;
  status: string;
  submitted_at_local: string | null;
  submitted_by: string | null;
  first_period: number | null;
  days_late: number | null;
}

export interface CuratorDaysRead {
  study_group_id: number;
  group_code: string;
  responsible_name: string | null;
  date_from: string;
  date_to: string;
  on_time: number;
  late: number;
  missed: number;
  total_study_days: number;
  average_on_time_submission: string | null;
  days: CuratorDayRow[];
}

export type TaskFieldType = "text" | "number" | "date" | "bool" | "select" | "multiselect" | "link";

export interface TaskField {
  key?: string | null;
  label: string;
  type: TaskFieldType;
  required: boolean;
  options: string[];
  // Поле досье, которое наполняется принятыми ответами.
  dossier_field?: string | null;
}

export interface TaskTemplate {
  id: number;
  name: string;
  author_name: string | null;
  created_at: string;
  can_manage: boolean;
  title: string;
  description: string | null;
  collect_mode: string;
  reviewer_rule: string;
  fields: TaskField[];
  scope: TaskScope;
  repeat: "" | "monthly" | "semester";
  repeat_day: number;
  due_offset_days: number;
  next_run: string | null;
  last_run_date: string | null;
  last_error: string | null;
}

export interface DossierTarget {
  key: string;
  label: string;
  types: TaskFieldType[];
}

export interface TaskScope {
  all_groups: boolean;
  department_ids: number[];
  courses: number[];
  group_ids: number[];
  exclude_group_ids: number[];
}

export interface TaskProgress {
  total: number;
  new: number;
  in_progress: number;
  submitted: number;
  returned: number;
  accepted: number;
  overdue: number;
}

export interface TaskListRow {
  id: number;
  title: string;
  collect_mode: string;
  reviewer_rule: string;
  due_date: string;
  is_closed: boolean;
  author_id?: number | null;
  author_name: string | null;
  progress: TaskProgress;
  step_no: number;
  step_total: number | null;
}

export interface TaskAssignmentSummary {
  id: number;
  study_group_id: number;
  group_code: string;
  course: number;
  department_name: string;
  status: string;
  is_overdue: boolean;
  submitted_at: string | null;
  reviewed_at: string | null;
  reviewed_by_name: string | null;
  /** Шаг цепочки ещё закрыт для группы. */
  is_locked?: boolean;
}

export interface TaskDetail {
  id: number;
  title: string;
  description: string | null;
  collect_mode: string;
  reviewer_rule: string;
  due_date: string;
  is_closed: boolean;
  author_id: number | null;
  author_name: string | null;
  fields: TaskField[];
  scope: TaskScope;
  can_manage: boolean;
  progress: TaskProgress;
  assignments: TaskAssignmentSummary[];
  step_no: number;
  unlock_on: "submitted" | "accepted" | null;
  steps: { id: number; title: string; step_no: number; due_date: string }[];
}

export interface MyAssignmentRow {
  id: number;
  task_id: number;
  title: string;
  collect_mode: string;
  group_code: string;
  due_date: string;
  status: string;
  is_overdue: boolean;
  is_closed: boolean;
  is_locked: boolean;
  step_no: number;
  step_total: number | null;
  /** Заполнено и всего: поля (ответ по группе) или студенты (остальные режимы). */
  filled: number;
  total: number;
  /** Замечание проверяющего — только пока назначение возвращено. */
  review_comment: string | null;
}

export interface TaskRowRead {
  student_id: number;
  student_name: string;
  is_included: boolean;
  values: Record<string, unknown>;
  /** Строка ещё не сохранялась, значения подставлены из досье. */
  from_dossier?: boolean;
}

export interface TaskCommentRead {
  id: number;
  student_id: number | null;
  author_name: string | null;
  text: string;
  created_at: string;
}

export interface TaskHistoryEvent {
  kind: "submitted" | "accepted" | "returned" | "auto_accepted";
  user_name: string | null;
  at: string;
  step: number | null;
}

export interface AssignmentDetail {
  id: number;
  task_id: number;
  title: string;
  description: string | null;
  collect_mode: string;
  reviewer_rule: string;
  due_date: string;
  is_closed: boolean;
  fields: (TaskField & { key: string })[];
  study_group_id: number;
  group_code: string;
  status: string;
  is_overdue: boolean;
  group_values: Record<string, unknown>;
  rows: TaskRowRead[];
  comments: TaskCommentRead[];
  review_comment: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  reviewed_by_name: string | null;
  history: TaskHistoryEvent[];
  review_step: number;
  review_steps: number;
  can_edit: boolean;
  can_submit: boolean;
  can_review: boolean;
  is_locked: boolean;
  locked_reason: string | null;
  step_no: number;
  step_total: number | null;
}

export interface ReviewQueueRow {
  id: number;
  task_id: number;
  title: string;
  group_code: string;
  department_name: string;
  due_date: string;
  submitted_at: string | null;
  is_overdue: boolean;
}

export interface RemindResult {
  sent: number;
  skipped: number;
}

export interface TaskSummaryField {
  key: string;
  label: string;
  type: TaskFieldType;
  filled: number;
  counts: { label: string; count: number }[];
}

/** Сводка отправленных ответов по задаче (без имён студентов). */
export interface TaskSummary {
  groups: number;
  answers: number;
  fields: TaskSummaryField[];
}

export interface PlanSection {
  key: string;
  title: string;
}

export interface PlanStudent {
  id: number;
  full_name: string;
}

export interface GroupEvent {
  id: number;
  study_group_id: number;
  school_year: string;
  section: string;
  title: string;
  event_date: string | null;
  time_text: string | null;
  responsible: string | null;
  goal: string | null;
  status: string;
  result: string | null;
  is_class_hour: boolean;
  description: string | null;
  attendee_ids: number[];
}

export interface GroupPlan {
  group_id: number;
  group_code: string;
  school_year: string;
  years: string[];
  sections: PlanSection[];
  events: GroupEvent[];
  students: PlanStudent[];
  can_edit: boolean;
}

export interface ParentMeeting {
  id: number;
  study_group_id: number;
  school_year: string;
  number: number;
  meeting_date: string | null;
  agenda: string | null;
  staff: string | null;
  speakers: string | null;
  meeting_format: string;
  parents_count: number | null;
  listened: string | null;
  resolved: string | null;
  attendee_ids: number[];
}

export interface MeetingGuardian {
  id: number;
  full_name: string;
  relation: string;
  student_name: string;
}

export interface GroupMeetings {
  group_id: number;
  school_year: string;
  meetings: ParentMeeting[];
  guardians: MeetingGuardian[];
}

export interface ReportField {
  key: string;
  label: string;
  hint: string | null;
  long: boolean;
  auto: string | null;
  value: string | null;
}

export interface ReportSection {
  key: string;
  title: string;
  fields: ReportField[];
}

export interface CuratorReport {
  group_id: number;
  group_code: string;
  school_year: string;
  semester: number;
  period_from: string;
  period_to: string;
  years: string[];
  sections: ReportSection[];
  updated_at: string | null;
  can_edit: boolean;
}

/** Профиль пользователя для администрации (интерфейс 3.0). */
export interface UserGroupLink {
  group_id: number;
  group_code: string;
  course: number;
  department_name: string | null;
  role_type: "curator" | "deputy";
  start_date: string;
  end_date: string | null;
  is_current: boolean;
  students_count: number;
}

export interface UserDiscipline {
  date_from: string;
  date_to: string;
  study_days: number;
  submitted: number;
  on_time: number;
  late: number;
  missed: number;
  percent_on_time: number | null;
}

export interface UserTaskStats {
  total: number;
  accepted: number;
  submitted: number;
  in_work: number;
  returned: number;
  overdue: number;
}

export interface UserProfile {
  user: UserAdmin;
  department_name: string | null;
  created_at: string;
  last_activity_at: string | null;
  groups: UserGroupLink[];
  discipline: UserDiscipline;
  tasks: UserTaskStats;
  marks_created_30d: number;
  days_submitted_30d: number;
  notes_written_30d: number;
  follow_ups_open: number;
  dossier_views_30d: number;
  activity_30d: { date: string; count: number }[];
}

export interface UserActivityEntry {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string;
  created_at: string;
}

export interface UserActivityPage {
  items: UserActivityEntry[];
  next_before_id: number | null;
}

export interface MyIdRow {
  student_id: number;
  full_name: string;
  biometrics: boolean | null;
  biometrics_reason: string | null;
  max_student: boolean | null;
  max_student_reason: string | null;
  max_parent: boolean | null;
  max_parent_reason: string | null;
}

export interface MyIdData {
  group_id: number;
  group_code: string;
  school_year: string;
  can_edit: boolean;
  rows: MyIdRow[];
  totals: {
    students: number;
    biometrics_yes: number;
    biometrics_no: number;
    biometrics_unset: number;
    max_student_yes: number;
    max_student_no: number;
    max_parent_yes: number;
    max_parent_no: number;
  };
}
