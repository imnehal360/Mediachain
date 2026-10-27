export type Modality = 'text' | 'audio' | 'video';

export interface MediaAsset {
  id: string;
  source: string;
  media_type: Modality;
  content_hash: string;
  owner_id: string;
  duration: number | null;
  metadata: Record<string, unknown>;
}

export interface Job {
  id: string;
  media_id: string;
  owner_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  error: string | null;
  created_at: number;
}

export interface SourceReference {
  media_id: string;
  document_id: string;
  source: string;
  modality: Modality;
  start_time: number | null;
  end_time: number | null;
}

export interface ModelResponse {
  answer: string;
  sources: SourceReference[];
  insufficient_evidence: boolean;
  token_usage: number | null;
  metadata: Record<string, unknown>;
}

export interface AgentToolCall {
  tool: string;
  arguments: Record<string, unknown>;
  result_count: number;
}

export interface WorkspaceConfig {
  owner: string;
  authentication_required: boolean;
  agent_available: boolean;
  max_upload_bytes: number;
  max_remote_bytes: number;
  max_remote_duration_seconds: number;
  youtube_url_enabled: boolean;
  formats: string[];
  answer_mode: 'generative' | 'extractive';
}
