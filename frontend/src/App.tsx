import type { ReactElement } from "react";
import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import InvitationAcceptPage from "./pages/InvitationAcceptPage";
import CuratorCabinetPage from "./pages/CuratorCabinetPage";
import DashboardsPage from "./pages/DashboardsPage";
import AdminPage from "./pages/AdminPage";

const MANAGEMENT_ROLES = ["dept_head", "edu_department", "admin"];

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="loading-screen">Загрузка…</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function RequireAdminAccess({ children }: { children: ReactElement }) {
  const { user } = useAuth();
  if (!user || !["admin", "edu_department"].includes(user.role)) return <Navigate to="/" replace />;
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
          <Route path="/invite/:token" element={<InvitationAcceptPage />} />
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
