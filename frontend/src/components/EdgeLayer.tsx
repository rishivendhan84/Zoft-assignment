import type { Edge } from '../types';
import { NODE_H, NODE_W, type LayoutResult } from '../lib/layout';
import { edgeKey, edgePairKey, type GraphHighlights } from '../lib/diff';

/** SVG bezier edges drawn underneath the node cards, labeled with `port`. */
export function EdgeLayer({
  edges,
  layout,
  highlights,
  width,
  height,
}: {
  edges: Edge[];
  layout: LayoutResult;
  highlights: GraphHighlights;
  width: number;
  height: number;
}) {
  return (
    <svg width={width} height={height} className="absolute inset-0" aria-hidden>
      {edges.map((edge) => {
        const from = layout.byId.get(edge.from);
        const to = layout.byId.get(edge.to);
        if (!from || !to) return null;

        const removed = highlights.removedEdges.has(edgePairKey(edge.from, edge.to));
        const added = highlights.addedEdges.has(edgeKey(edge.from, edge.to, edge.port));

        const x1 = from.x + NODE_W;
        const y1 = from.y + NODE_H / 2;
        const x2 = to.x;
        const y2 = to.y + NODE_H / 2;
        const dx = Math.max(36, (x2 - x1) / 2);
        const path = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

        const stroke = added
          ? 'stroke-emerald-500'
          : removed
            ? 'stroke-red-400'
            : 'stroke-zinc-300 dark:stroke-zinc-600';
        const dot = added
          ? 'fill-emerald-500'
          : removed
            ? 'fill-red-400'
            : 'fill-zinc-300 dark:fill-zinc-600';

        return (
          <g key={edgeKey(edge.from, edge.to, edge.port)} className="transition-all duration-700">
            <path
              d={path}
              fill="none"
              strokeWidth={added ? 2 : 1.5}
              strokeDasharray={removed ? '4 4' : undefined}
              className={stroke}
            />
            <circle cx={x2} cy={y2} r={2.5} className={dot} />
            {edge.port && (
              <text
                x={(x1 + x2) / 2}
                y={(y1 + y2) / 2 - 6}
                textAnchor="middle"
                className="fill-zinc-400 text-[10px] font-medium dark:fill-zinc-500"
              >
                {edge.port}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
