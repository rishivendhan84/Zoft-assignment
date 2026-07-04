import { API_BASE, http } from './client';

export const cancelRun = (runId: string) => http.post<void>(`/runs/${runId}/cancel`);

export const runEventsUrl = (runId: string) => `${API_BASE}/runs/${runId}/events`;
