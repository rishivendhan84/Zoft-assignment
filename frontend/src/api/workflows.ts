import { http } from './client';
import type {
  OperationDiff,
  VersionSummary,
  Workflow,
  WorkflowSummary,
  WorkflowVersion,
} from '../types';

export const listWorkflows = () => http.get<WorkflowSummary[]>('/workflows');

/** Raw wire shape of GET /workflows/{id}: the current version is nested. */
type WorkflowResponse = {
  id: string;
  name: string;
  current_version_id: string | null;
  version: WorkflowVersion | null;
};

export const getWorkflow = async (id: string): Promise<Workflow> => {
  const raw = await http.get<WorkflowResponse>(`/workflows/${id}`);
  return {
    id: raw.id,
    name: raw.name,
    current_version_id: raw.current_version_id ?? '',
    updated_at: raw.version?.created_at ?? '',
    graph: raw.version?.graph ?? { nodes: [], edges: [] },
  };
};

export const listVersions = (workflowId: string) =>
  http.get<VersionSummary[]>(`/workflows/${workflowId}/versions`);

export const getVersion = (workflowId: string, versionId: string) =>
  http.get<WorkflowVersion>(`/workflows/${workflowId}/versions/${versionId}`);

export const getDiff = (workflowId: string, from: string, to: string) =>
  http.get<OperationDiff>(
    `/workflows/${workflowId}/diff?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
  );
