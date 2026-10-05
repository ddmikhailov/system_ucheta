import { Suspense, lazy } from "react";
import type { ReactElement } from "react";
import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/useAuth";
import FeedbackHost from "./components/FeedbackHost";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import CuratorCabinetPage from "./pages/CuratorCabinetPage";
import { DOSSIER_STAFF_ROLES, MANAGEMENT_ROLES, TASK_MANAGER_ROLES, inRoles } from "./constants/roles";
import MyDayPage from "./pages/MyDayPage";
import MyTasksPage from "./pages/MyTasksPage";
import TaskAssignmentPage from "./pages/TaskAssignmentPage";

// Разделы управления и справочные страницы грузятся по требованию: куратору на телефоне не нужно
// скачивать витрины и админку, чтобы открыть «Мой день».
const DashboardsPage = lazy(() => import("./pages/DashboardsPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const StudentCardPage = lazy(() => import("./pages/StudentCardPage"));
const StudentsSearchPage = lazy(() => import("./pages/StudentsSearchPage"));
const IndividualWorkPage = lazy(() => import("./pages/IndividualWorkPage"));
const PassportPage = lazy(() => import("./pages/PassportPage"));
const TasksPage = lazy(() => import("./pages/TasksPage"));

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-screen">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  // Временный пароль от администратора — дальше пути нет, пока не задан свой.
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
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

function HomeRedirect() {
  const { user, loading } = useAuth();
  // Пока /auth/me не ответил, user == null: без ожидания человек с действующим входом
  // отправлялся бы на страницу входа при каждом открытии сайта по корневому адресу.
  if (loading) return <div className="loading-screen">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
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

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Suspense fallback={<div className="loading-screen">Загрузка…</div>}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/change-password"
              element={
                <RequireAuthOnly>
                  <ChangePasswordPage />
                </RequireAuthOnly>
              }
            />
            <Route
              path="/my-day"
              element={
                <RequireAuth>
                  <Layout>
                    <MyDayPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/cabinet"
              element={
                <RequireAuth>
                  <Layout>
                    <CuratorCabinetPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/dashboards"
              element={
                <RequireAuth>
                  <Layout>
                    <DashboardsPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/admin"
              element={
                <RequireAuth>
                  <RequireAdminAccess>
                    <Layout>
                      <AdminPage />
                    </Layout>
                  </RequireAdminAccess>
                </RequireAuth>
              }
            />
            <Route
              path="/tasks"
              element={
                <RequireAuth>
                  <RequireTaskManager>
                    <Layout>
                      <TasksPage />
                    </Layout>
                  </RequireTaskManager>
                </RequireAuth>
              }
            />
            <Route
              path="/my-tasks"
              element={
                <RequireAuth>
                  <Layout>
                    <MyTasksPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/tasks/assignment/:assignmentId"
              element={
                <RequireAuth>
                  <Layout>
                    <TaskAssignmentPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/passport"
              element={
                <RequireAuth>
                  <Layout>
                    <PassportPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/individual-work"
              element={
                <RequireAuth>
                  <Layout>
                    <IndividualWorkPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/students"
              element={
                <RequireAuth>
                  <Layout>
                    <StudentsSearchPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route
              path="/students/:studentId"
              element={
                <RequireAuth>
                  <Layout>
                    <StudentCardPage />
                  </Layout>
                </RequireAuth>
              }
            />
            <Route path="/" element={<HomeRedirect />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </Suspense>
      </Router>
      <FeedbackHost />
    </AuthProvider>
  );
}
