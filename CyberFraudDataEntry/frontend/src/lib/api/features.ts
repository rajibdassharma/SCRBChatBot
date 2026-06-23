import { apiFetch } from './client';

export interface Features {
  chat_enabled: boolean;
}

/** Read the public feature flag list. Used by the sidebar to hide
 *  entry points for features that aren't provisioned in this
 *  environment (e.g. chat without a GPU box). Endpoint is unauthenticated
 *  so it can be called before login if ever needed. */
export async function getFeatures(): Promise<Features> {
  return apiFetch<Features>('/api/v1/features');
}
