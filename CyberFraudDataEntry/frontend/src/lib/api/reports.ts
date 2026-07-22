/**
 * Report download helpers — every function fetches the PDF as a blob,
 * triggers a save dialog via a hidden anchor, and revokes the object URL.
 *
 * Each function returns a Promise that resolves once the download has
 * been initiated; rejection means the request itself failed (auth,
 * server error). The browser then handles the actual file save.
 */

const BASE = import.meta.env.VITE_API_BASE ?? '';


/** Fetches a binary attachment, honours Content-Disposition for the
 *  filename, and triggers a browser save. Name is `downloadPdf` for
 *  history but it works for any content-type (used by the FIR
 *  performance .xlsx export too). */
async function downloadPdf(path: string, fallbackName: string): Promise<void> {
  const token = localStorage.getItem('token');
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`Download failed (${res.status}): ${txt || res.statusText}`);
  }

  // Prefer the server-provided filename when available
  const cd = res.headers.get('Content-Disposition') || '';
  const match = cd.match(/filename="?([^";]+)"?/i);
  const filename = match?.[1] || fallbackName;

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


/**
 * Case file — one PDF for the given case (looked up by FIR number, or
 * by petition number if FIR is empty). Includes header + arrests with
 * accomplices/accused details + petitions + lien accounts + unfreezes +
 * refunds.
 *
 * Authorization (server-side):
 *   - super_admin: any case
 *   - admin / unit_user: only cases submitted from their own PS
 */
export function downloadCasePdf(opts: { firNo?: string; petitionNo?: string }): Promise<void> {
  const params = new URLSearchParams();
  if (opts.firNo) params.set('fir_no', opts.firNo);
  else if (opts.petitionNo) params.set('petition_no', opts.petitionNo);
  const ident = opts.firNo || opts.petitionNo || 'case';
  return downloadPdf(
    `/api/v1/reports/case.pdf?${params.toString()}`,
    `CaseFile_${ident}.pdf`,
  );
}


/**
 * Mule report — one PDF for the given bank acknowledgement number,
 * including all 6 transaction tables (landscape).
 *
 * Authorization (server-side):
 *   - super_admin: any mule report
 *   - admin / unit_user: only reports submitted from their own PS
 */
export function downloadMulePdf(ackNo: string): Promise<void> {
  return downloadPdf(
    `/api/v1/reports/mule.pdf?ack_no=${encodeURIComponent(ackNo)}`,
    `MuleReport_${ackNo}.pdf`,
  );
}


/**
 * DSR report — aggregated live from cases / arrests / petitions /
 * lien_accounts / refunds / mule_reports over a date range, filtered
 * by `created_at`.
 *
 * Scope precedence (super_admin only — all other roles are forced to
 * their own PS server-side):
 *   - psId N (>0)   → that single PS
 *   - psId 0        → all PSes (district ignored)
 *   - district set  → all PSes in that district
 *   - none          → super_admin's own PS
 */
export function downloadDsrPdf(
  dateFrom: string,
  dateTo: string,
  opts: { psId?: number; district?: string } = {},
): Promise<void> {
  const params = new URLSearchParams({ from: dateFrom, to: dateTo });
  if (opts.psId !== undefined && opts.psId !== null) {
    params.set('ps_id', String(opts.psId));
  }
  if (opts.district) {
    params.set('district', opts.district);
  }
  return downloadPdf(
    `/api/v1/reports/dsr.pdf?${params.toString()}`,
    `DSR_${dateFrom}_${dateTo}.pdf`,
  );
}

/**
 * PDF version of the Dashboard → Overview → Submission Status table
 * for a given date. Mirrors the on-screen rows; auth follows the same
 * admin / super_admin scoping as the JSON route.
 */
export function downloadSubmissionStatusPdf(date: string): Promise<void> {
  return downloadPdf(
    `/api/v1/reports/submission-status.pdf?date=${encodeURIComponent(date)}`,
    `SubmissionStatus_${date}.pdf`,
  );
}


/**
 * FIR Dashboard PS-performance table — PDF or Excel export. Uses the
 * same aggregation as the on-screen JSON endpoint so the file always
 * matches what the operator sees before any client-side re-sort.
 *
 * Admin scoping applies server-side: admin sees own PS only,
 * super_admin sees every active PS.
 */
export function downloadFirPsPerformancePdf(
  from: string,
  to: string,
): Promise<void> {
  const qs = new URLSearchParams({ from, to });
  return downloadPdf(
    `/api/v1/reports/fir-ps-performance.pdf?${qs.toString()}`,
    `FIR_PS_Performance_${from}_to_${to}.pdf`,
  );
}

export function downloadFirPsPerformanceExcel(
  from: string,
  to: string,
): Promise<void> {
  const qs = new URLSearchParams({ from, to });
  return downloadPdf(
    `/api/v1/reports/fir-ps-performance.xlsx?${qs.toString()}`,
    `FIR_PS_Performance_${from}_to_${to}.xlsx`,
  );
}
