export interface MeGroupInfo {
  id: number;
  code: string;
  course: number;
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
