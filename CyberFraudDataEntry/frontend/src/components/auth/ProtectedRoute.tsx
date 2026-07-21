import { Navigate } from 'react-router';
import { useAuthStore } from '../../lib/stores/auth-store';

interface Props {
  children: React.ReactNode;
  /** Allows admin + super_admin (e.g. Dashboard). */
  requireAdmin?: boolean;
  /** PS-administrator gate (User Management). Allows admin + super_admin
   *  — the same-PS isolation is enforced server-side, so a super_admin
   *  anchored to e.g. Cyber Crime PS can manage users of that PS only. */
  requirePsAdmin?: boolean;
}

export function ProtectedRoute({ children, requireAdmin, requirePsAdmin }: Props) {
  const { token, user } = useAuthStore();

  if (!token || !user) return <Navigate to="/login" replace />;
  if (requirePsAdmin && user.role !== 'admin' && user.role !== 'super_admin') {
    return <Navigate to="/" replace />;
  }
  if (requireAdmin && user.role !== 'admin' && user.role !== 'super_admin') {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
