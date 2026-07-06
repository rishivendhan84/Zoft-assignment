import { API_BASE, http } from './client';

/** 202 body: 'cancelling' when a live task was cancelled, otherwise the run's
 * already-terminal status (finished runs stay finished). */
export const cancelRun = (runId: string) =>
  http.post<{ status: string }>(`/runs/${runId}/cancel`);

export const runEventsUrl = (runId: string) => `${API_BASE}/runs/${runId}/events`;
