import {
  AlertCircle,
  ArrowRight,
  Check,
  Clock3,
  FileAudio,
  FileText,
  FileVideo,
  Library,
  Link2,
  LoaderCircle,
  LogOut,
  MessageSquareText,
  Play,
  Plus,
  Search,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ApiError, api } from './api';
import type { AgentToolCall, Conversation, Job, MediaAsset, ModelResponse, SourceReference, WorkspaceConfig } from './types';

type View = 'library' | 'ask';

const mediaIcon = {
  text: FileText,
  audio: FileAudio,
  video: FileVideo,
};

function displayName(asset: MediaAsset) {
  return String(asset.metadata.original_name || asset.source.split('/').at(-1) || 'Untitled media');
}

function formatTime(seconds: number | null) {
  if (seconds === null) return '';
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${minutes}:${remainder.toString().padStart(2, '0')}`;
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(0)} MB`;
}

function ErrorNotice({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="notice error-notice" role="alert">
      <AlertCircle size={18} />
      <span>{message}</span>
      <button className="icon-button" onClick={onClose} aria-label="Dismiss error"><X size={16} /></button>
    </div>
  );
}

function Connect({ onConnect }: { onConnect: (key: string, config: WorkspaceConfig) => void }) {
  const [key, setKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const config = await api.config(key.trim());
      sessionStorage.setItem('mediachain_api_key', key.trim());
      onConnect(key.trim(), config);
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : 'Could not reach MediaChain');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="connect-page">
      <section className="connect-panel">
        <div className="brand-mark"><span /></div>
        <p className="eyebrow">Media intelligence workspace</p>
        <h1>Find the moment.<br />Keep the evidence.</h1>
        <p className="connect-copy">Connect securely to search, understand, and cite your media.</p>
        <form onSubmit={submit}>
          <label htmlFor="api-key">Workspace API key</label>
          <div className="input-action">
            <input
              id="api-key"
              type="password"
              value={key}
              onChange={(event) => setKey(event.target.value)}
              placeholder="Paste your key"
              autoFocus
              required
            />
            <button className="primary-button square" disabled={busy || !key.trim()} aria-label="Connect">
              {busy ? <LoaderCircle className="spin" size={19} /> : <ArrowRight size={19} />}
            </button>
          </div>
          {error && <p className="field-error">{error}</p>}
        </form>
        <p className="privacy-note">Stored only for this browser session. Provider secrets stay on the server.</p>
      </section>
      <div className="signal" aria-hidden="true"><i /><i /><i /><i /></div>
    </main>
  );
}

function UploadPanel({
  config,
  busy,
  onUpload,
  onUrlUpload,
}: {
  config: WorkspaceConfig;
  busy: boolean;
  onUpload: (file: File) => void;
  onUrlUpload: (url: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [url, setUrl] = useState('');
  const accept = config.formats.join(',');

  function pick(files: FileList | null) {
    if (files?.[0]) onUpload(files[0]);
  }

  return (
    <div className="ingestion-panel">
      <div
      className={`upload-zone ${dragging ? 'dragging' : ''}`}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); pick(event.dataTransfer.files); }}
      >
        <input ref={input} type="file" accept={accept} onChange={(event) => pick(event.target.files)} hidden />
        <div className="upload-icon">{busy ? <LoaderCircle className="spin" /> : <UploadCloud />}</div>
        <div>
          <strong>{busy ? 'Importing media…' : 'Drop media here'}</strong>
          <p>{config.formats.join(' · ')} · up to {formatBytes(config.max_upload_bytes)}</p>
        </div>
        <button className="secondary-button" onClick={() => input.current?.click()} disabled={busy}>
          <Plus size={16} /> Choose file
        </button>
      </div>
      {config.youtube_url_enabled && (
        <form className="url-import" onSubmit={(event) => { event.preventDefault(); if (url.trim()) { onUrlUpload(url.trim()); setUrl(''); } }}>
          <Link2 size={17} />
          <input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="Paste a public YouTube video URL" disabled={busy} required />
          <button className="secondary-button" disabled={busy || !url.trim()}>{busy ? 'Importing…' : 'Add video'}</button>
        </form>
      )}
    </div>
  );
}

function MediaLibrary({
  assets,
  jobs,
  config,
  uploading,
  onUpload,
  onUrlUpload,
  onProcess,
  onDelete,
}: {
  assets: MediaAsset[];
  jobs: Job[];
  config: WorkspaceConfig;
  uploading: boolean;
  onUpload: (file: File) => void;
  onUrlUpload: (url: string) => void;
  onProcess: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [search, setSearch] = useState('');
  const latestJobs = useMemo(() => {
    const result = new Map<string, Job>();
    [...jobs].sort((a, b) => b.created_at - a.created_at).forEach((job) => {
      if (!result.has(job.media_id)) result.set(job.media_id, job);
    });
    return result;
  }, [jobs]);
  const filtered = assets.filter((asset) => displayName(asset).toLowerCase().includes(search.toLowerCase()));

  return (
    <section className="view">
      <header className="view-header">
        <div><p className="eyebrow">Workspace</p><h2>Your media</h2></div>
        <div className="search-box"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search media" /></div>
      </header>
      <UploadPanel config={config} busy={uploading} onUpload={onUpload} onUrlUpload={onUrlUpload} />
      <div className="section-heading"><h3>Library</h3><span>{filtered.length} item{filtered.length === 1 ? '' : 's'}</span></div>
      {filtered.length === 0 ? (
        <div className="empty-state"><Library size={28} /><h3>No media yet</h3><p>Upload your first file to begin.</p></div>
      ) : (
        <div className="media-list">
          {filtered.map((asset) => {
            const Icon = mediaIcon[asset.media_type];
            const job = latestJobs.get(asset.id);
            const processing = job?.status === 'queued' || job?.status === 'running';
            return (
              <article className="media-row" key={asset.id}>
                <div className="file-icon"><Icon size={20} /></div>
                <div className="media-copy">
                  <strong title={displayName(asset)}>{displayName(asset)}</strong>
                  <span>{asset.media_type}{asset.duration ? ` · ${formatTime(asset.duration)}` : ''}</span>
                </div>
                <div className={`status ${job?.status || 'ready'}`}>
                  {processing && <LoaderCircle className="spin" size={13} />}
                  {job?.status === 'completed' && <Check size={13} />}
                  {job?.status === 'failed' && <AlertCircle size={13} />}
                  {job?.status || 'uploaded'}
                </div>
                <div className="row-actions">
                  {job?.status !== 'completed' && (
                    <button className="secondary-button" disabled={processing} onClick={() => onProcess(asset.id)}>
                      <Play size={15} /> Process
                    </button>
                  )}
                  <button className="icon-button danger" onClick={() => onDelete(asset.id)} aria-label={`Delete ${displayName(asset)}`}><Trash2 size={17} /></button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function AskWorkspace({ assets, jobs, apiKey, agentAvailable, focusedId, onRetry }: { assets: MediaAsset[]; jobs: Job[]; apiKey: string; agentAvailable: boolean; focusedId: string | null; onRetry: (id: string) => void }) {
  const [selected, setSelected] = useState<string[]>(focusedId ? [focusedId] : []);
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState<ModelResponse | null>(null);
  const [chat, setChat] = useState<Conversation | null>(null);
  const [conversations, setConversations] = useState<Omit<Conversation, 'messages'>[]>([]);
  const historyEnd = useRef<HTMLDivElement>(null);

  async function openChat(id: string) {
    if (busy) return;
    try {
      const saved = await api.conversation(apiKey, id);
      setChat(saved);
      setSelected(saved.media_ids || []);
      setResponse(saved.messages.at(-1)?.response || null);
      setActiveSource(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not open chat'); }
  }

  useEffect(() => {
    api.conversations(apiKey).then(setConversations).catch(() => setError('Could not load saved conversations'));
  }, [apiKey]);

  useEffect(() => { historyEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [chat?.messages.length]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [activeSource, setActiveSource] = useState<SourceReference | null>(null);
  const [mediaUrl, setMediaUrl] = useState('');
  const [queryMode, setQueryMode] = useState<'quick' | 'agent'>('quick');
  const readyIds = useMemo(() => {
    const latest = new Map<string, Job>();
    [...jobs].sort((a, b) => b.created_at - a.created_at).forEach((job) => {
      if (!latest.has(job.media_id)) latest.set(job.media_id, job);
    });
    return new Set(
      [...latest.entries()]
        .filter(([, job]) => job.status === 'completed')
        .map(([mediaId]) => mediaId),
    );
  }, [jobs]);
  const readyAssets = assets.filter((asset) => readyIds.has(asset.id));
  const waiting = selected.some((id) => !readyIds.has(id));
  const canAsk = readyAssets.length > 0 && !waiting;
  const pendingAssets = assets.filter((asset) => !readyIds.has(asset.id));

  useEffect(() => {
    setSelected(focusedId ? [focusedId] : []);
    setResponse(null);
    setChat(null);
  }, [focusedId]);

  useEffect(() => {
    setSelected((items) => items.filter((id) => assets.some((asset) => asset.id === id)));
  }, [assets]);

  function toggle(id: string) {
    setSelected((items) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]);
  }

  async function run(mode: 'ask' | 'summarize') {
    if (!canAsk || busy) return;
    if (mode === 'ask' && !question.trim()) return;
    setBusy(true);
    setError('');
    setResponse(null);
    setActiveSource(null);
    try {
      const activeChat = chat || await api.newConversation(apiKey, selected);
      setChat(activeChat);
      const updated = await api.sendMessage(apiKey, activeChat.id, question.trim() || 'Summarize the available evidence', selected, mode === 'summarize' ? 'summary' : queryMode);
      setChat(updated);
      setResponse(updated.messages.at(-1)?.response || null);
      setQuestion('');
      api.conversations(apiKey).then(setConversations).catch(() => undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The query failed');
    } finally {
      setBusy(false);
    }
  }

  const sourceAsset = activeSource && assets.find((asset) => asset.id === activeSource.media_id);

  useEffect(() => {
    if (!sourceAsset || sourceAsset.media_type === 'text') {
      setMediaUrl('');
      return;
    }
    let objectUrl = '';
    let cancelled = false;
    api.content(apiKey, sourceAsset.id).then((blob) => {
      if (cancelled) return;
      objectUrl = URL.createObjectURL(blob);
      setMediaUrl(objectUrl);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : 'Could not load source media'));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [apiKey, sourceAsset]);

  return (
    <section className="view ask-view">
      <header className="view-header">
        <div><p className="eyebrow">Grounded intelligence</p><h2>Ask your media</h2></div>
        <span className="mode-pill"><Sparkles size={14} /> {response ? `${response.sources.length} sources` : 'Evidence first'}</span>
      </header>
      <div className="processing-updates" aria-live="polite">
        {pendingAssets.map((asset) => {
          const job = [...jobs].filter((item) => item.media_id === asset.id).sort((a, b) => b.created_at - a.created_at)[0];
          const active = job?.status === 'queued' || job?.status === 'running';
          return <div className="notice" key={asset.id}>
            {active ? <LoaderCircle className="spin" size={18} /> : <AlertCircle size={18} />}
            <span><strong>{displayName(asset)}</strong><br />{active ? 'Preparing your media for questions. Audio and video can take several minutes; keep the server running.' : 'This media is not ready. Try processing it again.'}{job?.error && <small> {job.error}</small>}</span>
            {!active && <button className="secondary-button" onClick={() => onRetry(asset.id)}>Retry processing</button>}
          </div>;
        })}
      </div>
      <div className="conversation-toolbar">
        <button className="secondary-button" disabled={busy} onClick={() => { setChat(null); setResponse(null); setQuestion(''); setActiveSource(null); }}>New chat</button>
        <select aria-label="Saved conversations" disabled={busy} value={chat?.id || ''} onChange={(event) => { if (event.target.value) openChat(event.target.value); }}>
          <option value="">Open a saved conversation</option>
          {conversations.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select>
      </div>
      <div className="ask-grid">
        <aside className="source-picker">
          <div className="section-heading"><h3>Sources</h3><button onClick={() => setSelected(selected.length ? [] : readyAssets.map((a) => a.id))}>{selected.length ? 'Clear' : 'All'}</button></div>
          <p className="picker-help">No selection searches the whole library.</p>
          <div className="source-options">
            {readyAssets.map((asset) => {
              const Icon = mediaIcon[asset.media_type];
              const checked = selected.includes(asset.id);
              return (
                <button className={`source-option ${checked ? 'selected' : ''}`} onClick={() => toggle(asset.id)} key={asset.id}>
                  <Icon size={17} /><span>{displayName(asset)}</span><i>{checked && <Check size={12} />}</i>
                </button>
              );
            })}
          </div>
        </aside>
        <div className="answer-panel">
          <div className="question-box">
            <div className="query-mode" aria-label="Answer mode">
              <button className={queryMode === 'quick' ? 'active' : ''} onClick={() => setQueryMode('quick')}>Quick Answer</button>
              <button className={queryMode === 'agent' ? 'active' : ''} onClick={() => setQueryMode('agent')} disabled={!agentAvailable} title={agentAvailable ? 'Use multiple media tools' : 'A chat model is required'}>Agent Analysis</button>
            </div>
            <p className="picker-help" role="status">{waiting ? 'Your selected media is being prepared. You can type a question now and send it when ready.' : canAsk ? 'Ready to ask. Type a question about your media below.' : 'Upload a file or paste a YouTube link above to get started.'}</p>
            <textarea value={question} maxLength={6000} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question, or enter a focus for the summary…" rows={3} />
            <div className="question-actions">
              <button className="secondary-button" onClick={() => run('summarize')} disabled={busy || !canAsk}><Sparkles size={16} /> Summarize</button>
              <button className="primary-button" onClick={() => run('ask')} disabled={busy || !question.trim() || !canAsk}>
                {busy ? <LoaderCircle className="spin" size={17} /> : <MessageSquareText size={17} />} {queryMode === 'agent' ? 'Analyze' : 'Ask'}
              </button>
            </div>
          </div>
          {error && <ErrorNotice message={error} onClose={() => setError('')} />}
          {!chat?.messages.length && !busy && (
            <div className="answer-empty"><div><span /><span /><span /></div><h3>Answers anchored to evidence</h3><p>Every response points back to the exact source and moment.</p></div>
          )}
          {busy && <div className="answer-empty"><LoaderCircle className="spin" /><h3>{queryMode === 'agent' ? 'Agent is investigating your media…' : 'Searching your evidence…'}</h3></div>}
          <div className="chat-history" role="log" aria-label="Conversation history">
          {chat?.messages.map((message, index) => message.role === 'user' ? <div className="chat-question" key={index}><p className="eyebrow">You</p><p>{message.content}</p></div> : message.response ? (() => {
            const response = message.response;
            const toolCalls = (response.metadata.tool_calls as AgentToolCall[] | undefined) || [];
            return (
            <div className="response" key={index}>
              <p className="eyebrow">Answer</p>
              <div className="answer-text">{response.answer}</div>
              {toolCalls.length > 0 && (
                <div className="agent-activity">
                  <h3>Agent activity</h3>
                  {toolCalls.map((call, index) => (
                    <div key={`${call.tool}-${index}`}><Sparkles size={13} /><span>{call.tool.replaceAll('_', ' ')}</span><small>{call.result_count} result{call.result_count === 1 ? '' : 's'}</small></div>
                  ))}
                </div>
              )}
              {response.sources.length > 0 && (
                <div className="citations">
                  <h3>Evidence</h3>
                  {response.sources.map((source, index) => (
                    <button key={`${source.document_id}-${index}`} onClick={() => setActiveSource(source)}>
                      <span>{index + 1}</span>
                      <div><strong>{assets.find((asset) => asset.id === source.media_id) ? displayName(assets.find((asset) => asset.id === source.media_id)!) : 'Source'}</strong><small>{source.modality}{source.start_time !== null ? ` · ${formatTime(source.start_time)}` : ''}</small></div>
                      <ArrowRight size={15} />
                    </button>
                  ))}
                </div>
              )}
            </div>
          ); })() : null)}
          {busy && <div className="chat-question"><p className="eyebrow">You</p><p>{question || 'Summarize the available evidence'}</p></div>}
          <div ref={historyEnd} />
          </div>
        </div>
      </div>
      {activeSource && sourceAsset && (
        <div className="source-drawer">
          <div className="drawer-head"><div><p className="eyebrow">Evidence source</p><h3>{displayName(sourceAsset)}</h3></div><button className="icon-button" onClick={() => setActiveSource(null)}><X /></button></div>
          <div className="source-meta"><span>{activeSource.modality}</span>{activeSource.start_time !== null && <span><Clock3 size={14} /> {formatTime(activeSource.start_time)}–{formatTime(activeSource.end_time)}</span>}</div>
          {sourceAsset.media_type !== 'text' && !mediaUrl && <div className="media-loading"><LoaderCircle className="spin" /> Loading media…</div>}
          {sourceAsset.media_type === 'video' && mediaUrl && <video controls src={mediaUrl + `#t=${activeSource.start_time || 0}`} />}
          {sourceAsset.media_type === 'audio' && mediaUrl && <audio controls src={mediaUrl + `#t=${activeSource.start_time || 0}`} />}
          {sourceAsset.media_type === 'text' && <p className="text-source-note">Open the indexed evidence entry from the citation above. Text originals are kept private behind the authenticated API.</p>}
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [config, setConfig] = useState<WorkspaceConfig | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [view, setView] = useState<View>('ask');
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async (key = apiKey) => {
    if (key === null) return;
    const [nextAssets, nextJobs] = await Promise.all([api.media(key), api.jobs(key)]);
    setAssets(nextAssets);
    setJobs(nextJobs);
  }, [apiKey]);

  useEffect(() => {
    async function connect() {
      try {
        const next = await api.config('');
        setApiKey('');
        setConfig(next);
        return;
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 401) return;
      }
      const saved = sessionStorage.getItem('mediachain_api_key');
      if (!saved) return;
      try {
        const next = await api.config(saved);
        setApiKey(saved);
        setConfig(next);
      } catch {
        sessionStorage.removeItem('mediachain_api_key');
      }
    }
    connect().finally(() => setInitializing(false));
  }, []);

  useEffect(() => {
    if (apiKey === null) return;
    refresh().catch((reason) => setError(reason instanceof Error ? reason.message : 'Could not load workspace'));
  }, [apiKey, refresh]);

  useEffect(() => {
    if (!jobs.some((job) => job.status === 'queued' || job.status === 'running')) return;
    const timer = window.setInterval(() => refresh().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, [jobs, refresh]);

  async function upload(file: File) {
    if (apiKey === null) return;
    setUploading(true);
    setError('');
    try {
      const asset = await api.upload(apiKey, file);
      setAssets((items) => [asset, ...items.filter((item) => item.id !== asset.id)]);
      setFocusedId(asset.id);
      setView('ask');
      const job = await api.process(apiKey, asset.id);
      setJobs((items) => [job, ...items]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  async function uploadUrl(url: string) {
    if (apiKey === null) return;
    setUploading(true);
    setError('');
    try {
      const asset = await api.uploadUrl(apiKey, url);
      setAssets((items) => [asset, ...items.filter((item) => item.id !== asset.id)]);
      setFocusedId(asset.id);
      setView('ask');
      const job = await api.process(apiKey, asset.id);
      setJobs((items) => [job, ...items]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'YouTube import failed');
    } finally {
      setUploading(false);
    }
  }

  async function process(id: string) {
    if (apiKey === null) return;
    try {
      const job = await api.process(apiKey, id);
      setJobs((items) => [job, ...items]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not start processing');
    }
  }

  async function remove(id: string) {
    if (apiKey === null) return;
    if (!window.confirm('Delete this media and its indexed evidence?')) return;
    try {
      await api.remove(apiKey, id);
      setAssets((items) => items.filter((item) => item.id !== id));
      setJobs((items) => items.filter((item) => item.media_id !== id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Delete failed');
    }
  }

  function disconnect() {
    sessionStorage.removeItem('mediachain_api_key');
    setApiKey(null);
    setConfig(null);
    setAssets([]);
    setJobs([]);
  }

  if (initializing) return <main className="connect-page"><LoaderCircle className="spin" aria-label="Connecting" /></main>;
  if (apiKey === null || !config) return <Connect onConnect={(key, next) => { setApiKey(key); setConfig(next); }} />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="wordmark"><div className="brand-mark small"><span /></div><strong>MediaChain</strong></div>
        <nav>
          <button className={view === 'library' ? 'active' : ''} onClick={() => setView('library')}><Library size={19} /> Library</button>
          <button className={view === 'ask' ? 'active' : ''} onClick={() => setView('ask')}><MessageSquareText size={19} /> Ask</button>
        </nav>
        <div className="sidebar-foot">
          <div className="connection"><i /><div><span>Connected</span><small>{config.owner}</small></div></div>
          {config.authentication_required && <button className="logout" onClick={disconnect}><LogOut size={17} /> Disconnect</button>}
        </div>
      </aside>
      <div className="mobile-bar"><div className="wordmark"><div className="brand-mark small"><span /></div><strong>MediaChain</strong></div>{config.authentication_required && <button className="icon-button" onClick={disconnect}><LogOut size={18} /></button>}</div>
      <main className="workspace">
        {error && <ErrorNotice message={error} onClose={() => setError('')} />}
        {view === 'library' ? (
          <MediaLibrary assets={assets} jobs={jobs} config={config} uploading={uploading} onUpload={upload} onUrlUpload={uploadUrl} onProcess={process} onDelete={remove} />
        ) : <>
          <div className="section-heading"><div><h2>Upload or paste a link. Then ask.</h2><p className="picker-help">1. Add media · 2. We prepare it automatically · 3. Ask questions with sources</p></div></div>
          <UploadPanel config={config} busy={uploading} onUpload={upload} onUrlUpload={uploadUrl} />
          <AskWorkspace assets={assets} jobs={jobs} apiKey={apiKey} agentAvailable={config.agent_available} focusedId={focusedId} onRetry={process} />
        </>}
      </main>
      <nav className="mobile-nav"><button className={view === 'library' ? 'active' : ''} onClick={() => setView('library')}><Library size={19} />Library</button><button className={view === 'ask' ? 'active' : ''} onClick={() => setView('ask')}><MessageSquareText size={19} />Ask</button></nav>
    </div>
  );
}
