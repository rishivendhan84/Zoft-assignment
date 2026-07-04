import { http } from './client';

export async function checkHealth(): Promise<boolean> {
  try {
    await http.get<unknown>('/health');
    return true;
  } catch {
    return false;
  }
}
