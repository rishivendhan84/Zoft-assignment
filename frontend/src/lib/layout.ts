import type { Edge, WorkflowNode } from '../types';

export const NODE_W = 216;
export const NODE_H = 92;
export const COL_GAP = 72;
export const ROW_GAP = 28;
export const PADDING = 24;

export type PositionedNode = {
  node: WorkflowNode;
  x: number;
  y: number;
  /** true when the node existed in a previous graph but was removed (rendered as ghost) */
  ghost?: boolean;
};

export type LayoutResult = {
  nodes: PositionedNode[];
  byId: Map<string, PositionedNode>;
  width: number;
  height: number;
};

/**
 * Left-to-right layered layout by topological order (longest path from a source).
 * Cycles (shouldn't happen in valid workflows) fall back to column 0 for
 * unresolved nodes so rendering never breaks.
 */
export function layoutGraph(nodes: WorkflowNode[], edges: Edge[], ghosts: WorkflowNode[] = []): LayoutResult {
  const ids = new Set(nodes.map((n) => n.id));
  const validEdges = edges.filter((e) => ids.has(e.from) && ids.has(e.to));

  const indegree = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const out = new Map<string, string[]>();
  for (const e of validEdges) {
    indegree.set(e.to, (indegree.get(e.to) ?? 0) + 1);
    out.set(e.from, [...(out.get(e.from) ?? []), e.to]);
  }

  // Kahn's algorithm computing layer = longest path length from any source.
  const layer = new Map<string, number>();
  const queue = nodes.filter((n) => (indegree.get(n.id) ?? 0) === 0).map((n) => n.id);
  for (const id of queue) layer.set(id, 0);
  const pending = new Map(indegree);
  while (queue.length > 0) {
    const id = queue.shift() as string;
    for (const next of out.get(id) ?? []) {
      layer.set(next, Math.max(layer.get(next) ?? 0, (layer.get(id) ?? 0) + 1));
      const left = (pending.get(next) ?? 0) - 1;
      pending.set(next, left);
      if (left === 0) queue.push(next);
    }
  }

  const columns = new Map<number, WorkflowNode[]>();
  for (const n of nodes) {
    const col = layer.get(n.id) ?? 0;
    columns.set(col, [...(columns.get(col) ?? []), n]);
  }

  const positioned: PositionedNode[] = [];
  const byId = new Map<string, PositionedNode>();
  let maxRows = 1;
  const sortedCols = [...columns.keys()].sort((a, b) => a - b);
  for (const col of sortedCols) {
    const colNodes = columns.get(col) ?? [];
    maxRows = Math.max(maxRows, colNodes.length);
    colNodes.forEach((node, row) => {
      const p: PositionedNode = {
        node,
        x: PADDING + col * (NODE_W + COL_GAP),
        y: PADDING + row * (NODE_H + ROW_GAP),
      };
      positioned.push(p);
      byId.set(node.id, p);
    });
  }

  // Ghost (removed) nodes: stack them in an extra column on the right.
  const ghostCol = sortedCols.length;
  ghosts.forEach((node, row) => {
    const p: PositionedNode = {
      node,
      x: PADDING + ghostCol * (NODE_W + COL_GAP),
      y: PADDING + row * (NODE_H + ROW_GAP),
      ghost: true,
    };
    positioned.push(p);
    byId.set(node.id, p);
  });

  const totalCols = ghostCol + (ghosts.length > 0 ? 1 : 0);
  const width = PADDING * 2 + Math.max(totalCols, 0) * (NODE_W + COL_GAP) + NODE_W - (totalCols > 0 ? 0 : 0);
  const height = PADDING * 2 + Math.max(maxRows, ghosts.length) * (NODE_H + ROW_GAP) - ROW_GAP;
  return { nodes: positioned, byId, width, height };
}
