import type { Operation } from '../types';

/** Per-node/edge highlight sets derived from a version's `operations[]`. */
export type GraphHighlights = {
  addedNodes: Set<string>;
  removedNodes: Set<string>;
  changedNodes: Set<string>;
  addedEdges: Set<string>;
  removedEdges: Set<string>;
};

/** Port-aware: parallel edges (a filter's true/false branches) must not collide. */
export const edgeKey = (from: string, to: string, port?: string) =>
  `${from}→${to}:${port ?? ''}`;

/** Pair-only key — disconnect operations don't carry a port. */
export const edgePairKey = (from: string, to: string) => `${from}→${to}`;

export function emptyHighlights(): GraphHighlights {
  return {
    addedNodes: new Set(),
    removedNodes: new Set(),
    changedNodes: new Set(),
    addedEdges: new Set(),
    removedEdges: new Set(),
  };
}

export function highlightsFromOperations(operations: Operation[]): GraphHighlights {
  const h = emptyHighlights();
  for (const op of operations) {
    switch (op.op) {
      case 'add_node':
        h.addedNodes.add(op.id);
        break;
      case 'remove_node':
        h.removedNodes.add(op.id);
        break;
      case 'set_config':
        h.changedNodes.add(op.id);
        break;
      case 'connect':
        h.addedEdges.add(edgeKey(op.from, op.to, op.port));
        break;
      case 'disconnect':
        h.removedEdges.add(edgePairKey(op.from, op.to));
        break;
    }
  }
  return h;
}

export function hasHighlights(h: GraphHighlights): boolean {
  return (
    h.addedNodes.size > 0 ||
    h.removedNodes.size > 0 ||
    h.changedNodes.size > 0 ||
    h.addedEdges.size > 0 ||
    h.removedEdges.size > 0
  );
}

/** Human-readable one-liner for an operation (used by the diff changelog). */
export function describeOperation(op: Operation): { sign: string; tone: 'add' | 'remove' | 'change'; text: string } {
  switch (op.op) {
    case 'add_node':
      return { sign: '+', tone: 'add', text: `Added node ${op.type} (${op.id})` };
    case 'remove_node':
      return { sign: '−', tone: 'remove', text: `Removed node ${op.id}` };
    case 'connect':
      return {
        sign: '+',
        tone: 'add',
        text: `Connected ${op.from} → ${op.to}${op.port ? ` (port "${op.port}")` : ''}`,
      };
    case 'disconnect':
      return { sign: '−', tone: 'remove', text: `Disconnected ${op.from} → ${op.to}` };
    case 'set_config':
      return {
        sign: '⚙',
        tone: 'change',
        text: `Changed config on ${op.id}: ${summarizeConfig(op.config)}`,
      };
  }
}

export function summarizeConfig(config: Record<string, unknown> | undefined, max = 3): string {
  if (!config) return '';
  const entries = Object.entries(config).slice(0, max);
  const rest = Object.keys(config).length - entries.length;
  const body = entries.map(([k, v]) => `${k}: ${formatConfigValue(v)}`).join(', ');
  return rest > 0 ? `${body}, +${rest} more` : body;
}

export function formatConfigValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'string') return v.length > 32 ? `${v.slice(0, 32)}…` : v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  const json = JSON.stringify(v);
  return json.length > 32 ? `${json.slice(0, 32)}…` : json;
}
