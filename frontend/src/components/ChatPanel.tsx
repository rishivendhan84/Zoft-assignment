import { useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';
import { MessageBubble } from './MessageBubble';
import { Composer } from './Composer';
import { Timeline } from './Timeline';
import { AlertIcon, SparklesIcon, Spinner, XIcon } from './icons';

const SUGGESTIONS = [
  "Send a Slack message when Stripe receives a payment",
  'Only notify me for payments over $500 on weekdays',
  'Swap Slack for Microsoft Teams in my workflow',
  'Explain what my workflow does',
];

function EmptyState() {
  const setComposerDraft = useStore((s) => s.setComposerDraft);
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 px-8 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600/10 text-indigo-500 dark:bg-indigo-500/15">
        <SparklesIcon size={22} />
      </span>
      <div>
        <h2 className="text-lg font-semibold tracking-tight">Build workflows by chatting</h2>
        <p className="mt-1 max-w-md text-sm text-zinc-500 dark:text-zinc-400">
          Describe an automation and the copilot will plan it, validate it against the node
          catalog, and commit it as a new workflow version — you watch every step.
        </p>
      </div>
      <div className="flex max-w-lg flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => setComposerDraft(s)}
            className="rounded-full border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600 transition-colors hover:border-indigo-400 hover:text-indigo-600 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-indigo-500 dark:hover:text-indigo-400"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessagesSkeleton() {
  return (
    <div className="space-y-4 p-6" aria-hidden>
      <div className="ml-auto h-10 w-2/5 animate-pulse rounded-2xl bg-zinc-200/70 dark:bg-zinc-800/70" />
      <div className="h-20 w-3/5 animate-pulse rounded-2xl bg-zinc-200/70 dark:bg-zinc-800/70" />
      <div className="ml-auto h-10 w-1/3 animate-pulse rounded-2xl bg-zinc-200/70 dark:bg-zinc-800/70" />
    </div>
  );
}

export function ChatPanel() {
  const activeConversationId = useStore((s) => s.activeConversationId);
  const conversations = useStore((s) => s.conversations);
  const messages = useStore((s) =>
    s.activeConversationId ? s.messages[s.activeConversationId] : undefined,
  );
  const messagesLoading = useStore((s) => s.messagesLoading);
  const activeRun = useStore((s) => s.activeRun);
  const retryLast = useStore((s) => s.retryLast);
  const workflows = useStore((s) => s.workflows);

  const conversation = conversations.find((c) => c.id === activeConversationId);
  const attachedWorkflow = workflows.find((w) => w.id === conversation?.workflow_id);
  const runIsHere = activeRun !== null && activeRun.conversationId === activeConversationId;

  const scrollRef = useRef<HTMLDivElement>(null);
  const messageCount = messages?.length ?? 0;
  const streamLen = runIsHere ? activeRun.streamText.length : 0;
  const timelineLen = runIsHere ? activeRun.timeline.length : 0;
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messageCount, streamLen, timelineLen, activeConversationId]);

  const lastMessage = messages?.[messages.length - 1];
  const showRetry =
    !activeRun &&
    lastMessage?.role === 'assistant' &&
    (lastMessage.runStatus === 'failed' || lastMessage.runStatus === 'cancelled');

  const terminalError = runIsHere ? activeRun.error : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 border-b border-zinc-200 px-4 dark:border-zinc-800">
        <h2 className="truncate text-sm font-medium">
          {conversation ? conversation.title ?? 'Untitled chat' : 'Chat'}
        </h2>
        {attachedWorkflow && (
          <span className="rounded-full border border-violet-300 bg-violet-50 px-2 py-0.5 text-[11px] text-violet-700 dark:border-violet-500/40 dark:bg-violet-500/10 dark:text-violet-300">
            editing {attachedWorkflow.name}
          </span>
        )}
        {runIsHere && activeRun.reconnecting && (
          <span className="ml-auto flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-400">
            <Spinner size={10} /> reconnecting…
          </span>
        )}
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto scrollbar-thin">
        {!activeConversationId ? (
          <EmptyState />
        ) : messagesLoading ? (
          <MessagesSkeleton />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 pb-6">
            {messageCount === 0 && !runIsHere && (
              <p className="py-10 text-center text-sm text-zinc-400 dark:text-zinc-500">
                Try: “Send a Slack message when Stripe receives a payment”
              </p>
            )}
            {messages?.map((m) => <MessageBubble key={m.id} message={m} />)}

            {runIsHere && (
              <div className="flex justify-start animate-fade-in">
                <div className="min-w-0 max-w-[85%] flex-1 space-y-2">
                  <Timeline entries={activeRun.timeline} live />
                  {activeRun.streamText && (
                    <div className="whitespace-pre-wrap rounded-2xl rounded-bl-md border border-zinc-200 bg-white px-4 py-2.5 text-sm text-zinc-700 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
                      {activeRun.streamText}
                      <span className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-caret-blink rounded-sm bg-indigo-500" />
                    </div>
                  )}
                  {terminalError && !terminalError.recoverable && (
                    <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-500/40 dark:bg-red-950/50 dark:text-red-300">
                      <AlertIcon size={13} className="mt-0.5 shrink-0" />
                      <span>
                        {terminalError.message}{' '}
                        <span className="opacity-60">({terminalError.code})</span>
                      </span>
                    </div>
                  )}
                  {terminalError?.recoverable && (
                    <div className="flex items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-500/40 dark:bg-amber-950/40 dark:text-amber-300">
                      <Spinner size={12} />
                      {terminalError.message} — retrying…
                    </div>
                  )}
                  {activeRun.status === 'cancelling' && (
                    <p className="flex items-center gap-1.5 text-[11px] text-zinc-400 dark:text-zinc-500">
                      <XIcon size={10} /> stopping the run…
                    </p>
                  )}
                </div>
              </div>
            )}

            {showRetry && (
              <div className="flex justify-start">
                <button
                  onClick={() => void retryLast()}
                  className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium text-zinc-600 transition-colors hover:border-indigo-400 hover:text-indigo-600 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-indigo-500 dark:hover:text-indigo-400"
                >
                  ↻ Try again
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      <Composer />
    </div>
  );
}
