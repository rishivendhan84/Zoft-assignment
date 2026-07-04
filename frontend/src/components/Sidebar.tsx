import { useStore } from '../store/useStore';
import { relativeTime } from '../lib/time';
import { HealthDot } from './HealthDot';
import { ThemeToggle } from './ThemeToggle';
import { PlusIcon, SparklesIcon, CommitIcon } from './icons';

function SkeletonRows({ count }: { count: number }) {
  return (
    <div className="space-y-2 px-3 py-2" aria-hidden>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="h-8 animate-pulse rounded-md bg-zinc-200/70 dark:bg-zinc-800/70" />
      ))}
    </div>
  );
}

export function Sidebar() {
  const conversations = useStore((s) => s.conversations);
  const conversationsLoading = useStore((s) => s.conversationsLoading);
  const activeConversationId = useStore((s) => s.activeConversationId);
  const selectConversation = useStore((s) => s.selectConversation);
  const newConversation = useStore((s) => s.newConversation);
  const workflows = useStore((s) => s.workflows);
  const workflowsLoading = useStore((s) => s.workflowsLoading);
  const activeWorkflowId = useStore((s) => s.activeWorkflowId);
  const selectWorkflow = useStore((s) => s.selectWorkflow);

  return (
    <aside className="flex w-64 shrink-0 flex-col bg-zinc-50 dark:bg-zinc-900/60">
      <div className="flex items-center gap-2 px-4 py-3">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-indigo-600 text-white">
          <SparklesIcon size={13} />
        </span>
        <h1 className="text-sm font-semibold tracking-tight">Workflow Copilot</h1>
        <div className="ml-auto flex items-center gap-2">
          <HealthDot />
          <ThemeToggle />
        </div>
      </div>

      <div className="px-3">
        <button
          onClick={() => void newConversation()}
          className="flex w-full items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm font-medium text-zinc-700 transition-colors hover:border-indigo-400 hover:text-indigo-600 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-indigo-500 dark:hover:text-indigo-400"
        >
          <PlusIcon size={14} />
          New chat
        </button>
      </div>

      <div className="mt-4 flex-1 overflow-y-auto scrollbar-thin">
        <p className="px-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Conversations
        </p>
        {conversationsLoading ? (
          <SkeletonRows count={4} />
        ) : conversations.length === 0 ? (
          <p className="px-4 py-2 text-xs text-zinc-400 dark:text-zinc-500">
            No conversations yet — start one above.
          </p>
        ) : (
          <ul className="space-y-0.5 px-2">
            {conversations.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => void selectConversation(c.id)}
                  className={`w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                    c.id === activeConversationId
                      ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300'
                      : 'text-zinc-600 hover:bg-zinc-200/60 dark:text-zinc-400 dark:hover:bg-zinc-800/70'
                  }`}
                >
                  <span className="block truncate">{c.title ?? 'Untitled chat'}</span>
                  <span className="block text-[11px] text-zinc-400 dark:text-zinc-500">
                    {relativeTime(c.created_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <p className="mt-5 px-4 pb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          Workflows
        </p>
        {workflowsLoading ? (
          <SkeletonRows count={3} />
        ) : workflows.length === 0 ? (
          <p className="px-4 py-2 text-xs text-zinc-400 dark:text-zinc-500">
            None yet — ask the copilot to build one.
          </p>
        ) : (
          <ul className="space-y-0.5 px-2 pb-4">
            {workflows.map((w) => (
              <li key={w.id}>
                <button
                  onClick={() => void selectWorkflow(w.id)}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
                    w.id === activeWorkflowId
                      ? 'bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300'
                      : 'text-zinc-600 hover:bg-zinc-200/60 dark:text-zinc-400 dark:hover:bg-zinc-800/70'
                  }`}
                >
                  <CommitIcon size={13} className="shrink-0 opacity-60" />
                  <span className="min-w-0">
                    <span className="block truncate">{w.name}</span>
                    <span className="block text-[11px] text-zinc-400 dark:text-zinc-500">
                      updated {relativeTime(w.updated_at)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
