import { useEffect, useRef, type KeyboardEvent } from 'react';
import { useStore } from '../store/useStore';
import { SendIcon, Spinner, StopIcon } from './icons';

export function Composer() {
  const draft = useStore((s) => s.composerDraft);
  const setDraft = useStore((s) => s.setComposerDraft);
  const send = useStore((s) => s.send);
  const activeRun = useStore((s) => s.activeRun);
  const cancelActiveRun = useStore((s) => s.cancelActiveRun);
  const activeConversationId = useStore((s) => s.activeConversationId);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const running = activeRun !== null;

  // Keep keyboard focus on the composer when switching chats or when a run ends.
  useEffect(() => {
    if (!running) textareaRef.current?.focus();
  }, [running, activeConversationId]);

  const submit = () => {
    if (running) return;
    void send(draft);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="border-t border-zinc-200 bg-zinc-50/60 p-3 dark:border-zinc-800 dark:bg-zinc-900/40">
      <div className="flex items-end gap-2 rounded-xl border border-zinc-300 bg-white p-2 shadow-sm focus-within:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-900 dark:focus-within:border-indigo-500">
        <textarea
          ref={textareaRef}
          rows={Math.min(6, Math.max(1, draft.split('\n').length))}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={running}
          placeholder={
            running
              ? 'The agent is working — you can stop it with the button →'
              : 'Describe the automation you want… (Enter to send, Shift+Enter for a new line)'
          }
          className="max-h-40 flex-1 resize-none bg-transparent px-1.5 py-1 text-sm outline-none placeholder:text-zinc-400 disabled:opacity-60 dark:placeholder:text-zinc-500"
        />
        {running ? (
          <button
            onClick={() => void cancelActiveRun()}
            disabled={activeRun?.status === 'cancelling'}
            title="Stop this run"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-600 text-white transition-colors hover:bg-red-500 disabled:opacity-60"
          >
            {activeRun?.status === 'cancelling' ? <Spinner size={14} /> : <StopIcon size={14} />}
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!draft.trim()}
            title="Send (Enter)"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white transition-colors hover:bg-indigo-500 disabled:opacity-40"
          >
            <SendIcon size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
