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
  telegram_linked: boolean;
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

export interface StudentMarkHistoryEntry {
  date: string;
  mark_code: string;
  mark_name: string;
  basis_reference: string | null;
  basis_status: string;
}

export interface StudentCard {
  student_id: number;
  full_name: string;
  group_code: string;
  status: string;
  percent_period: number;
  history: StudentMarkHistoryEntry[];
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
}

export interface DeleteResult {
  deleted: boolean;
  anonymized: boolean;
  detail: string;
}

export interface StudentAdmin {
  id: number;
  full_name: string;
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
  telegram_linked: boolean;
  has_password: boolean;
  must_change_password: boolean;
  is_locked: boolean;
  receives_leadership_digest: boolean;
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
