import { runEventsUrl } from '../api/runs';
import type {
  DoneEvent,
  MessageEvent as RunMessageEvent,
  RunErrorEvent,
  StepEvent,
  TokenEvent,
  ValidationEvent,
  WorkflowUpdatedEvent,
} from '../types';

export type RunStreamHandlers = {
  onStep: (e: StepEvent) => void;
  onToken: (e: TokenEvent) => void;
  onValidation: (e: ValidationEvent) => void;
  onWorkflowUpdated: (e: WorkflowUpdatedEvent) => void;
  onMessage: (e: RunMessageEvent) => void;
  onError: (e: RunErrorEvent) => void;
  onDone: (e: DoneEvent) => void;
  /** Transport-level connectivity (not run failures). */
  onConnectionChange: (connected: boolean) => void;
};

/**
 * Opens the SSE stream for a run using the native EventSource:
 * - named events via addEventListener (the contract never uses unnamed `message` frames —
 *   `message` here is a *named* event type);
 * - auto-reconnect with `Last-Event-ID` is built into EventSource, so resume-after-drop
 *   is free. Because replay is at-least-once, events carrying an `id` are deduplicated;
 * - the stream is closed by the caller on the (exactly one) `done` event.
 *
 * Returns a close function.
 */
export function openRunStream(runId: string, handlers: RunStreamHandlers): () => void {
  const source = new EventSource(runEventsUrl(runId));

  // At-least-once replay dedupe: track seen SSE ids (bounded by one run's events).
  const seenIds = new Set<string>();
  const isDuplicate = (e: Event): boolean => {
    const id = (e as globalThis.MessageEvent).lastEventId;
    if (!id) return false;
    if (seenIds.has(id)) return true;
    seenIds.add(id);
    return false;
  };

  function on<T>(type: string, handler: (data: T) => void) {
    source.addEventListener(type, (e) => {
      if (isDuplicate(e)) return;
      handlers.onConnectionChange(true);
      let data: T;
      try {
        data = JSON.parse((e as globalThis.MessageEvent).data) as T;
      } catch {
        return; // malformed frame — ignore rather than crash the run UI
      }
      handler(data);
    });
  }

  on<StepEvent>('step', handlers.onStep);
  on<TokenEvent>('token', handlers.onToken);
  on<ValidationEvent>('validation', handlers.onValidation);
  on<WorkflowUpdatedEvent>('workflow_updated', handlers.onWorkflowUpdated);
  on<RunMessageEvent>('message', handlers.onMessage);
  on<RunErrorEvent>('error', handlers.onError);
  on<DoneEvent>('done', handlers.onDone);

  source.onopen = () => handlers.onConnectionChange(true);
  // EventSource retries automatically; we only surface "reconnecting…" state.
  source.onerror = () => handlers.onConnectionChange(false);

  return () => source.close();
}
