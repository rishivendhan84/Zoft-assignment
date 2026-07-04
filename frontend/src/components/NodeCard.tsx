import type { NodeCategory, WorkflowNode } from '../types';
import { NODE_H, NODE_W } from '../lib/layout';
import { formatConfigValue } from '../lib/diff';
import { CategoryIcon } from './icons';

export type NodeHighlight = 'added' | 'changed' | 'removed' | null;

const categoryTone: Record<NodeCategory, string> = {
  trigger: 'text-amber-500 dark:text-amber-400',
  action: 'text-indigo-500 dark:text-indigo-400',
  logic: 'text-violet-500 dark:text-violet-400',
};

const highlightRing: Record<Exclude<NodeHighlight, null>, string> = {
  added: 'ring-2 ring-emerald-500 border-emerald-400 dark:border-emerald-500',
  changed: 'ring-2 ring-amber-500 border-amber-400 dark:border-amber-500',
  removed: 'border-dashed border-red-400 opacity-50 dark:border-red-500',
};

/** "slack.send_message" → "Slack · Send Message" */
function titleFromType(type: string): string {
  const [ns, ...rest] = type.split('.');
  const pretty = (s: string) =>
    s
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  return rest.length > 0 ? `${pretty(ns)} · ${pretty(rest.join('.'))}` : pretty(type);
}

export function NodeCard({
  node,
  category,
  x,
  y,
  highlight,
}: {
  node: WorkflowNode;
  category: NodeCategory;
  x: number;
  y: number;
  highlight: NodeHighlight;
}) {
  const config = Object.entries(node.config ?? {}).slice(0, 3);
  return (
    <div
      className={`absolute overflow-hidden rounded-xl border bg-white p-2.5 shadow-sm transition-all duration-700 dark:bg-zinc-900 ${
        highlight ? highlightRing[highlight] : 'border-zinc-200 dark:border-zinc-700'
      }`}
      style={{ left: x, top: y, width: NODE_W, height: NODE_H }}
      title={node.type}
    >
      <div className="flex items-center gap-1.5">
        <span className={`shrink-0 ${categoryTone[category]}`}>
          <CategoryIcon category={category} size={13} />
        </span>
        <span className="truncate text-xs font-semibold text-zinc-800 dark:text-zinc-100">
          {node.title ?? titleFromType(node.type)}
        </span>
      </div>
      <p className="mt-0.5 truncate font-mono text-[10px] text-zinc-400 dark:text-zinc-500">
        {node.id} · {node.type}
      </p>
      <div className="mt-1 space-y-px">
        {config.length === 0 ? (
          <p className="text-[10px] italic text-zinc-300 dark:text-zinc-600">no configuration</p>
        ) : (
          config.map(([k, v]) => (
            <p key={k} className="truncate text-[10px] text-zinc-500 dark:text-zinc-400">
              <span className="text-zinc-400 dark:text-zinc-500">{k}:</span> {formatConfigValue(v)}
            </p>
          ))
        )}
      </div>
    </div>
  );
}
