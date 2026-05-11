import { useState, useRef } from 'react';
import { Upload, CheckCircle, XCircle, FileSpreadsheet, Trash2 } from 'lucide-react';
import { uploadMuleExcel } from '../lib/api/mule-reports';
import { useAuthStore } from '../lib/stores/auth-store';
import { toast } from 'sonner';

interface UploadResult {
  filename: string;
  ok: boolean;
  error?: string;
  report_id?: string;
  acknowledgement_no?: string;
  total_transactions?: number;
}

export function MuleUploadPage() {
  const { user } = useAuthStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const xlsxFiles = files.filter(f => f.name.endsWith('.xlsx') || f.name.endsWith('.xls'));
    if (xlsxFiles.length < files.length) {
      toast.warning('Some files were skipped (only .xlsx and .xls files are accepted)');
    }
    setSelectedFiles(prev => [...prev, ...xlsxFiles]);
    setResults([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setResults([]);
    try {
      const response = await uploadMuleExcel(selectedFiles);
      setResults(response.results);
      const okCount = response.results.filter(r => r.ok).length;
      const failCount = response.results.filter(r => !r.ok).length;
      if (okCount > 0) toast.success(`${okCount} file(s) uploaded successfully`);
      if (failCount > 0) toast.error(`${failCount} file(s) failed`);
      setSelectedFiles([]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="rounded-2xl p-4 mb-4" style={{ background: 'var(--ksp-navy)', color: '#fff' }}>
        <h1 className="text-lg font-bold" style={{ color: 'var(--ksp-yellow)' }}>Mule Accounts Data</h1>
        <div className="flex gap-6 mt-2 text-sm">
          <span><strong>District:</strong> {user?.unit_name}</span>
          <span><strong>CCPS:</strong> {user?.ps_name || 'N/A'}</span>
          <span><strong>User:</strong> {user?.username}</span>
        </div>
      </div>

      <h1 className="text-[22px] font-bold mb-1" style={{ color: 'var(--ksp-navy)' }}>Upload Bank Action Reports</h1>
      <p className="text-sm font-medium mb-6" style={{ color: 'var(--ksp-red)' }}>
        Upload one or more Excel files (.xlsx). Each file will create a mule report with all transaction tabs.
      </p>

      {/* Upload area */}
      <div className="max-w-3xl">
        <div className="flex gap-4">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex-1 rounded-2xl p-6 text-center cursor-pointer transition hover:opacity-80"
            style={{ background: '#fff', border: '3px dashed rgba(11,44,74,0.3)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}
          >
            <Upload className="w-10 h-10 mx-auto mb-2" style={{ color: 'var(--ksp-navy)' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--ksp-navy)' }}>Select Files</p>
            <p className="text-xs mt-1" style={{ color: 'rgba(11,44,74,0.5)' }}>Pick one or more .xlsx files</p>
          </button>
          <button
            type="button"
            onClick={() => folderInputRef.current?.click()}
            className="flex-1 rounded-2xl p-6 text-center cursor-pointer transition hover:opacity-80"
            style={{ background: '#fff', border: '3px dashed rgba(11,44,74,0.3)', boxShadow: '0 6px 16px rgba(0,0,0,0.08)' }}
          >
            <FileSpreadsheet className="w-10 h-10 mx-auto mb-2" style={{ color: 'var(--ksp-navy)' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--ksp-navy)' }}>Select Folder</p>
            <p className="text-xs mt-1" style={{ color: 'rgba(11,44,74,0.5)' }}>Upload all .xlsx files from a folder</p>
          </button>
          <input ref={fileInputRef} type="file" multiple accept=".xlsx,.xls" onChange={handleFileSelect} className="hidden" />
          <input ref={folderInputRef} type="file" accept=".xlsx,.xls" onChange={handleFileSelect} className="hidden" {...{ webkitdirectory: '', directory: '' } as any} />
        </div>

        {/* Selected files list */}
        {selectedFiles.length > 0 && (
          <div className="mt-4 rounded-2xl p-4" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }}>
            <p className="text-xs font-semibold mb-3" style={{ color: 'var(--ksp-navy)' }}>
              {selectedFiles.length} file(s) selected
            </p>
            {selectedFiles.map((f, i) => (
              <div key={i} className="flex items-center justify-between py-2 px-3 rounded-xl mb-1" style={{ background: 'rgba(11,44,74,0.04)' }}>
                <div className="flex items-center gap-2">
                  <FileSpreadsheet className="w-4 h-4" style={{ color: 'var(--ksp-navy)' }} />
                  <span className="text-sm font-medium" style={{ color: 'var(--ksp-navy)' }}>{f.name}</span>
                  <span className="text-xs" style={{ color: 'rgba(11,44,74,0.5)' }}>({(f.size / 1024).toFixed(0)} KB)</span>
                </div>
                <button onClick={() => removeFile(i)} className="p-1 rounded hover:bg-red-100 transition">
                  <Trash2 className="w-4 h-4" style={{ color: 'var(--ksp-red)' }} />
                </button>
              </div>
            ))}

            <div className="mt-4 flex gap-3">
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="flex items-center gap-2 px-6 py-2.5 text-sm font-semibold rounded-xl transition disabled:opacity-50"
                style={{ background: 'var(--ksp-navy)', color: 'var(--ksp-yellow)', border: '2px solid rgba(0,0,0,0.25)' }}
              >
                <Upload className="w-4 h-4" /> {uploading ? 'Uploading...' : 'Upload All'}
              </button>
              <button
                onClick={() => { setSelectedFiles([]); setResults([]); }}
                className="flex items-center gap-2 px-6 py-2.5 text-sm font-semibold rounded-xl transition"
                style={{ background: '#fff', color: 'var(--ksp-red)', border: '2px solid rgba(177,0,0,0.3)' }}
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <div className="mt-4 rounded-2xl p-4" style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }}>
            <p className="text-xs font-semibold mb-3" style={{ color: 'var(--ksp-navy)' }}>Upload Results</p>
            {results.map((r, i) => (
              <div key={i} className="flex items-center gap-3 py-2 px-3 rounded-xl mb-1" style={{ background: r.ok ? 'rgba(22,163,74,0.06)' : 'rgba(177,0,0,0.06)' }}>
                {r.ok ? (
                  <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
                ) : (
                  <XCircle className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--ksp-red)' }} />
                )}
                <div className="flex-1">
                  <span className="text-sm font-semibold" style={{ color: 'var(--ksp-navy)' }}>{r.filename}</span>
                  {r.ok ? (
                    <p className="text-xs text-green-700">
                      Ack No: {r.acknowledgement_no} | {r.total_transactions} transactions imported
                    </p>
                  ) : (
                    <p className="text-xs" style={{ color: 'var(--ksp-red)' }}>{r.error}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
