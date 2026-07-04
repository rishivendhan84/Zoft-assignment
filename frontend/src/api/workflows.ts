import { http } from './client';
import type {
  OperationDiff,
  VersionSummary,
  Workflow,
  WorkflowSummary,
  WorkflowVersion,
} from '../types';

export const listWorkflows = () => http.get<WorkflowSummary[]>('/workflows');

export const getWorkflow = (id: string) => http.get<Workflow>(`/workflows/${id}`);

export const listVersions = (workflowId: string) =>
  http.get<VersionSummary[]>(`/workflows/${workflowId}/versions`);

export const getVersion = (workflowId: string, versionId: string) =>
  http.get<WorkflowVersion>(`/workflows/${workflowId}/versions/${versionId}`);

export const getDiff = (workflowId: string, from: string, to: string) =>
  http.get<OperationDiff>(
    `/workflows/${workflowId}/diff?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
  );
