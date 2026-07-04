import { http } from './client';
import type { ConversationSummary, Message } from '../types';

export const createConversation = () =>
  http.post<{ conversation_id: string }>('/conversations');

export const listConversations = () =>
  http.get<ConversationSummary[]>('/conversations');

export const listMessages = (conversationId: string) =>
  http.get<Message[]>(`/conversations/${conversationId}/messages`);

export const sendMessage = (
  conversationId: string,
  content: string,
  workflowId?: string,
) =>
  http.post<{ run_id: string }>(`/conversations/${conversationId}/messages`, {
    content,
    ...(workflowId ? { workflow_id: workflowId } : {}),
  });
