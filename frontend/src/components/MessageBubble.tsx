import type { ChatMessage } from '../store/useStore';
import { Timeline } from './Timeline';

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-sm text-white shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const failed = message.runStatus === 'failed';
  const cancelled = message.runStatus === 'cancelled';

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] min-w-0">
        {message.timeline && message.timeline.length > 0 && (
          <Timeline entries={message.timeline} live={false} />
        )}
        {message.content && (
          <div
            className={`whitespace-pre-wrap rounded-2xl rounded-bl-md border px-4 py-2.5 text-sm shadow-sm ${
              failed
                ? 'border-red-200 bg-red-50/50 text-zinc-700 dark:border-red-500/30 dark:bg-red-950/30 dark:text-zinc-300'
                : 'border-zinc-200 bg-white text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200'
            }`}
          >
            {message.content}
          </div>
        )}
        {(failed || cancelled) && (
          <p className={`mt-1 text-[11px] ${failed ? 'text-red-500' : 'text-zinc-400 dark:text-zinc-500'}`}>
            {failed ? 'This run failed — the reply above may be incomplete.' : 'Run cancelled.'}
          </p>
        )}
      </div>
    </div>
  );
}
