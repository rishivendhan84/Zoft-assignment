import { useStore } from '../store/useStore';
import { emptyHighlights } from '../lib/diff';
import { WorkflowCanvas } from './WorkflowCanvas';
import { VersionList } from './VersionList';
import { DiffView } from './DiffView';
import { CommitIcon, Spinner, XIcon } from './icons';

function Tab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? 'bg-zinc-200/80 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100'
          : 'text-zinc-400 hover:text-zinc-600 dark:text-zinc-500 dark:hover:text-zinc-300'
      }`}
    >
      {label}
    </button>
  );
}

export function WorkflowPanel() {
  const activeWorkflow = useStore((s) => s.activeWorkflow);
  const workflowLoading = useStore((s) => s.workflowLoading);
  const liveHighlights = useStore((s) => s.liveHighlights);
  const liveGhosts = useStore((s) => s.liveGhosts);
  const panelTab = useStore((s) => s.panelTab);
  const setPanelTab = useStore((s) => s.setPanelTab);
  const preview = useStore((s) => s.preview);
  const clearPreview = useStore((s) => s.clearPreview);

  const showingPreview = preview !== null;
  const graph = preview?.graph ?? activeWorkflow?.graph;
  const highlights = preview?.highlights ?? (showingPreview ? emptyHighlights() : liveHighlights);
  const ghosts = preview?.ghosts ?? (showingPreview ? [] : liveGhosts);

  return (
    <aside className="flex w-[26rem] shrink-0 flex-col bg-zinc-50 dark:bg-zinc-900/60 xl:w-[30rem]">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-200 px-3 dark:border-zinc-800">
        <CommitIcon size={14} className="shrink-0 text-violet-500" />
        <h2 className="min-w-0 truncate text-sm font-medium">
          {activeWorkflow?.name ?? 'Workflow'}
        </h2>
        {activeWorkflow && (
          <span className="rounded bg-zinc-200/70 px-1.5 py-px font-mono text-[10px] text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
            {activeWorkflow.current_version_id}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Tab label="Canvas" active={panelTab === 'canvas'} onClick={() => setPanelTab('canvas')} />
          <Tab
            label="Versions"
            active={panelTab === 'versions'}
            onClick={() => setPanelTab('versions')}
          />
        </div>
      </header>

      {showingPreview && (
        <div className="flex items-center gap-2 border-b border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300">
          {preview.diff
            ? `Diff ${preview.diff.from} → ${preview.diff.to}`
            : `Viewing ${preview.versionId} (historical)`}
          <button
            onClick={clearPreview}
            className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 font-medium transition-colors hover:bg-indigo-100 dark:hover:bg-indigo-500/20"
          >
            <XIcon size={10} /> Back to current
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1">
        {!activeWorkflow && !workflowLoading ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
            <CommitIcon size={24} className="text-zinc-300 dark:text-zinc-700" />
            <p className="text-sm text-zinc-400 dark:text-zinc-500">
              No workflow selected — pick one from the sidebar, or ask the copilot to build one
              and it will appear here live.
            </p>
          </div>
        ) : workflowLoading || !graph ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-zinc-400 dark:text-zinc-500">
            <Spinner size={15} /> Loading workflow…
          </div>
        ) : panelTab === 'canvas' ? (
          <div className="flex h-full flex-col">
            <div className="min-h-0 flex-1">
              <WorkflowCanvas graph={graph} highlights={highlights} ghosts={ghosts} />
            </div>
            {preview?.diff && <DiffView diff={preview.diff} />}
          </div>
        ) : (
          <VersionList />
        )}
      </div>
    </aside>
  );
}
