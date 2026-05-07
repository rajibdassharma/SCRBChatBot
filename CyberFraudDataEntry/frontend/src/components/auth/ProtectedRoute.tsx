import { Navigate } from 'react-router';
import { useAuthStore } from '../../lib/stores/auth-store';

export function ProtectedRoute({ children, requireAdmin }: { children: React.ReactNode; requireAdmin?: boolean }) {
  const { token, user } = useAuthStore();

  if (!token || !user) return <Navigate to="/login" replace />;
  if (requireAdmin && user.role !== 'admin' && user.role !== 'super_admin') {
    return <Navigate to="/cases/new" replace />;
  }

  return <>{children}</>;
}
