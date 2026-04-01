/**
 * Minimal OpenAI proxy — Central Coast Dashboard
 * Runs on port 3456, accepts POST /ask { question, data }
 * Returns { answer }
 */
const http = require('http');
const https = require('https');

const PORT = 3456;
const OPENAI_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_KEY) { console.error('OPENAI_API_KEY not set'); process.exit(1); }

const SYSTEM_PROMPT = `You are a data analyst assistant for Central Coast Council, NSW, Australia.
Answer questions concisely using the SA2-level indicator data provided.
Format numbers clearly. Keep answers under 150 words unless a list is needed.`;

const server = http.createServer((req, res) => {
  // CORS — allow GitHub Pages origin
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  if (req.method !== 'POST' || req.url !== '/ask') {
    res.writeHead(404); res.end('Not found'); return;
  }

  let body = '';
  req.on('data', chunk => body += chunk);
  req.on('end', () => {
    let payload;
    try { payload = JSON.parse(body); } catch {
      res.writeHead(400); res.end('Bad JSON'); return;
    }

    const { question, data } = payload;
    if (!question) { res.writeHead(400); res.end('Missing question'); return; }

    const messages = [
      { role: 'system', content: SYSTEM_PROMPT + '\n\nData: ' + JSON.stringify(data) },
      { role: 'user', content: question }
    ];

    const reqBody = JSON.stringify({ model: 'gpt-4o-mini', messages, max_tokens: 400, temperature: 0.3 });
    const options = {
      hostname: 'api.openai.com', port: 443,
      path: '/v1/chat/completions', method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${OPENAI_KEY}`, 'Content-Length': Buffer.byteLength(reqBody) }
    };

    const apiReq = https.request(options, apiRes => {
      let apiBody = '';
      apiRes.on('data', c => apiBody += c);
      apiRes.on('end', () => {
        try {
          const json = JSON.parse(apiBody);
          const answer = json.choices?.[0]?.message?.content || 'No response.';
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ answer }));
        } catch {
          res.writeHead(500); res.end('Parse error');
        }
      });
    });
    apiReq.on('error', e => { res.writeHead(502); res.end(e.message); });
    apiReq.write(reqBody);
    apiReq.end();
  });
});

server.listen(PORT, '0.0.0.0', () => console.log(`CC Dashboard proxy listening on port ${PORT}`));
