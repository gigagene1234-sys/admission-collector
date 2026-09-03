const WORKER = 'https://admission-collector-offload.gigagene1234.workers.dev';

function allowedRunId(value) {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{8,100}$/.test(value);
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  const action = String(req.query.action || 'health');
  const provider = String(req.query.provider || '');
  const runId = String(req.query.runId || '');
  let path;
  let needsAuth = true;

  if (action === 'health') {
    path = '/health';
    needsAuth = false;
  } else if (action === 'latest' && (provider === 'adiga' || provider === 'jinhak')) {
    path = `/v1/runs/latest?provider=${encodeURIComponent(provider)}`;
  } else if (action === 'status' && allowedRunId(runId)) {
    path = `/v1/runs/${encodeURIComponent(runId)}/status`;
  } else if (action === 'pending' && allowedRunId(runId)) {
    path = `/v1/runs/${encodeURIComponent(runId)}/pending-pages?limit=100`;
  } else {
    return res.status(400).json({ error: 'unsupported-request' });
  }

  const headers = { Accept: 'application/json' };
  if (needsAuth) {
    const auth = req.headers.authorization || '';
    if (!auth.startsWith('Bearer ') || auth.length < 16) {
      return res.status(401).json({ error: 'collector-token-required' });
    }
    headers.Authorization = auth;
  }

  try {
    const upstream = await fetch(WORKER + path, { method: 'GET', headers, cache: 'no-store' });
    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/json; charset=utf-8');
    return res.send(text || '{}');
  } catch (error) {
    return res.status(502).json({ error: 'worker-unreachable', type: error?.name || 'Error' });
  }
}
