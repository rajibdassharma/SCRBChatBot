import { MuleForm } from '../components/mule/MuleForm';

export function MuleEntryPage() {
  return (
    <div>
      <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)', letterSpacing: '-0.02em' }}>Mule Accounts Details</h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>Enter mule account analysis for your unit</p>
      <MuleForm />
    </div>
  );
}
