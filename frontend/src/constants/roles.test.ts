import { describe, expect, it } from "vitest";
import {
  COLLEGE_WIDE_ROLES,
  CURATOR_CAPABLE_ROLES,
  DEPARTMENT_REQUIRED_ROLES,
  DEPARTMENT_SCOPED_ROLES,
  DOSSIER_STAFF_ROLES,
  MANAGEMENT_ROLES,
  ROLE,
  ROLE_LABELS,
  STRUCTURE_EDITOR_ROLES,
  TASK_MANAGER_ROLES,
  TEACHER_ROLES,
  VIEWER_ROLES,
  assignableRoles,
  inRoles,
  leadsGroups,
} from "./roles";

describe("inRoles", () => {
  it("true только для ролей из группы; пустая роль — нет", () => {
    expect(inRoles("tutor", DEPARTMENT_SCOPED_ROLES)).toBe(true);
    expect(inRoles("admin", DEPARTMENT_SCOPED_ROLES)).toBe(false);
    expect(inRoles(undefined, MANAGEMENT_ROLES)).toBe(false);
    expect(inRoles(null, MANAGEMENT_ROLES)).toBe(false);
  });
});

describe("leadsGroups", () => {
  it("куратор и заместитель — по роли, остальные — если им назначена группа", () => {
    expect(leadsGroups({ role: "curator", groups: [] })).toBe(true);
    expect(leadsGroups({ role: "deputy_curator" })).toBe(true);
    expect(leadsGroups({ role: "psychologist", groups: [{ id: 1 }] })).toBe(true);
    expect(leadsGroups({ role: "psychologist", groups: [] })).toBe(false);
    expect(leadsGroups({ role: "admin", groups: [] })).toBe(false);
    expect(leadsGroups(null)).toBe(false);
  });
});

describe("assignableRoles", () => {
  it("админ — любые; зав. отделением — рабочие роли и зав. отделением; тьютор — без зав. отделением; остальные — никакие", () => {
    expect(assignableRoles("admin").sort()).toEqual(Object.values(ROLE).sort());
    expect(assignableRoles("dept_head")).toEqual(
      expect.arrayContaining(["curator", "deputy_curator", "social_pedagogue", "psychologist", "dept_head"])
    );
    expect(assignableRoles("dept_head")).not.toContain("admin");
    expect(assignableRoles("dept_head")).not.toContain("tutor");
    expect(assignableRoles("tutor")).not.toContain("dept_head");
    expect(assignableRoles("tutor")).toContain("psychologist");
    for (const role of ["curator", "edu_department", "social_pedagogue", undefined]) {
      expect(assignableRoles(role)).toEqual([]);
    }
  });
});

describe("состав групп ролей", () => {
  it("у каждой роли есть подпись, а группы состоят только из существующих ролей", () => {
    const all = Object.values(ROLE);
    expect(Object.keys(ROLE_LABELS).sort()).toEqual([...all].sort());
    for (const group of [
      TEACHER_ROLES, DOSSIER_STAFF_ROLES, DEPARTMENT_SCOPED_ROLES, MANAGEMENT_ROLES, VIEWER_ROLES, TASK_MANAGER_ROLES,
      CURATOR_CAPABLE_ROLES, STRUCTURE_EDITOR_ROLES, COLLEGE_WIDE_ROLES, DEPARTMENT_REQUIRED_ROLES,
    ]) {
      for (const role of group) expect(all).toContain(role);
      expect(new Set(group).size).toBe(group.length); // без повторов
    }
  });

  it("инварианты прав: куратор не управленец; специалисты видят всё, но не управляют; тьютор в отделении", () => {
    expect(MANAGEMENT_ROLES).not.toContain("curator");
    expect(MANAGEMENT_ROLES).not.toContain("psychologist");
    expect(VIEWER_ROLES).toEqual(expect.arrayContaining([...MANAGEMENT_ROLES, ...DOSSIER_STAFF_ROLES]));
    expect(STRUCTURE_EDITOR_ROLES).not.toContain("edu_department");
    expect(DEPARTMENT_SCOPED_ROLES).toContain("tutor");
    expect(COLLEGE_WIDE_ROLES).not.toContain("tutor");
    expect(DEPARTMENT_REQUIRED_ROLES).not.toContain("admin");
    expect(DEPARTMENT_REQUIRED_ROLES).not.toContain("edu_department");
  });
});
