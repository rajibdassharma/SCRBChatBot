import { apiFetch } from './client';
import type { MuleReport, MuleReportListItem } from '../../types';

export async function createMuleReport(data: MuleReport): Promise<MuleReport> {
  return apiFetch<MuleReport>('/api/v1/mule-reports/', { method: 'POST', body: JSON.stringify(data) });
}
export async function updateMuleReport(id: string, data: MuleReport): Promise<MuleReport> {
  return apiFetch<MuleReport>(`/api/v1/mule-reports/${id}`, { method: 'PUT', body: JSON.stringify(data) });
}
export async function getMuleReport(id: string): Promise<MuleReport> {
  return apiFetch<MuleReport>(`/api/v1/mule-reports/${id}`);
}
export async function listMuleReports(limit = 50, offset = 0): Promise<MuleReportListItem[]> {
  return apiFetch<MuleReportListItem[]>(`/api/v1/mule-reports/?limit=${limit}&offset=${offset}`);
}
export async function deleteMuleReport(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/mule-reports/${id}`, { method: 'DELETE' });
}

export async function searchMuleReportByAck(ackNo: string): Promise<MuleReport | null> {
  return apiFetch<MuleReport | null>(`/api/v1/mule-reports/search?ack_no=${encodeURIComponent(ackNo)}`);
}

export async function parseMuleExcel(file: File): Promise<any> {
  const formData = new FormData();
  formData.append('file', file);
  const token = localStorage.getItem('token');
  const baseUrl = import.meta.env.VITE_API_BASE || '';
  const res = await fetch(`${baseUrl}/api/v1/mule-reports/parse-excel`, {
    method: 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Parse failed');
  }
  return res.json();
}

export async function uploadMuleExcel(files: File[]): Promise<{ results: Array<{ filename: string; ok: boolean; error?: string; report_id?: string; acknowledgement_no?: string; total_transactions?: number }> }> {
  const formData = new FormData();
  for (const f of files) {
    formData.append('files', f);
  }
  const token = localStorage.getItem('token');
  const baseUrl = import.meta.env.VITE_API_BASE || '';
  const res = await fetch(`${baseUrl}/api/v1/mule-reports/upload-excel`, {
    method: 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Upload failed');
  }
  return res.json();
}
