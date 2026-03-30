import { DsrForm } from '../components/dsr/DsrForm';

export function DsrEntryPage() {
  return (
    <div>
      <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>Daily Status Report (DSR)</h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>Enter your unit's daily cyber fraud statistics</p>
      <DsrForm />
    </div>
  );
}
