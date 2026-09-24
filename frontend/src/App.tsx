import type { ReactElement } from "react";
import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import ChangePasswordPage from "./pages/ChangePasswordPage";
import CuratorCabinetPage from "./pages/CuratorCabinetPage";
import DashboardsPage from "./pages/DashboardsPage";
import AdminPage from "./pages/AdminPage";

const MANAGEMENT_ROLES = ["dept_head", "edu_department", "admin", "tutor"];

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
  if (MANAGEMENT_ROLES.includes(user.role)) return <Navigate to="/dashboards" replace />;
  return <Navigate to="/cabinet" replace />;
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
          <Route path="/" element={<HomeRedirect />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}
