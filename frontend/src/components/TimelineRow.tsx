import type { TimelineEntry } from '../store/useStore';
import { AlertIcon, PhaseIcon, Spinner } from './icons';
import { ValidationRow } from './ValidationRow';

/** Fallback when a repair step predates the backend's max_attempts field. */
const DEFAULT_MAX_ATTEMPTS = 3;

export function TimelineRow({
  entry,
  active,
  live,
}: {
  entry: TimelineEntry;
  active: boolean;
  live: boolean;
}) {
  if (entry.kind === 'validation') {
    return <ValidationRow entry={entry} />;
  }

  if (entry.kind === 'error') {
    return (
      <div className="flex items-start gap-2 py-1 text-xs text-red-600 dark:text-red-400">
        <AlertIcon size={13} className="mt-0.5 shrink-0" />
        <span className="min-w-0">
          <span className="font-medium">{entry.message}</span>
          <span className="ml-1.5 text-red-400/80 dark:text-red-500/80">({entry.code})</span>
          {entry.recoverable &&
            (live ? (
              <span className="ml-2 inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                <Spinner size={10} /> Retrying…
              </span>
            ) : (
              <span className="ml-2 text-amber-600/80 dark:text-amber-400/80">
                (recoverable)
              </span>
            ))}
        </span>
      </div>
    );
  }

  // step
  return (
    <div className="flex items-center gap-2 py-1 text-xs text-zinc-500 dark:text-zinc-400">
      <span className="flex h-5 w-5 shrink-0 items-center justify-center text-zinc-400 dark:text-zinc-500">
        {active ? <Spinner size={13} className="text-indigo-500" /> : <PhaseIcon phase={entry.phase} size={13} />}
      </span>
      <span className="min-w-0 truncate">{entry.label}</span>
      {entry.tool && (
        <span
          className="shrink-0 rounded border border-zinc-200 bg-zinc-100 px-1.5 py-px font-mono text-[10px] text-zinc-500 dark:border-zinc-700 dark:bg-zinc-800/80 dark:text-zinc-400"
          title={entry.arg ? `${entry.tool}(${entry.arg})` : entry.tool}
        >
          {entry.tool}
          {entry.arg ? `(${entry.arg})` : ''}
        </span>
      )}
      {entry.attempt !== undefined && (
        <span className="shrink-0 rounded-full border border-amber-300 bg-amber-50 px-1.5 py-px text-[10px] font-medium text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-400">
          attempt {entry.attempt}/
          {entry.max_attempts ?? Math.max(DEFAULT_MAX_ATTEMPTS, entry.attempt)}
        </span>
      )}
    </div>
  );
}
