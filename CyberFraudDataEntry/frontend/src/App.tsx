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

      <Route path="*" element={<Navigate to="/cases/new" replace />} />
      </Routes>
    </>
  );
}

export default App;
