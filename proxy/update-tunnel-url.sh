#!/bin/bash
# Waits for cloudflared tunnel to be ready, then updates config.json on GitHub
# Called by systemd after cc-dashboard-tunnel starts

GITHUB_TOKEN_FILE="/home/azureuser/.cc-dashboard-pat"
REPO="pspedding/central-coast-dashboard"
DASHBOARD_DIR="/home/azureuser/council-work/sa2-dashboard"

# Wait up to 30s for tunnel URL
for i in $(seq 1 30); do
    TUNNEL_URL=$(curl -s http://127.0.0.1:20241/metrics 2>/dev/null | grep -o "https://[a-z-]*\.trycloudflare\.com" | head -1)
    if [ -n "$TUNNEL_URL" ]; then break; fi
    sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
    echo "ERROR: Could not get tunnel URL after 30s"
    exit 1
fi

echo "Tunnel URL: $TUNNEL_URL"

# Write config.json locally
echo "{\"apiUrl\": \"${TUNNEL_URL}/ask\"}" > "${DASHBOARD_DIR}/config.json"

# Push to GitHub via API
if [ ! -f "$GITHUB_TOKEN_FILE" ]; then
    echo "No PAT file at $GITHUB_TOKEN_FILE — skipping GitHub push"
    exit 0
fi

TOKEN=$(cat "$GITHUB_TOKEN_FILE")
CONTENT=$(base64 -w0 "${DASHBOARD_DIR}/config.json")

# Get current SHA of config.json (needed for update)
SHA=$(curl -s -H "Authorization: token $TOKEN" \
    "https://api.github.com/repos/${REPO}/contents/config.json" | \
    python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('sha',''))" 2>/dev/null)

# Push update
PAYLOAD="{\"message\":\"chore: update tunnel URL\",\"content\":\"${CONTENT}\""
if [ -n "$SHA" ]; then PAYLOAD="${PAYLOAD},\"sha\":\"${SHA}\""; fi
PAYLOAD="${PAYLOAD}}"

RESULT=$(curl -s -X PUT \
    -H "Authorization: token $TOKEN" \
    -H "Content-Type: application/json" \
    "https://api.github.com/repos/${REPO}/contents/config.json" \
    -d "$PAYLOAD")

echo "$RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print('GitHub push:', r.get('content',{}).get('name','ERROR: '+str(r.get('message',r))))" 2>/dev/null
