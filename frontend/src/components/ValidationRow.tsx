import type { TimelineEntry } from '../store/useStore';
import { CheckIcon, ShieldIcon, Spinner, XIcon } from './icons';

type ValidationEntry = Extract<TimelineEntry, { kind: 'validation' }>;

export function ValidationRow({ entry }: { entry: ValidationEntry }) {
  if (entry.status === 'running') {
    return (
      <div className="flex items-center gap-2 py-1 text-xs text-zinc-500 dark:text-zinc-400">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center">
          <Spinner size={13} className="text-indigo-500" />
        </span>
        Validating workflow…
      </div>
    );
  }

  if (entry.status === 'passed') {
    return (
      <div className="flex items-center gap-2 py-1 text-xs text-emerald-600 dark:text-emerald-400">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center">
          <CheckIcon size={13} />
        </span>
        Validation passed
      </div>
    );
  }

  return (
    <div className="rounded-md border border-red-200 bg-red-50/60 px-2 py-1.5 dark:border-red-500/30 dark:bg-red-950/40">
      <div className="flex items-center gap-2 text-xs font-medium text-red-600 dark:text-red-400">
        <span className="flex h-5 w-5 shrink-0 items-center justify-center">
          <XIcon size={13} />
        </span>
        Validation failed
      </div>
      {entry.errors && entry.errors.length > 0 && (
        <ul className="mt-0.5 space-y-0.5 pl-7">
          {entry.errors.map((err, i) => (
            <li key={i} className="flex items-baseline gap-1.5 text-[11px] text-red-500 dark:text-red-400/90">
              {err.node && (
                <span className="rounded bg-red-100 px-1 font-mono text-[10px] dark:bg-red-500/15">
                  {err.node}
                </span>
              )}
              {err.message}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-0.5 flex items-center gap-1 pl-7 text-[11px] text-zinc-400 dark:text-zinc-500">
        <ShieldIcon size={10} /> invalid proposals are never persisted
      </p>
    </div>
  );
}
