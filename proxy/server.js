/**
 * Central Coast Dashboard — OpenAI Proxy with server-side data analysis
 * Pre-computes rankings/stats so LLM only formats, never calculates.
 */
const http = require('http');
const https = require('https');

const PORT = 3456;
const OPENAI_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_KEY) { console.error('OPENAI_API_KEY not set'); process.exit(1); }

// ── Pre-compute a rich summary of the data for each question ──────────
function computeStats(data) {
  if (!data || !data.length) return '';

  // Collect all numeric columns
  const numericCols = {};
  data.forEach(row => {
    Object.entries(row).forEach(([k, v]) => {
      if (k === 'sa2' || k === 'region') return;
      const n = parseFloat(v);
      if (!isNaN(n)) {
        if (!numericCols[k]) numericCols[k] = [];
        numericCols[k].push({ sa2: row.sa2, value: n });
      }
    });
  });

  // For each column: sort and produce ranked list
  const stats = {};
  Object.entries(numericCols).forEach(([col, rows]) => {
    const sorted = [...rows].sort((a, b) => b.value - a.value);
    stats[col] = {
      ranked: sorted,  // descending order — index 0 = highest
      min: sorted[sorted.length - 1],
      max: sorted[0],
    };
  });
  return stats;
}

function buildContext(data, stats) {
  // Produce a compact but accurate pre-computed summary the LLM can reference
  const lines = ['=== PRE-COMPUTED RANKINGS (use ONLY these for any ranking/top/bottom questions) ==='];
  Object.entries(stats).forEach(([col, s]) => {
    const top5 = s.ranked.slice(0, 5).map((r, i) => `${i+1}. ${r.sa2}: ${r.value}`).join('; ');
    const bot3 = s.ranked.slice(-3).reverse().map((r, i) => `${i+1}. ${r.sa2}: ${r.value}`).join('; ');
    lines.push(`${col}: TOP5=[${top5}] | BOTTOM3=[${bot3}]`);
  });
  lines.push('');
  lines.push('=== FULL SA2 DATA (for individual lookups) ===');
  data.forEach(row => {
    lines.push(JSON.stringify(row));
  });
  return lines.join('\n');
}

const SYSTEM_PROMPT = `You are a data analyst assistant for Central Coast Council, NSW, Australia.

CRITICAL RULES:
1. For ANY question about rankings, highest, lowest, top N, bottom N — you MUST use the PRE-COMPUTED RANKINGS section ONLY. Never try to rank the raw data yourself.
2. For individual SA2 lookups, use the FULL SA2 DATA section.
3. Never invent or estimate numbers. Only report exact values from the data provided.
4. Keep answers concise and well-formatted. Use markdown bold for SA2 names.
5. If a column name is not in the data, say so clearly.`;

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  if (req.method !== 'POST' || req.url !== '/ask') { res.writeHead(404); res.end('Not found'); return; }

  let body = '';
  req.on('data', chunk => body += chunk);
  req.on('end', () => {
    let payload;
    try { payload = JSON.parse(body); } catch { res.writeHead(400); res.end('Bad JSON'); return; }

    const { question, data } = payload;
    if (!question) { res.writeHead(400); res.end('Missing question'); return; }

    const stats = computeStats(data);
    const context = buildContext(data, stats);

    const messages = [
      { role: 'system', content: SYSTEM_PROMPT + '\n\n' + context },
      { role: 'user', content: question }
    ];

    const reqBody = JSON.stringify({ model: 'gpt-4o-mini', messages, max_tokens: 500, temperature: 0 });
    const options = {
      hostname: 'api.openai.com', port: 443,
      path: '/v1/chat/completions', method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${OPENAI_KEY}`,
        'Content-Length': Buffer.byteLength(reqBody)
      }
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
        } catch { res.writeHead(500); res.end('Parse error'); }
      });
    });
    apiReq.on('error', e => { res.writeHead(502); res.end(e.message); });
    apiReq.write(reqBody);
    apiReq.end();
  });
});

server.listen(PORT, '0.0.0.0', () => console.log(`CC Dashboard proxy listening on port ${PORT}`));
