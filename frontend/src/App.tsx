import type { ReactElement } from "react";
import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/useAuth";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import CuratorCabinetPage from "./pages/CuratorCabinetPage";
import DashboardsPage from "./pages/DashboardsPage";
import AdminPage from "./pages/AdminPage";
import StudentCardPage from "./pages/StudentCardPage";
import { DOSSIER_STAFF_ROLES, MANAGEMENT_ROLES } from "./constants/roles";
import StudentsSearchPage from "./pages/StudentsSearchPage";
import PassportPage from "./pages/PassportPage";
import TasksPage from "./pages/TasksPage";
import MyTasksPage from "./pages/MyTasksPage";
import TaskAssignmentPage from "./pages/TaskAssignmentPage";

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
  if (!user || !["admin", "edu_department", "dept_head", "tutor"].includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

function HomeRedirect() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (DOSSIER_STAFF_ROLES.includes(user.role)) return <Navigate to="/students" replace />;
  if (MANAGEMENT_ROLES.includes(user.role)) return <Navigate to="/dashboards" replace />;
  return <Navigate to="/cabinet" replace />;
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
                <Layout>
                  <TasksPage />
                </Layout>
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
      </Router>
    </AuthProvider>
  );
}
