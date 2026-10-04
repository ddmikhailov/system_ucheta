export interface MeGroupInfo {
  id: number;
  code: string;
  course: number;
}

export interface DossierProfile {
  birth_date: string | null;
  funding: "budget" | "contract" | null;
  phone: string | null;
  email: string | null;
  messenger: string | null;
  registration_address: string | null;
  residence_address: string | null;
  additional_education: string | null;
}

export interface DossierSpecial {
  is_orphan: boolean;
  under_guardianship: boolean;
  disability_group: string | null;
  has_ovz: boolean;
  large_family: boolean;
  low_income: boolean;
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
}

export interface GroupSummary {
  id: number;
  code: string;
  course: number;
  is_submitted_today: boolean;
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
  author_name: string | null;
  progress: TaskProgress;
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
}

export interface TaskRowRead {
  student_id: number;
  student_name: string;
  is_included: boolean;
  values: Record<string, unknown>;
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
