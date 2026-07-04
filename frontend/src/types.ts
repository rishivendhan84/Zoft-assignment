/**
 * Types mirroring docs/API_CONTRACT.md verbatim.
 * The contract leaves graph node/edge shapes implicit; the FE assumptions for
 * those are noted inline and in the README.
 */

export type JSONSchema = Record<string, unknown>;

export type NodeCategory = 'trigger' | 'action' | 'logic';

export type NodeType = {
  type: string;
  category: NodeCategory;
  title: string;
  config_schema: JSONSchema;
  input_ports: string[];
  output_ports: string[];
};

export type Operation =
  | { op: 'add_node'; id: string; type: string; config?: Record<string, unknown> }
  | { op: 'remove_node'; id: string }
  | { op: 'connect'; from: string; to: string; port?: string }
  | { op: 'disconnect'; from: string; to: string }
  | { op: 'set_config'; id: string; config: Record<string, unknown> };

/** Graph node — id/type are contractual (operations reference them); the rest is defensive. */
export type WorkflowNode = {
  id: string;
  type: string;
  title?: string;
  category?: NodeCategory;
  config?: Record<string, unknown>;
};

export type Edge = { from: string; to: string; port?: string };

export type Graph = { nodes: WorkflowNode[]; edges: Edge[] };

export type WorkflowVersion = {
  id: string;
  workflow_id: string;
  parent_version_id?: string;
  graph: Graph;
  operations: Operation[];
  author: 'user' | 'ai';
  rationale?: string;
  created_at: string;
};

/** GET /workflows/{id}/versions list item — assumed to be WorkflowVersion sans full graph. */
export type VersionSummary = {
  id: string;
  workflow_id: string;
  parent_version_id?: string;
  author: 'user' | 'ai';
  rationale?: string;
  created_at: string;
  operations?: Operation[];
};

export type OperationDiff = { from: string; to: string; operations: Operation[] };

export type ConversationSummary = {
  id: string;
  workflow_id?: string;
  title?: string;
  created_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  run_id?: string;
  created_at: string;
};

export type WorkflowSummary = {
  id: string;
  name: string;
  current_version_id: string;
  updated_at: string;
};

/** GET /workflows/{id} → "Workflow (current version)". */
export type Workflow = WorkflowSummary & { graph: Graph };

// ---------------------------------------------------------------------------
// SSE events (exhaustive per contract)
// ---------------------------------------------------------------------------

export type Phase =
  | 'planning'
  | 'retrieving'
  | 'proposing'
  | 'validating'
  | 'repairing'
  | 'committing'
  | 'explaining';

export type StepEvent = {
  phase: Phase;
  label: string;
  tool?: string;
  arg?: string;
  attempt?: number;
};

export type TokenEvent = { text: string };

export type ValidationErrorItem = { node?: string; message: string };

export type ValidationEvent = {
  status: 'running' | 'passed' | 'failed';
  errors?: ValidationErrorItem[];
};

export type WorkflowUpdatedEvent = {
  workflow_id: string;
  version_id: string;
  graph: Graph;
  operations: Operation[];
};

export type MessageEvent = { role: 'assistant' | 'system'; content: string };

export type RunErrorEvent = { code: string; message: string; recoverable: boolean };

export type RunStatus = 'completed' | 'failed' | 'cancelled';

export type DoneEvent = { run_id: string; status: RunStatus };

// ---------------------------------------------------------------------------
// REST error envelope
// ---------------------------------------------------------------------------

export type ApiErrorBody = {
  error: { code: string; message: string; recoverable: boolean };
};
