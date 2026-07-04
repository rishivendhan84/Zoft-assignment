import { create } from 'zustand';
import {
  createConversation,
  listConversations,
  listMessages,
  sendMessage,
} from '../api/conversations';
import { getDiff, getVersion, getWorkflow, listVersions, listWorkflows } from '../api/workflows';
import { cancelRun } from '../api/runs';
import { checkHealth } from '../api/health';
import { ApiError } from '../api/client';
import { openRunStream } from '../sse/runStream';
import {
  emptyHighlights,
  highlightsFromOperations,
  type GraphHighlights,
} from '../lib/diff';
import type {
  ConversationSummary,
  Graph,
  Message,
  OperationDiff,
  RunErrorEvent,
  RunStatus,
  StepEvent,
  ValidationEvent,
  VersionSummary,
  Workflow,
  WorkflowNode,
  WorkflowSummary,
} from '../types';

// ---------------------------------------------------------------------------
// Local UI models
// ---------------------------------------------------------------------------

export type TimelineEntry =
  | ({ kind: 'step'; entryId: number } & StepEvent)
  | ({ kind: 'validation'; entryId: number } & ValidationEvent)
  | ({ kind: 'error'; entryId: number } & RunErrorEvent);

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  run_id?: string;
  /** Timeline of the run that produced this assistant message (in-memory only). */
  timeline?: TimelineEntry[];
  runStatus?: RunStatus;
};

export type ActiveRun = {
  runId: string;
  conversationId: string;
  status: 'streaming' | 'cancelling';
  timeline: TimelineEntry[];
  streamText: string;
  /** Final content from the `message` event, if it has arrived. */
  finalContent?: string;
  /** Last error event; recoverable errors show a "Retrying…" banner. */
  error?: RunErrorEvent;
  reconnecting: boolean;
};

export type Toast = { id: number; kind: 'error' | 'success' | 'info'; text: string };

export type VersionPreview = {
  versionId: string;
  graph: Graph;
  highlights: GraphHighlights;
  ghosts: WorkflowNode[];
  /** Set when the preview was produced by a diff request. */
  diff?: OperationDiff;
};

type StoreState = {
  // health / theme / toasts
  backendUp: boolean | null;
  theme: 'dark' | 'light';
  toasts: Toast[];

  // conversations & chat
  conversations: ConversationSummary[];
  conversationsLoading: boolean;
  activeConversationId: string | null;
  messages: Record<string, ChatMessage[]>;
  messagesLoading: boolean;
  composerDraft: string;
  activeRun: ActiveRun | null;

  // workflows & versions
  workflows: WorkflowSummary[];
  workflowsLoading: boolean;
  activeWorkflowId: string | null;
  activeWorkflow: Workflow | null;
  workflowLoading: boolean;
  /** Highlights from a live `workflow_updated` event; fade after a few seconds. */
  liveHighlights: GraphHighlights;
  liveGhosts: WorkflowNode[];
  versions: VersionSummary[];
  versionsLoading: boolean;
  panelTab: 'canvas' | 'versions';
  preview: VersionPreview | null;
  diffFrom: string | null;
  diffTo: string | null;
  diffLoading: boolean;

  // actions
  init: () => void;
  toggleTheme: () => void;
  pushToast: (kind: Toast['kind'], text: string) => void;
  dismissToast: (id: number) => void;

  refreshConversations: () => Promise<void>;
  newConversation: () => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  setComposerDraft: (draft: string) => void;
  send: (content: string) => Promise<void>;
  retryLast: () => Promise<void>;
  cancelActiveRun: () => Promise<void>;

  refreshWorkflows: () => Promise<void>;
  selectWorkflow: (id: string) => Promise<void>;
  detachWorkflow: () => void;
  setPanelTab: (tab: 'canvas' | 'versions') => void;
  previewVersion: (versionId: string) => Promise<void>;
  clearPreview: () => void;
  setDiffSelection: (which: 'from' | 'to', versionId: string | null) => void;
  loadDiff: () => Promise<void>;
};

// Module-level run plumbing (not reactive state).
let closeActiveStream: (() => void) | null = null;
let highlightTimer: ReturnType<typeof setTimeout> | null = null;
let toastSeq = 0;
let entrySeq = 0;
let initialized = false; // guards React 18 StrictMode double-invoked effects

const errorText = (e: unknown): string =>
  e instanceof ApiError ? e.message : 'Something went wrong';

export const useStore = create<StoreState>((set, get) => ({
  backendUp: null,
  theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
  toasts: [],

  conversations: [],
  conversationsLoading: true,
  activeConversationId: null,
  messages: {},
  messagesLoading: false,
  composerDraft: '',
  activeRun: null,

  workflows: [],
  workflowsLoading: true,
  activeWorkflowId: null,
  activeWorkflow: null,
  workflowLoading: false,
  liveHighlights: emptyHighlights(),
  liveGhosts: [],
  versions: [],
  versionsLoading: false,
  panelTab: 'canvas',
  preview: null,
  diffFrom: null,
  diffTo: null,
  diffLoading: false,

  init: () => {
    if (initialized) return;
    initialized = true;
    void get().refreshConversations();
    void get().refreshWorkflows();
    const poll = async () => set({ backendUp: await checkHealth() });
    void poll();
    setInterval(() => void poll(), 30_000);
  },

  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark';
    document.documentElement.classList.toggle('dark', next === 'dark');
    try {
      localStorage.setItem('theme', next);
    } catch {
      // storage unavailable — theme just won't persist
    }
    set({ theme: next });
  },

  pushToast: (kind, text) => {
    const id = ++toastSeq;
    set((s) => ({ toasts: [...s.toasts, { id, kind, text }] }));
    setTimeout(() => get().dismissToast(id), 5000);
  },

  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  refreshConversations: async () => {
    try {
      const conversations = await listConversations();
      set({ conversations, conversationsLoading: false });
    } catch (e) {
      set({ conversationsLoading: false });
      get().pushToast('error', `Couldn't load conversations: ${errorText(e)}`);
    }
  },

  newConversation: async () => {
    try {
      const { conversation_id } = await createConversation();
      const summary: ConversationSummary = {
        id: conversation_id,
        created_at: new Date().toISOString(),
      };
      set((s) => ({
        conversations: [summary, ...s.conversations],
        activeConversationId: conversation_id,
        messages: { ...s.messages, [conversation_id]: [] },
      }));
    } catch (e) {
      get().pushToast('error', `Couldn't create conversation: ${errorText(e)}`);
    }
  },

  selectConversation: async (id) => {
    set({ activeConversationId: id, messagesLoading: get().messages[id] === undefined });
    const conv = get().conversations.find((c) => c.id === id);
    if (conv?.workflow_id && conv.workflow_id !== get().activeWorkflowId) {
      void get().selectWorkflow(conv.workflow_id);
    }
    try {
      const history = await listMessages(id);
      // Merge: server history wins for persisted messages. In-memory run
      // timelines are re-attached by message id or (for locally finalized
      // replies) by run_id.
      const existing = get().messages[id] ?? [];
      const byId = new Map(existing.filter((m) => m.timeline).map((m) => [m.id, m] as const));
      const byRunId = new Map(
        existing.filter((m) => m.run_id && m.timeline).map((m) => [m.run_id as string, m] as const),
      );
      const merged: ChatMessage[] = history.map((m: Message) => {
        const local = byId.get(m.id) ?? (m.run_id ? byRunId.get(m.run_id) : undefined);
        return { ...m, timeline: local?.timeline, runStatus: local?.runStatus };
      });
      // Keep local-only messages the server doesn't know about (e.g. a failed
      // run's partial reply) — but drop optimistic user bubbles and any local
      // reply whose run the server has since persisted.
      const serverIds = new Set(history.map((m) => m.id));
      const serverRunIds = new Set(history.map((m) => m.run_id).filter(Boolean));
      const localOnly = existing.filter(
        (m) =>
          !serverIds.has(m.id) &&
          !m.id.startsWith('local-') &&
          !(m.run_id && serverRunIds.has(m.run_id)),
      );
      set((s) => ({
        messages: { ...s.messages, [id]: [...merged, ...localOnly] },
        messagesLoading: false,
      }));
    } catch (e) {
      set({ messagesLoading: false });
      get().pushToast('error', `Couldn't load messages: ${errorText(e)}`);
    }
  },

  setComposerDraft: (composerDraft) => set({ composerDraft }),

  send: async (content) => {
    const trimmed = content.trim();
    if (!trimmed || get().activeRun) return;

    let cid = get().activeConversationId;
    if (!cid) {
      try {
        const { conversation_id } = await createConversation();
        cid = conversation_id;
        const summary: ConversationSummary = {
          id: conversation_id,
          created_at: new Date().toISOString(),
        };
        set((s) => ({
          conversations: [summary, ...s.conversations],
          activeConversationId: conversation_id,
          messages: { ...s.messages, [conversation_id]: [] },
        }));
      } catch (e) {
        get().pushToast('error', `Couldn't start a conversation: ${errorText(e)}`);
        return;
      }
    }
    const conversationId = cid;

    const optimistic: ChatMessage = {
      id: `local-${Date.now()}`,
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    set((s) => ({
      composerDraft: '',
      messages: {
        ...s.messages,
        [conversationId]: [...(s.messages[conversationId] ?? []), optimistic],
      },
    }));

    const conv = get().conversations.find((c) => c.id === conversationId);
    const workflowId = conv?.workflow_id ?? get().activeWorkflowId ?? undefined;

    let runId: string;
    try {
      ({ run_id: runId } = await sendMessage(conversationId, trimmed, workflowId));
    } catch (e) {
      // REST-level failure: remove the optimistic bubble, restore the draft.
      set((s) => ({
        composerDraft: trimmed,
        messages: {
          ...s.messages,
          [conversationId]: (s.messages[conversationId] ?? []).filter(
            (m) => m.id !== optimistic.id,
          ),
        },
      }));
      get().pushToast('error', `Message not sent: ${errorText(e)}`);
      return;
    }

    set({
      activeRun: {
        runId,
        conversationId,
        status: 'streaming',
        timeline: [],
        streamText: '',
        reconnecting: false,
      },
    });

    const patchRun = (fn: (run: ActiveRun) => Partial<ActiveRun>) =>
      set((s) => (s.activeRun ? { activeRun: { ...s.activeRun, ...fn(s.activeRun) } } : {}));

    closeActiveStream?.();
    closeActiveStream = openRunStream(runId, {
      onStep: (e) =>
        patchRun((run) => ({
          timeline: [...run.timeline, { kind: 'step', entryId: ++entrySeq, ...e }],
        })),

      onToken: (e) => patchRun((run) => ({ streamText: run.streamText + e.text })),

      onValidation: (e) =>
        patchRun((run) => {
          const last = run.timeline[run.timeline.length - 1];
          // A passed/failed result settles the preceding "running" row in place.
          if (e.status !== 'running' && last?.kind === 'validation' && last.status === 'running') {
            return {
              timeline: [
                ...run.timeline.slice(0, -1),
                { ...last, status: e.status, errors: e.errors },
              ],
            };
          }
          return {
            timeline: [...run.timeline, { kind: 'validation', entryId: ++entrySeq, ...e }],
          };
        }),

      onWorkflowUpdated: (e) => {
        const prev = get().activeWorkflow;
        const highlights = highlightsFromOperations(e.operations);
        const ghosts =
          prev && prev.id === e.workflow_id
            ? prev.graph.nodes.filter((n) => highlights.removedNodes.has(n.id))
            : [];
        const known = get().workflows.find((w) => w.id === e.workflow_id);
        set((s) => ({
          activeWorkflowId: e.workflow_id,
          activeWorkflow: {
            id: e.workflow_id,
            name: known?.name ?? prev?.name ?? 'Workflow',
            current_version_id: e.version_id,
            updated_at: new Date().toISOString(),
            graph: e.graph,
          },
          liveHighlights: highlights,
          liveGhosts: ghosts,
          preview: null,
          panelTab: 'canvas',
          // Bind the conversation to the (possibly new) workflow so follow-up
          // messages target it.
          conversations: s.conversations.map((c) =>
            c.id === conversationId ? { ...c, workflow_id: e.workflow_id } : c,
          ),
        }));
        if (highlightTimer) clearTimeout(highlightTimer);
        highlightTimer = setTimeout(
          () => set({ liveHighlights: emptyHighlights(), liveGhosts: [] }),
          6000,
        );
        // Keep sidebar + version history fresh (fire-and-forget).
        void get().refreshWorkflows();
        void listVersions(e.workflow_id)
          .then((versions) => {
            if (get().activeWorkflowId === e.workflow_id) set({ versions });
          })
          .catch(() => undefined);
      },

      onMessage: (e) => patchRun(() => ({ finalContent: e.content })),

      onError: (e) =>
        patchRun((run) => ({
          error: e,
          timeline: [...run.timeline, { kind: 'error', entryId: ++entrySeq, ...e }],
        })),

      onDone: (e) => {
        closeActiveStream?.();
        closeActiveStream = null;
        const run = get().activeRun;
        if (!run || run.runId !== e.run_id) {
          set({ activeRun: null });
          return;
        }
        const content =
          run.finalContent ??
          run.streamText ??
          '';
        const assistant: ChatMessage | null =
          content || run.timeline.length > 0
            ? {
                id: `run-${run.runId}`,
                role: 'assistant',
                content,
                created_at: new Date().toISOString(),
                run_id: run.runId,
                timeline: run.timeline,
                runStatus: e.status,
              }
            : null;
        set((s) => ({
          activeRun: null,
          messages: assistant
            ? {
                ...s.messages,
                [run.conversationId]: [...(s.messages[run.conversationId] ?? []), assistant],
              }
            : s.messages,
        }));
        // Titles are often derived server-side from the first message.
        void get().refreshConversations();
      },

      onConnectionChange: (connected) =>
        set((s) =>
          s.activeRun && s.activeRun.reconnecting === connected
            ? { activeRun: { ...s.activeRun, reconnecting: !connected } }
            : {},
        ),
    });
  },

  retryLast: async () => {
    const cid = get().activeConversationId;
    if (!cid) return;
    const lastUser = [...(get().messages[cid] ?? [])].reverse().find((m) => m.role === 'user');
    if (lastUser) await get().send(lastUser.content);
  },

  cancelActiveRun: async () => {
    const run = get().activeRun;
    if (!run || run.status === 'cancelling') return;
    set({ activeRun: { ...run, status: 'cancelling' } });
    try {
      await cancelRun(run.runId);
      // UI settles when the stream delivers done{status:'cancelled'}.
    } catch (e) {
      set((s) =>
        s.activeRun ? { activeRun: { ...s.activeRun, status: 'streaming' } } : {},
      );
      get().pushToast('error', `Couldn't cancel: ${errorText(e)}`);
    }
  },

  refreshWorkflows: async () => {
    try {
      const workflows = await listWorkflows();
      set({ workflows, workflowsLoading: false });
    } catch (e) {
      set({ workflowsLoading: false });
      get().pushToast('error', `Couldn't load workflows: ${errorText(e)}`);
    }
  },

  selectWorkflow: async (id) => {
    set({
      activeWorkflowId: id,
      workflowLoading: true,
      preview: null,
      diffFrom: null,
      diffTo: null,
      liveHighlights: emptyHighlights(),
      liveGhosts: [],
      versions: [],
      versionsLoading: true,
    });
    try {
      const [workflow, versions] = await Promise.all([getWorkflow(id), listVersions(id)]);
      if (get().activeWorkflowId !== id) return; // stale response
      set({ activeWorkflow: workflow, versions, workflowLoading: false, versionsLoading: false });
    } catch (e) {
      if (get().activeWorkflowId !== id) return;
      set({ workflowLoading: false, versionsLoading: false });
      get().pushToast('error', `Couldn't load workflow: ${errorText(e)}`);
    }
  },

  detachWorkflow: () =>
    set({
      activeWorkflowId: null,
      activeWorkflow: null,
      versions: [],
      preview: null,
      diffFrom: null,
      diffTo: null,
      liveHighlights: emptyHighlights(),
      liveGhosts: [],
    }),

  setPanelTab: (panelTab) => set({ panelTab }),

  previewVersion: async (versionId) => {
    const wfId = get().activeWorkflowId;
    if (!wfId) return;
    try {
      const version = await getVersion(wfId, versionId);
      set({
        panelTab: 'canvas', // jump to the graph of the selected version
        preview: {
          versionId,
          graph: version.graph,
          highlights: emptyHighlights(),
          ghosts: [],
        },
        diffFrom: null,
        diffTo: null,
      });
    } catch (e) {
      get().pushToast('error', `Couldn't load version: ${errorText(e)}`);
    }
  },

  clearPreview: () => set({ preview: null, diffFrom: null, diffTo: null }),

  setDiffSelection: (which, versionId) =>
    set(which === 'from' ? { diffFrom: versionId } : { diffTo: versionId }),

  loadDiff: async () => {
    const { activeWorkflowId: wfId, diffFrom, diffTo } = get();
    if (!wfId || !diffFrom || !diffTo || diffFrom === diffTo) return;
    set({ diffLoading: true });
    try {
      const [diff, toVersion, fromVersion] = await Promise.all([
        getDiff(wfId, diffFrom, diffTo),
        getVersion(wfId, diffTo),
        getVersion(wfId, diffFrom),
      ]);
      const highlights = highlightsFromOperations(diff.operations);
      const ghosts = fromVersion.graph.nodes.filter((n) => highlights.removedNodes.has(n.id));
      set({
        diffLoading: false,
        panelTab: 'canvas', // show the highlighted graph alongside the changelog
        preview: { versionId: diffTo, graph: toVersion.graph, highlights, ghosts, diff },
      });
    } catch (e) {
      set({ diffLoading: false });
      get().pushToast('error', `Couldn't compute diff: ${errorText(e)}`);
    }
  },
}));
