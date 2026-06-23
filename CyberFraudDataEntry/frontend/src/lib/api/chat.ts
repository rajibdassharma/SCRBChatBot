import { apiFetch } from './client';
import type { ChatResponse } from '../../types';

/** Send a natural-language question to the LLM-backed chat endpoint.
 *  The backend handles SQL generation, safety validation, execution, and
 *  natural-language summary in a single round-trip (2 LLM calls server-side). */
export async function askChat(question: string): Promise<ChatResponse> {
  return apiFetch<ChatResponse>('/api/v1/chat/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
}
