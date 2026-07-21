import type { PortalsDsrMetrics } from '../../types';

/** Declarative tab config for the Portals DSR entry form + the
 *  admin dashboard. Same source of truth for both — order + field
 *  names must match the DB columns + schema. */
export type PortalMetricField = {
  key: keyof PortalsDsrMetrics;
  label: string;
};

export type PortalTab = {
  key: string;         // slug (also the tab-hash if we ever add it)
  label: string;       // header label shown on the tab button
  accent: string;      // hex colour used for tab + KPI cards + charts
  metrics: PortalMetricField[];
};

/** 8 tabs, 25 metric fields total. Order comes from the paper form
 *  operators use today (see migration 013 for the definitive layout). */
export const PORTAL_TABS: PortalTab[] = [
  {
    key: 'ncrp',
    label: 'NCRP',
    accent: '#0b2c4a',   // navy
    metrics: [
      { key: 'ncrp_received', label: 'Received' },
      { key: 'ncrp_disposed', label: 'Disposed' },
      { key: 'ncrp_pending',  label: 'Pending' },
    ],
  },
  {
    key: 'samanvaya',
    label: 'Samanvaya',
    accent: '#0a6b28',   // green
    metrics: [
      { key: 'samanvaya_request_received', label: 'No. of Request Received' },
      { key: 'samanvaya_actions',          label: 'No. of Actions' },
      { key: 'samanvaya_action_pending',   label: 'No. of Action Pending' },
      { key: 'samanvaya_request_sent',     label: 'No. of Request Sent' },
      { key: 'samanvaya_reply_received',   label: 'No. of Reply Received' },
      { key: 'samanvaya_replies_pending',  label: 'No. of Replies Pending' },
    ],
  },
  {
    key: 'sahayog',
    label: 'Sahayog',
    accent: '#8b1919',   // red
    metrics: [
      { key: 'sahayog_unlawful_content_removal', label: 'No. of Unlawful Content Removal Requests' },
      { key: 'sahayog_intermediary_requests',    label: 'No. of Intermediary Requests' },
      { key: 'sahayog_crypto_requests',          label: 'No. of Crypto Requests' },
    ],
  },
  {
    key: 'grm',
    label: 'GRM',
    accent: '#6a1b9a',   // purple
    metrics: [
      { key: 'grm_request_received', label: 'No. of Request Received' },
      { key: 'grm_action',           label: 'No. of Action' },
      { key: 'grm_pending',          label: 'No. of Pending' },
    ],
  },
  {
    key: 'mrm',
    label: 'MRM',
    accent: '#c67c1d',   // orange
    metrics: [
      { key: 'mrm_request_received', label: 'No. of Request Received' },
      { key: 'mrm_action',           label: 'No. of Action' },
      { key: 'mrm_pending',          label: 'No. of Pending' },
    ],
  },
  {
    key: 'bharatpol',
    label: 'Bharatpol',
    accent: '#00695c',   // teal
    metrics: [
      { key: 'bharatpol_request_received', label: 'No. of Requests Received' },
    ],
  },
  {
    key: 'ocwc',
    label: 'OCWC',
    accent: '#5b6b7a',   // slate
    metrics: [
      { key: 'ocwc_received', label: 'No. of Received' },
      { key: 'ocwc_disposed', label: 'No. of Disposed' },
      { key: 'ocwc_pending',  label: 'No. of Pending' },
    ],
  },
  {
    key: 'ncmec',
    label: 'NCMEC (Tipline)',
    accent: '#b10000',   // deep red
    metrics: [
      { key: 'ncmec_received', label: 'No. of Received' },
      { key: 'ncmec_disposed', label: 'No. of Disposed' },
      { key: 'ncmec_pending',  label: 'No. of Pending' },
    ],
  },
];

/** Blank metrics record — all 25 fields set to 0. Used as the
 *  initial state of the entry form and as a reset target. */
export function emptyMetrics(): PortalsDsrMetrics {
  const out = {} as PortalsDsrMetrics;
  for (const tab of PORTAL_TABS) {
    for (const m of tab.metrics) {
      (out as any)[m.key] = 0;
    }
  }
  return out;
}
