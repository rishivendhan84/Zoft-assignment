import { useMemo } from 'react';
import type { Graph, NodeCategory, WorkflowNode } from '../types';
import { layoutGraph } from '../lib/layout';
import type { GraphHighlights } from '../lib/diff';
import { EdgeLayer } from './EdgeLayer';
import { NodeCard, type NodeHighlight } from './NodeCard';

const LOGIC_HINT = /(filter|condition|branch|switch|logic|if\b)/i;

/**
 * Category per node: explicit `category` wins; otherwise infer — sources
 * (no incoming edges) read as triggers, filter-ish types as logic, rest as actions.
 */
function inferCategory(node: WorkflowNode, hasIncoming: boolean): NodeCategory {
  if (node.category) return node.category;
  if (LOGIC_HINT.test(node.type)) return 'logic';
  return hasIncoming ? 'action' : 'trigger';
}

export function WorkflowCanvas({
  graph,
  highlights,
  ghosts,
}: {
  graph: Graph;
  highlights: GraphHighlights;
  ghosts: WorkflowNode[];
}) {
  const layout = useMemo(
    () => layoutGraph(graph.nodes, graph.edges, ghosts),
    [graph, ghosts],
  );
  const incoming = useMemo(
    () => new Set(graph.edges.map((e) => e.to)),
    [graph.edges],
  );

  if (graph.nodes.length === 0 && ghosts.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-zinc-400 dark:text-zinc-500">
        This workflow has no nodes yet.
      </div>
    );
  }

  const nodeHighlight = (id: string, ghost?: boolean): NodeHighlight => {
    if (ghost || highlights.removedNodes.has(id)) return 'removed';
    if (highlights.addedNodes.has(id)) return 'added';
    if (highlights.changedNodes.has(id)) return 'changed';
    return null;
  };

  return (
    <div className="h-full overflow-auto scrollbar-thin">
      <div className="relative" style={{ width: layout.width, height: layout.height }}>
        <EdgeLayer
          edges={graph.edges}
          layout={layout}
          highlights={highlights}
          width={layout.width}
          height={layout.height}
        />
        {layout.nodes.map((p) => (
          <NodeCard
            key={p.node.id}
            node={p.node}
            category={inferCategory(p.node, incoming.has(p.node.id))}
            x={p.x}
            y={p.y}
            highlight={nodeHighlight(p.node.id, p.ghost)}
          />
        ))}
      </div>
    </div>
  );
}
