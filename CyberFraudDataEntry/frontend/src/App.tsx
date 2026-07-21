import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router';
import { Toaster } from 'sonner';
import { useAuthStore } from './lib/stores/auth-store';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { AppShell } from './components/layout/AppShell';
import { LoginPage } from './pages/LoginPage';
import { CaseEntryPage } from './pages/CaseEntryPage';
import { CaseUpdatePage } from './pages/CaseUpdatePage';
import { DashboardPage } from './pages/DashboardPage';
import { MuleReportEntryPage } from './pages/MuleReportEntryPage';
import { MuleUpdatePage } from './pages/MuleUpdatePage';
import { MuleUploadPage } from './pages/MuleUploadPage';
import { PetitionEntryPage } from './pages/PetitionEntryPage';
import { PetitionUpdatePage } from './pages/PetitionUpdatePage';
import { ChangePasswordPage } from './pages/ChangePasswordPage';
import { UserManagementPage } from './pages/UserManagementPage';
import { ReportsPage } from './pages/ReportsPage';
import { ChatPage } from './pages/ChatPage';
import { AllAccountEntryPage } from './pages/AllAccountEntryPage';
import { AllAccountUpdatePage } from './pages/AllAccountUpdatePage';
import { AccountsDashboardPage } from './pages/AccountsDashboardPage';
import { PortalsDsrEntryPage } from './pages/PortalsDsrEntryPage';
import { PortalsDsrUpdatePage } from './pages/PortalsDsrUpdatePage';
import { PortalsDsrDashboardPage } from './pages/PortalsDsrDashboardPage';
import { HomePage } from './pages/HomePage';

function App() {
  const { logout } = useAuthStore();

  // Always start fresh — require login on every new browser/tab session
  useEffect(() => {
    logout();
  }, []);

  return (
    <>
      <Toaster position="top-right" richColors closeButton />
      <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/change-password" element={<ChangePasswordPage />} />

      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        {/* Post-login landing — tile grid picker. Each tile navigates
             to its module's landingUrl; the Sidebar then switches to
             that module's contextual link list. */}
        <Route path="/" element={<HomePage />} />

        <Route path="/cases/new" element={<CaseEntryPage />} />
        <Route path="/cases/update" element={<CaseUpdatePage />} />
        <Route path="/cases/:id" element={<CaseEntryPage />} />

        <Route path="/petitions/new" element={<PetitionEntryPage />} />
        <Route path="/petitions/update" element={<PetitionUpdatePage />} />
        <Route path="/petitions/:id" element={<PetitionEntryPage />} />

        <Route path="/mule/upload" element={<MuleUploadPage />} />
        <Route path="/mule/new" element={<MuleReportEntryPage />} />
        <Route path="/mule/update" element={<MuleUpdatePage />} />
        <Route path="/mule/:id" element={<MuleReportEntryPage />} />

        <Route path="/all-accounts/new" element={<AllAccountEntryPage />} />
        <Route path="/all-accounts/update" element={<AllAccountUpdatePage />} />
        <Route path="/all-accounts/:id" element={<AllAccountEntryPage />} />

        <Route path="/portals-dsr/new" element={<PortalsDsrEntryPage />} />
        <Route path="/portals-dsr/update" element={<PortalsDsrUpdatePage />} />
        <Route path="/portals-dsr/:id" element={<PortalsDsrEntryPage />} />
        <Route
          path="/portals-dsr/dashboard"
          element={
            <ProtectedRoute requireAdmin>
              <PortalsDsrDashboardPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/dashboard"
          element={
            <ProtectedRoute requireAdmin>
              <DashboardPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/accounts-dashboard"
          element={
            <ProtectedRoute requireAdmin>
              <AccountsDashboardPage />
            </ProtectedRoute>
          }
        />

        <Route path="/chat" element={<ChatPage />} />

        <Route
          path="/users"
          element={
            <ProtectedRoute requirePsAdmin>
              <UserManagementPage />
            </ProtectedRoute>
          }
        />

        <Route path="/reports" element={<ReportsPage />} />
      </Route>

      {/* Unknown URL → land on the tile grid, not deep-linked entry. */}
      <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default App;
