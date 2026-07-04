import type { OperationDiff } from '../types';
import { describeOperation } from '../lib/diff';

const toneClass = {
  add: 'text-emerald-600 dark:text-emerald-400',
  remove: 'text-red-600 dark:text-red-400',
  change: 'text-amber-600 dark:text-amber-400',
};

/** Readable changelog for an OperationDiff; the canvas highlights the same ops. */
export function DiffView({ diff }: { diff: OperationDiff }) {
  return (
    <div className="border-t border-zinc-200 bg-zinc-50/60 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/50">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
        Changes {diff.from} → {diff.to}
      </p>
      {diff.operations.length === 0 ? (
        <p className="text-xs text-zinc-400 dark:text-zinc-500">No changes between these versions.</p>
      ) : (
        <ul className="max-h-40 space-y-0.5 overflow-y-auto scrollbar-thin">
          {diff.operations.map((op, i) => {
            const d = describeOperation(op);
            return (
              <li key={i} className={`flex items-baseline gap-2 text-xs ${toneClass[d.tone]}`}>
                <span className="w-3 shrink-0 text-center font-bold">{d.sign}</span>
                <span className="min-w-0 break-words">{d.text}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
