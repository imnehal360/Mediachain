import { expect, test, type Page } from '@playwright/test';

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
  let uploaded = withMedia;
  let processed = withMedia;
  await page.route('**/api/v1/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
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
      return route.fulfill({ json: { answer: 'The notes describe grounded retrieval.', sources: [{ media_id: asset.id, document_id: 'doc-1', source: asset.source, modality: 'text', start_time: null, end_time: null }], insufficient_evidence: false, token_usage: null, metadata: {} } });
    }
    if (path === '/api/v1/agent/query') {
      return route.fulfill({ json: { answer: 'The agent compared the available evidence.', sources: [{ media_id: asset.id, document_id: 'doc-1', source: asset.source, modality: 'text', start_time: null, end_time: null }], insufficient_evidence: false, token_usage: 12, metadata: { mode: 'agentic', tool_calls: [{ tool: 'search_text', arguments: { query: 'evidence' }, result_count: 1 }] } } });
    }
    if (path === '/api/v1/summarize') {
      return route.fulfill({ json: { answer: 'A grounded summary of the notes.', sources: [{ media_id: asset.id, document_id: 'doc-1', source: asset.source, modality: 'text', start_time: null, end_time: null }], insufficient_evidence: false, token_usage: null, metadata: {} } });
    }
    return route.fulfill({ status: 404, json: { error: { message: 'Not found' } } });
  });
}

async function connect(page: Page) {
  await page.goto('/');
  await page.getByLabel('Workspace API key').fill('test-key');
  await page.getByRole('button', { name: 'Connect' }).click();
  await expect(page.getByRole('heading', { name: 'Your media' })).toBeVisible();
}

test('connects and shows a clear empty library', async ({ page }, testInfo) => {
  await mockApi(page);
  await connect(page);
  await expect(page.getByRole('heading', { name: 'Your media' })).toBeVisible();
  await expect(page.getByText('No media yet')).toBeVisible();
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
  await expect(page.getByRole('heading', { name: 'Your media' })).toBeVisible();
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

test('uploads, processes, summarizes, and deletes media', async ({ page }) => {
  await mockApi(page);
  await connect(page);
  await page.locator('input[type="file"]').setInputFiles({
    name: 'research-notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('Grounded retrieval keeps evidence.'),
  });
  await expect(page.getByText('research-notes.txt')).toBeVisible();
  await expect(page.getByText('completed')).toBeVisible({ timeout: 4_000 });

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
  await expect(page.getByText('completed')).toBeVisible({ timeout: 4_000 });
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
