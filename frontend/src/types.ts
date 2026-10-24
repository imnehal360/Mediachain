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

export interface WorkspaceConfig {
  owner: string;
  max_upload_bytes: number;
  formats: string[];
  answer_mode: 'generative' | 'extractive';
}
