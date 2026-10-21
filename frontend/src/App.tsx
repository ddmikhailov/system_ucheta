import { Suspense, lazy, useState } from "react";
import type { ReactElement } from "react";
import { Navigate, Outlet, RouterProvider, createBrowserRouter, useLocation } from "react-router-dom";
import type { RouteObject } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/useAuth";
import FeedbackHost from "./components/FeedbackHost";
import Layout from "./components/Layout";
import NavMemory from "./components/NavMemory";
import LoginPage from "./pages/LoginPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import CuratorCabinetPage from "./pages/CuratorCabinetPage";
import CuratorGroupPage from "./pages/CuratorGroupPage";
import { MODULE } from "./constants/modules";
import type { ModuleName } from "./constants/modules";
import { isModuleOn } from "./utils/modules";
import { DOSSIER_STAFF_ROLES, MANAGEMENT_ROLES, MEAL_VIEW_ROLES, ROLE, TASK_MANAGER_ROLES, VIEWER_ROLES, inRoles } from "./constants/roles";
import MyDayPage from "./pages/MyDayPage";
import MyIdPanel from "./components/MyIdPanel";
import PlanPage from "./pages/PlanPage";
import ReportPage from "./pages/ReportPage";
import MyTasksPage from "./pages/MyTasksPage";
import TaskAssignmentPage from "./pages/TaskAssignmentPage";

// Разделы управления и справочные страницы грузятся по требованию: куратору на телефоне не нужно
// скачивать витрины и админку, чтобы открыть «Мой день».
const DashboardsPage = lazy(() => import("./pages/DashboardsPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const UserProfilePage = lazy(() => import("./pages/UserProfilePage"));
const StudentCardPage = lazy(() => import("./pages/StudentCardPage"));
const StudentsSearchPage = lazy(() => import("./pages/StudentsSearchPage"));
const IndividualWorkPage = lazy(() => import("./pages/IndividualWorkPage"));
const PassportPage = lazy(() => import("./pages/PassportPage"));
const TasksPage = lazy(() => import("./pages/TasksPage"));
const MealsPage = lazy(() => import("./pages/MealsPage"));

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  if (loading) return <div className="loading-screen">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  // Временный пароль от администратора — дальше пути нет, пока не задан свой.
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  // Ответственной по питанию открыта только вкладка «Питание»: остальные разделы ей недоступны (и сервер их закрывает).
  if (user.role === ROLE.MEAL_MANAGER && !pathname.startsWith("/meals")) return <Navigate to="/meals" replace />;
  return children;
}

// «Питание» (своды питающихся) — для руководства и ответственной по питанию.
function RequireMealViewer({ children }: { children: ReactElement }) {
  const { user } = useAuth();
  if (!user || !inRoles(user.role, MEAL_VIEW_ROLES)) return <Navigate to="/" replace />;
  return children;
}

// Для самой страницы смены пароля — только «пользователь вошёл», без
// проверки must_change_password (иначе RequireAuth зациклит редирект на неё же).
function RequireAuthOnly({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-screen">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

// Раздел выключенного модуля (ENABLED_MODULES, релиз 3.5.0) не открывается и по прямой ссылке — человек попадает
// на главную. Сама страница и её код остаются в проекте: модуль включается переменной окружения.
function RequireModule({ name, children }: { name: ModuleName; children: ReactElement }) {
  const { user } = useAuth();
  if (!isModuleOn(user, name)) return <Navigate to="/" replace />;
  return children;
}

function RequireAdminAccess({ children }: { children: ReactElement }) {
  const { user } = useAuth();
  // Зав. отделением тоже пускаем в админку — ему там доступна пока только
  // вкладка «Пользователи» (управление логинами/паролями кураторов своего
  // отделения), см. AdminPage.
  if (!user || !inRoles(user.role, MANAGEMENT_ROLES)) return <Navigate to="/" replace />;
  return children;
}

// «Задачи» — для тех, кто ставит и проверяет задачи; куратор по ссылке попадает к себе на главную.
function RequireTaskManager({ children }: { children: ReactElement }) {
  const { user } = useAuth();
  if (!user || !inRoles(user.role, TASK_MANAGER_ROLES)) return <Navigate to="/" replace />;
  return children;
}

// «Витрины» и поиск студентов отдаются сервером только руководству и специалистам; куратор по прямой ссылке
// раньше видел пустую страницу с ошибкой «Недостаточно прав» — теперь попадает к себе на главную.
function RequireViewer({ children }: { children: ReactElement }) {
  const { user } = useAuth();
  if (!user || !inRoles(user.role, VIEWER_ROLES)) return <Navigate to="/" replace />;
  return children;
}

function HomeRedirect() {
  const { user, loading } = useAuth();
  // Пока /auth/me не ответил, user == null: без ожидания человек с действующим входом
  // отправлялся бы на страницу входа при каждом открытии сайта по корневому адресу.
  if (loading) return <div className="loading-screen">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === ROLE.MEAL_MANAGER) return <Navigate to="/meals" replace />;
  if (inRoles(user.role, DOSSIER_STAFF_ROLES)) return <Navigate to="/students" replace />;
  if (inRoles(user.role, MANAGEMENT_ROLES)) return <Navigate to="/dashboards" replace />;
  return <Navigate to="/my-day" replace />;
}

function NotFoundPage() {
  return (
    <div className="not-found-page">
      <h1>404</h1>
      <p>Такой страницы нет.</p>
      <a href="/">На главную</a>
    </div>
  );
}

// Один родительский маршрут с общей рамкой (меню, шапка) вместо обёртки RequireAuth + Layout у каждой страницы;
// проверки роли и модуля — у самих разделов. Роутер с данными (createBrowserRouter) нужен для useBlocker: журнал
// спрашивает, прежде чем уйти по меню с несданными отметками.
const pages: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  {
    path: "/change-password",
    element: (
      <RequireAuthOnly>
        <ChangePasswordPage />
      </RequireAuthOnly>
    ),
  },
  {
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { path: "/my-day", element: <MyDayPage /> },
      { path: "/cabinet", element: <CuratorCabinetPage /> },
      { path: "/cabinet/groups/:groupId", element: <CuratorGroupPage /> },
      {
        path: "/dashboards",
        element: (
          <RequireViewer>
            <DashboardsPage />
          </RequireViewer>
        ),
      },
      {
        path: "/meals",
        element: (
          <RequireModule name={MODULE.MEALS}>
            <RequireMealViewer>
              <MealsPage />
            </RequireMealViewer>
          </RequireModule>
        ),
      },
      {
        path: "/admin",
        element: (
          <RequireAdminAccess>
            <AdminPage />
          </RequireAdminAccess>
        ),
      },
      {
        path: "/admin/users/:userId",
        element: (
          <RequireAdminAccess>
            <UserProfilePage />
          </RequireAdminAccess>
        ),
      },
      {
        path: "/tasks",
        element: (
          <RequireModule name={MODULE.TASKS}>
            <RequireTaskManager>
              <TasksPage />
            </RequireTaskManager>
          </RequireModule>
        ),
      },
      { path: "/my-tasks", element: <RequireModule name={MODULE.TASKS}><MyTasksPage /></RequireModule> },
      { path: "/tasks/assignment/:assignmentId", element: <RequireModule name={MODULE.TASKS}><TaskAssignmentPage /></RequireModule> },
      { path: "/passport", element: <RequireModule name={MODULE.PASSPORT}><PassportPage /></RequireModule> },
      { path: "/individual-work", element: <RequireModule name={MODULE.INDIVIDUAL_WORK}><IndividualWorkPage /></RequireModule> },
      { path: "/plan", element: <RequireModule name={MODULE.PLAN}><PlanPage /></RequireModule> },
      { path: "/report", element: <RequireModule name={MODULE.REPORTS}><ReportPage /></RequireModule> },
      { path: "/my-id", element: <RequireModule name={MODULE.MY_ID}><MyIdPanel /></RequireModule> },
      {
        path: "/students",
        element: (
          <RequireViewer>
            <StudentsSearchPage />
          </RequireViewer>
        ),
      },
      { path: "/students/:studentId", element: <StudentCardPage /> },
    ],
  },
  { path: "/", element: <HomeRedirect /> },
  { path: "*", element: <NotFoundPage /> },
];

// Корень над всеми страницами: память пути вкладки (NavMemory) видит любой переход, в том числе на вход.
function Root() {
  return (
    <>
      <NavMemory />
      <Outlet />
    </>
  );
}

const routes: RouteObject[] = [{ element: <Root />, children: pages }];

export default function App() {
  // Роутер создаётся при первой отрисовке, а не при импорте модуля: он читает адрес страницы в момент создания.
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <AuthProvider>
      <Suspense fallback={<div className="loading-screen">Загрузка…</div>}>
        <RouterProvider router={router} />
      </Suspense>
      <FeedbackHost />
    </AuthProvider>
  );
}
