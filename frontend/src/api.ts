import type { Conversation, Job, MediaAsset, ModelResponse, WorkspaceConfig } from './types';

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, apiKey: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (apiKey) headers.set('Authorization', `Bearer ${apiKey}`);
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');

  const response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      message = body.error?.message || message;
    } catch {
      // Keep the status-based fallback for non-JSON proxy/service errors.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  conversations: (key: string) => request<Omit<Conversation, 'messages'>[]>('/api/v1/conversations', key),
  conversation: (key: string, id: string) => request<Conversation>(`/api/v1/conversations/${id}`, key),
  newConversation: (key: string, mediaIds: string[]) => request<Conversation>('/api/v1/conversations', key, { method: 'POST', body: JSON.stringify({ media_ids: mediaIds.length ? mediaIds : null }) }),
  sendMessage: (key: string, id: string, question: string, mediaIds: string[], mode: string) => request<Conversation>(`/api/v1/conversations/${id}/messages`, key, { method: 'POST', body: JSON.stringify({ question, media_ids: mediaIds.length ? mediaIds : null, mode }) }),
  config: (key: string) => request<WorkspaceConfig>('/api/v1/config', key),
  media: (key: string) => request<MediaAsset[]>('/api/v1/media?limit=500', key),
  jobs: (key: string) => request<Job[]>('/api/v1/jobs?limit=500', key),
  upload: (key: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<MediaAsset>('/api/v1/media', key, { method: 'POST', body });
  },
  uploadUrl: (key: string, url: string) =>
    request<MediaAsset>('/api/v1/media/url', key, {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
  process: (key: string, mediaId: string) =>
    request<Job>(`/api/v1/media/${mediaId}/process`, key, { method: 'POST' }),
  remove: (key: string, mediaId: string) =>
    request<void>(`/api/v1/media/${mediaId}`, key, { method: 'DELETE' }),
  ask: (key: string, question: string, mediaIds: string[]) =>
    request<ModelResponse>('/api/v1/query', key, {
      method: 'POST',
      body: JSON.stringify({ question, media_ids: mediaIds.length ? mediaIds : null }),
    }),
  agent: (key: string, question: string, mediaIds: string[]) =>
    request<ModelResponse>('/api/v1/agent/query', key, {
      method: 'POST',
      body: JSON.stringify({ question, media_ids: mediaIds.length ? mediaIds : null }),
    }),
  summarize: (key: string, mediaIds: string[], focus?: string) =>
    request<ModelResponse>('/api/v1/summarize', key, {
      method: 'POST',
      body: JSON.stringify({ media_ids: mediaIds.length ? mediaIds : null, focus: focus || null }),
    }),
  content: async (key: string, mediaId: string) => {
    const headers = new Headers();
    if (key) headers.set('Authorization', `Bearer ${key}`);
    const response = await fetch(`${baseUrl}/api/v1/media/${mediaId}/content`, {
      headers,
    });
    if (!response.ok) throw new ApiError('Could not load source media', response.status);
    return response.blob();
  },
};
