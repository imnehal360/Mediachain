import { expect, test, type Page } from '@playwright/test';
import type { Conversation, ModelResponse } from '../src/types';

const asset = {
  id: 'media-1',
  source: '/managed/note.txt',
  media_type: 'text',
  content_hash: 'hash',
  owner_id: 'tester',
  duration: null,
  metadata: { original_name: 'research-notes.txt' },
};

const completedJob = {
  id: 'job-1',
  media_id: asset.id,
  owner_id: 'tester',
  status: 'completed',
  error: null,
  created_at: 2,
};

async function mockApi(page: Page, withMedia = false) {
  const chats: Conversation[] = [];
  let uploaded = withMedia;
  let processed = withMedia;
  await page.route('**/api/v1/**', async (route) => {
    let path = new URL(route.request().url()).pathname;
    let active: Conversation | undefined;
    let turn: { question: string; media_ids: string[] | null; mode: string } | undefined;
    if (path === '/api/v1/conversations') {
      if (route.request().method() === 'POST') {
        const chat: Conversation = { id: `chat-${chats.length + 1}`, title: 'New chat', media_ids: route.request().postDataJSON().media_ids, messages: [], updated_at: Date.now() };
        chats.push(chat);
        return route.fulfill({ status: 201, json: chat });
      }
      return route.fulfill({ json: chats.map(({ messages, ...chat }) => chat) });
    }
    if (path.startsWith('/api/v1/conversations/')) {
      active = chats.find((chat) => chat.id === path.split('/')[4]);
      if (!active) return route.fulfill({ status: 404 });
      if (!path.endsWith('/messages')) return route.fulfill({ json: active });
      turn = route.request().postDataJSON();
      path = turn!.mode === 'agent' ? '/api/v1/agent/query' : turn!.mode === 'summary' ? '/api/v1/summarize' : '/api/v1/query';
    }
    function answer(result: ModelResponse) {
      if (!active || !turn) return route.fulfill({ json: result });
      active.title = active.messages.length ? active.title : turn.question;
      active.media_ids = turn.media_ids;
      active.messages.push({ role: 'user', content: turn.question, created_at: Date.now() }, { role: 'assistant', content: result.answer, response: result, created_at: Date.now() });
      return route.fulfill({ json: active });
    }
    if (path === '/api/v1/config') {
      if (route.request().headers().authorization !== 'Bearer test-key') {
        return route.fulfill({ status: 401, json: { error: { message: 'Authentication required' } } });
      }
      return route.fulfill({ json: { owner: 'tester', authentication_required: true, agent_available: true, youtube_url_enabled: true, max_upload_bytes: 104857600, max_remote_bytes: 524288000, max_remote_duration_seconds: 14400, formats: ['.txt', '.md'], answer_mode: 'extractive' } });
    }
    if (path === '/api/v1/media' && route.request().method() === 'GET') {
      return route.fulfill({ json: uploaded ? [asset] : [] });
    }
    if (path === '/api/v1/media' && route.request().method() === 'POST') {
      uploaded = true;
      return route.fulfill({ status: 201, json: asset });
    }
    if (path === '/api/v1/media/url' && route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({ url: 'https://youtu.be/abcdefghijk' });
      uploaded = true;
      return route.fulfill({ status: 201, json: { ...asset, metadata: { original_name: 'podcast.mp4', remote_provider: 'youtube' } } });
    }
    if (path === `/api/v1/media/${asset.id}/process`) {
      processed = true;
      return route.fulfill({ status: 202, json: { ...completedJob, status: 'queued' } });
    }
    if (path === `/api/v1/media/${asset.id}` && route.request().method() === 'DELETE') {
      uploaded = false;
      processed = false;
      return route.fulfill({ status: 204, body: '' });
    }
    if (path === '/api/v1/jobs') return route.fulfill({ json: processed ? [completedJob] : [] });
    if (path === '/api/v1/query') {
      return answer({ answer: 'The notes describe grounded retrieval.', sources: [{ media_id: asset.id, document_id: 'doc-1', source: asset.source, modality: 'text', start_time: null, end_time: null }], insufficient_evidence: false, token_usage: null, metadata: {} });
    }
    if (path === '/api/v1/agent/query') {
      return answer({ answer: 'The agent compared the available evidence.', sources: [{ media_id: asset.id, document_id: 'doc-1', source: asset.source, modality: 'text', start_time: null, end_time: null }], insufficient_evidence: false, token_usage: 12, metadata: { mode: 'agentic', tool_calls: [{ tool: 'search_text', arguments: { query: 'evidence' }, result_count: 1 }] } });
    }
    if (path === '/api/v1/summarize') {
      return answer({ answer: 'A grounded summary of the notes.', sources: [{ media_id: asset.id, document_id: 'doc-1', source: asset.source, modality: 'text', start_time: null, end_time: null }], insufficient_evidence: false, token_usage: null, metadata: {} });
    }
    return route.fulfill({ status: 404, json: { error: { message: 'Not found' } } });
  });
}

async function connect(page: Page) {
  await page.goto('/');
  await page.getByLabel('Workspace API key').fill('test-key');
  await page.getByRole('button', { name: 'Connect' }).click();
  await expect(page.getByRole('heading', { name: 'Upload or paste a link. Then ask.' })).toBeVisible();
}

test('connects and shows a clear empty library', async ({ page }, testInfo) => {
  await mockApi(page);
  await connect(page);
  await expect(page.getByRole('heading', { name: 'Upload or paste a link. Then ask.' })).toBeVisible();
  await expect(page.getByText('Upload a file or paste a YouTube link above to get started.')).toBeVisible();
  if (testInfo.project.name === 'desktop') await expect(page.getByText('Connected')).toBeVisible();
  else await expect(page.locator('.mobile-bar')).toBeVisible();
});

test('opens a local no-auth workspace without asking for a key', async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/v1/config') {
      expect(route.request().headers().authorization).toBeUndefined();
      return route.fulfill({ json: { owner: 'local-user', authentication_required: false, agent_available: true, youtube_url_enabled: true, max_upload_bytes: 104857600, max_remote_bytes: 524288000, max_remote_duration_seconds: 14400, formats: ['.txt'], answer_mode: 'extractive' } });
    }
    if (path === '/api/v1/media' || path === '/api/v1/jobs') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { error: { message: 'Not found' } } });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Upload or paste a link. Then ask.' })).toBeVisible();
  await expect(page.getByLabel('Workspace API key')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Disconnect' })).toHaveCount(0);
});

test('asks a grounded question and renders its evidence', async ({ page }, testInfo) => {
  await mockApi(page, true);
  await connect(page);
  const navigation = testInfo.project.name === 'mobile' ? page.locator('.mobile-nav') : page.locator('.sidebar');
  await navigation.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByPlaceholder('Ask a question, or enter a focus for the summary…').fill('What is described?');
  await page.locator('.question-actions .primary-button').click();
  await expect(page.getByText('The notes describe grounded retrieval.')).toBeVisible();
  await expect(page.locator('.citations strong')).toHaveText('research-notes.txt');
  await page.locator('.citations button').click();
  await expect(page.getByRole('heading', { name: 'research-notes.txt' })).toBeVisible();
  await expect(page.getByText('Text originals are kept private')).toBeVisible();
});

test('runs agent analysis and shows its tool activity', async ({ page }, testInfo) => {
  await mockApi(page, true);
  await connect(page);
  const navigation = testInfo.project.name === 'mobile' ? page.locator('.mobile-nav') : page.locator('.sidebar');
  await navigation.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByRole('button', { name: 'Agent Analysis' }).click();
  await page.getByPlaceholder('Ask a question, or enter a focus for the summary…').fill('Compare the evidence');
  await page.getByRole('button', { name: 'Analyze' }).click();
  await expect(page.getByText('The agent compared the available evidence.')).toBeVisible();
  await expect(page.getByText('search text')).toBeVisible();
  await expect(page.getByText('1 result')).toBeVisible();
});

test('keeps earlier answers and citations and reopens saved conversations after refresh', async ({ page }) => {
  await mockApi(page, true);
  await connect(page);
  await page.locator('textarea').fill('What is described?');
  await page.locator('.question-actions .primary-button').click();
  await expect(page.locator('.chat-history .response')).toHaveCount(1);
  await page.locator('textarea').fill('Explain that further');
  await page.locator('.question-actions .primary-button').click();
  await expect(page.locator('.chat-history .response')).toHaveCount(2);
  await expect(page.locator('.chat-history .citations')).toHaveCount(2);
  await expect(page.getByRole('log', { name: 'Conversation history' }).getByText('What is described?', { exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel('Saved conversations').selectOption('chat-1');
  await expect(page.locator('.chat-history .response')).toHaveCount(2);
  await page.getByRole('button', { name: 'New chat', exact: true }).click();
  await expect(page.locator('.chat-history .response')).toHaveCount(0);
  await page.getByLabel('Saved conversations').selectOption('chat-1');
  await expect(page.locator('.chat-history .response')).toHaveCount(2);
});

test('uploads, processes, summarizes, and deletes media', async ({ page }) => {
  await mockApi(page);
  await connect(page);
  await page.locator('input[type="file"]').setInputFiles({
    name: 'research-notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Grounded retrieval keeps evidence.'),
  });
  await expect(page.getByText('Preparing your media for questions.', { exact: false })).toBeVisible();
  await expect(page.getByText('Ready to ask. Type a question about your media below.')).toBeVisible({ timeout: 8_000 });

  const navigation = page.viewportSize()!.width <= 760 ? page.locator('.mobile-nav') : page.locator('.sidebar');
  await navigation.getByRole('button', { name: 'Ask', exact: true }).click();
  await page.getByRole('button', { name: 'Summarize' }).click();
  await expect(page.getByText('A grounded summary of the notes.')).toBeVisible();

  await navigation.getByRole('button', { name: 'Library', exact: true }).click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Delete research-notes.txt' }).click();
  await expect(page.getByText('No media yet')).toBeVisible();
});

test('imports and processes a YouTube video URL', async ({ page }) => {
  await mockApi(page);
  await connect(page);
  await page.getByPlaceholder('Paste a public YouTube video URL').fill('https://youtu.be/abcdefghijk');
  await page.getByRole('button', { name: 'Add video' }).click();
  await expect(page.getByText('podcast.mp4')).toBeVisible();
  await expect(page.getByText('Ready to ask. Type a question about your media below.')).toBeVisible({ timeout: 8_000 });
});

test('waits for the new media and asks about it without selecting sources manually', async ({ page }) => {
  await mockApi(page, true);
  const added = { ...asset, id: 'media-2', metadata: { original_name: 'new-notes.txt' } };
  let finished = false;
  let uploaded = false;
  await page.route('**/api/v1/media', (route) => {
    uploaded = true;
    return route.fulfill({ status: 201, json: added });
  });
  await page.route('**/api/v1/media?*', (route) => route.fulfill({ json: uploaded ? [added, asset] : [asset] }));
  await page.route('**/api/v1/media/media-2/process', (route) => route.fulfill({ status: 202, json: { ...completedJob, id: 'job-2', media_id: added.id, status: 'running' } }));
  await page.route('**/api/v1/jobs?*', (route) => route.fulfill({ json: [completedJob, ...(uploaded ? [{ ...completedJob, id: 'job-2', media_id: added.id, status: finished ? 'completed' : 'running' }] : [])] }));
  await page.route('**/api/v1/conversations/*/messages', (route) => {
    expect(route.request().postDataJSON().media_ids).toEqual([added.id]);
    return route.fulfill({ json: { id: 'chat-1', title: 'New upload', media_ids: [added.id], messages: [{ role: 'assistant', content: 'An answer about the new upload.', response: { answer: 'An answer about the new upload.', sources: [], metadata: {} } }] } });
  });
  await connect(page);
  await page.locator('input[type="file"]').setInputFiles({ name: 'new-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('New evidence') });
  await page.locator('textarea').fill('What is in this file?');
  await expect(page.locator('.question-actions .primary-button')).toBeDisabled();
  await expect(page.getByText('Preparing your media for questions.', { exact: false })).toBeVisible();
  finished = true;
  await expect(page.locator('.question-actions .primary-button')).toBeEnabled({ timeout: 8_000 });
  await page.locator('.question-actions .primary-button').click();
  await expect(page.getByText('An answer about the new upload.')).toBeVisible();
});

test('shows authentication errors and can disconnect', async ({ page }, testInfo) => {
  await page.route('**/api/v1/config', (route) => route.fulfill({
    status: 401,
    json: { error: { message: 'Authentication required' } },
  }));
  await page.goto('/');
  await page.getByLabel('Workspace API key').fill('invalid-key');
  await page.getByRole('button', { name: 'Connect' }).click();
  await expect(page.getByText('Authentication required')).toBeVisible();

  await page.unroute('**/api/v1/config');
  await mockApi(page);
  await page.getByLabel('Workspace API key').fill('test-key');
  await page.getByRole('button', { name: 'Connect' }).click();
  const disconnect = testInfo.project.name === 'mobile'
    ? page.locator('.mobile-bar').getByRole('button')
    : page.getByRole('button', { name: 'Disconnect' });
  await disconnect.click();
  await expect(page.getByLabel('Workspace API key')).toBeVisible();
});

test('uses compact navigation on mobile', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile', 'mobile-only assertion');
  await mockApi(page);
  await connect(page);
  await expect(page.locator('.mobile-nav')).toBeVisible();
  await expect(page.locator('.sidebar')).toBeHidden();
});
