import { useState } from 'react';
import type { TimelineEntry } from '../store/useStore';
import { TimelineRow } from './TimelineRow';
import { CheckIcon, ChevronIcon, XIcon } from './icons';

function summarize(entries: TimelineEntry[]) {
  const steps = entries.filter((e) => e.kind === 'step').length;
  const validation = [...entries].reverse().find((e) => e.kind === 'validation');
  const hadError = entries.some((e) => e.kind === 'error');
  return { steps, validationStatus: validation?.status, hadError };
}

/**
 * Agent activity timeline. Expanded while the run is live; collapses to a
 * one-line summary once attached to a finished message (click to expand).
 */
export function Timeline({ entries, live }: { entries: TimelineEntry[]; live: boolean }) {
  const [open, setOpen] = useState(false);
  if (entries.length === 0) return null;

  const rows = (
    <div className="space-y-px">
      {entries.map((entry, i) => (
        <TimelineRow
          key={entry.entryId}
          entry={entry}
          active={live && i === entries.length - 1 && entry.kind === 'step'}
          live={live}
        />
      ))}
    </div>
  );

  if (live) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-zinc-50/80 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
        {rows}
      </div>
    );
  }

  const { steps, validationStatus, hadError } = summarize(entries);
  return (
    <div className="mb-2 rounded-lg border border-zinc-200 bg-zinc-50/80 dark:border-zinc-800 dark:bg-zinc-900/60">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-[11px] text-zinc-400 transition-colors hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300"
        aria-expanded={open}
      >
        <ChevronIcon size={11} open={open} />
        <span>
          Agent ran {steps} step{steps === 1 ? '' : 's'}
        </span>
        {validationStatus === 'passed' && (
          <span className="flex items-center gap-0.5 text-emerald-500">
            <CheckIcon size={10} /> validated
          </span>
        )}
        {validationStatus === 'failed' && (
          <span className="flex items-center gap-0.5 text-red-500">
            <XIcon size={10} /> validation failed
          </span>
        )}
        {hadError && <span className="text-red-500">· errors</span>}
      </button>
      {open && <div className="border-t border-zinc-200 px-3 py-2 dark:border-zinc-800">{rows}</div>}
    </div>
  );
}
