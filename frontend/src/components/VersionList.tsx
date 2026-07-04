import { useStore } from '../store/useStore';
import { relativeTime } from '../lib/time';
import { Spinner } from './icons';

function AuthorBadge({ author }: { author: 'user' | 'ai' }) {
  return (
    <span
      className={`rounded px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ${
        author === 'ai'
          ? 'bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300'
          : 'bg-zinc-200 text-zinc-600 dark:bg-zinc-700/60 dark:text-zinc-300'
      }`}
    >
      {author}
    </span>
  );
}

export function VersionList() {
  const versions = useStore((s) => s.versions);
  const versionsLoading = useStore((s) => s.versionsLoading);
  const activeWorkflow = useStore((s) => s.activeWorkflow);
  const preview = useStore((s) => s.preview);
  const previewVersion = useStore((s) => s.previewVersion);
  const diffFrom = useStore((s) => s.diffFrom);
  const diffTo = useStore((s) => s.diffTo);
  const setDiffSelection = useStore((s) => s.setDiffSelection);
  const loadDiff = useStore((s) => s.loadDiff);
  const diffLoading = useStore((s) => s.diffLoading);

  if (versionsLoading) {
    return (
      <div className="space-y-2 p-3" aria-hidden>
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-14 animate-pulse rounded-lg bg-zinc-200/70 dark:bg-zinc-800/70" />
        ))}
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <p className="p-4 text-center text-sm text-zinc-400 dark:text-zinc-500">
        No versions yet — every validated change lands here as an immutable version.
      </p>
    );
  }

  const selectClass =
    'w-full rounded-md border border-zinc-300 bg-white px-1.5 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-900';

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-zinc-200 p-3 dark:border-zinc-800">
        <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Compare versions
        </p>
        <div className="flex items-center gap-2">
          <label className="flex-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            From
            <select
              className={selectClass}
              value={diffFrom ?? ''}
              onChange={(e) => setDiffSelection('from', e.target.value || null)}
            >
              <option value="">—</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.id}
                </option>
              ))}
            </select>
          </label>
          <label className="flex-1 text-[11px] text-zinc-500 dark:text-zinc-400">
            To
            <select
              className={selectClass}
              value={diffTo ?? ''}
              onChange={(e) => setDiffSelection('to', e.target.value || null)}
            >
              <option value="">—</option>
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.id}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => void loadDiff()}
            disabled={!diffFrom || !diffTo || diffFrom === diffTo || diffLoading}
            className="mt-4 flex h-7 items-center gap-1 rounded-md bg-indigo-600 px-2.5 text-xs font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-40"
          >
            {diffLoading && <Spinner size={11} />}
            Diff
          </button>
        </div>
      </div>

      <ul className="flex-1 space-y-1.5 overflow-y-auto p-3 scrollbar-thin">
        {versions.map((v) => {
          const isCurrent = v.id === activeWorkflow?.current_version_id;
          const isPreviewed = v.id === preview?.versionId;
          return (
            <li key={v.id}>
              <button
                onClick={() => void previewVersion(v.id)}
                className={`w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                  isPreviewed
                    ? 'border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-500/10'
                    : 'border-zinc-200 hover:border-zinc-300 dark:border-zinc-800 dark:hover:border-zinc-600'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-semibold text-zinc-700 dark:text-zinc-200">
                    {v.id}
                  </span>
                  <AuthorBadge author={v.author} />
                  {isCurrent && (
                    <span className="rounded bg-emerald-100 px-1.5 py-px text-[10px] font-medium text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                      current
                    </span>
                  )}
                  <span className="ml-auto text-[11px] text-zinc-400 dark:text-zinc-500">
                    {relativeTime(v.created_at)}
                  </span>
                </div>
                {v.rationale && (
                  <p className="mt-1 line-clamp-2 text-xs text-zinc-500 dark:text-zinc-400">
                    {v.rationale}
                  </p>
                )}
                {v.operations && v.operations.length > 0 && (
                  <p className="mt-0.5 text-[11px] text-zinc-400 dark:text-zinc-500">
                    {v.operations.length} operation{v.operations.length === 1 ? '' : 's'}
                  </p>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
