# Repos — Personal Assistant VM

## Framework Repo
- **GitHub**: `https://github.com/svarun115/assistant`
- **VM path**: `/home/ubuntu/assistant`
- **Branch**: `master`
- **Deploy commands**:
  - Full deploy: `cd /home/ubuntu/assistant && ./deploy.sh`
  - Update (pull + reinstall deps + restart): `./deploy.sh update`
  - Status: `./deploy.sh status`
  - Restart all: `./deploy.sh restart`
  - Restart one: `./deploy.sh restart mcp-<service>`
  - Logs: `./deploy.sh logs [mcp-<service>]`

## MCP Server Repos

| Local Path | GitHub Repo | Language |
|------------|-------------|----------|
| `mcp-servers/mcp-auth-gateway` | `svarun115/mcp-auth-gateway` | Python |
| `mcp-servers/db-mcp-server` | `svarun115/journal-db-mcp-server` | Python |
| `mcp-servers/garmin-mcp-server` | `svarun115/garmin-mcp-server` | Python |
| `mcp-servers/google-workspace-mcp-server` | `svarun115/google-workspace-mcp-server` | Python |
| `mcp-servers/googleplaces-mcp-server` | `svarun115/googleplaces-mcp-server` | Node/TS |
| `mcp-servers/splitwise-mcp-server` | `svarun115/splitwise-mcp-server` | Node/TS |
| `mcp-servers/skills-data-mcp-server` | `svarun115/skills-data-mcp-server` | Python |

Note: `github-mcp-server` is a pre-built binary at `/usr/local/bin/github-mcp-server` (not a local repo clone).

## Systemd Unit Files
- **Location (repo)**: `/home/ubuntu/assistant/systemd/mcp-*.service`
- **Installed location**: `/etc/systemd/system/mcp-*.service`
- **Update after editing**: `sudo cp /home/ubuntu/assistant/systemd/mcp-*.service /etc/systemd/system/ && sudo systemctl daemon-reload`

## Claude Config Repo
- **GitHub**: `https://github.com/svarun115/claude-config`
- **VM path**: `/home/ubuntu/assistant/.claude`
- **Branch**: `master`
- **Update**: `git -C /home/ubuntu/assistant/.claude pull`

## Deploy Steps for Code Changes

### Python MCP server (auth-gateway, journal-db, garmin, google-workspace, skills-data)
```bash
git -C /home/ubuntu/assistant/mcp-servers/<repo> pull
/home/ubuntu/assistant/mcp-servers/<repo>/.venv/bin/pip install -r requirements.txt -q   # or pip install . -q
sudo systemctl restart mcp-<service>
```

### Node MCP server (google-places, splitwise)
```bash
git -C /home/ubuntu/assistant/mcp-servers/<repo> pull
cd /home/ubuntu/assistant/mcp-servers/<repo>
npm ci --omit=dev --quiet
tsc   # if dist/ needs rebuild (requires: sudo npm install -g typescript)
sudo systemctl restart mcp-<service>
```

### Framework / systemd unit file changes
```bash
cd /home/ubuntu/assistant && git pull
sudo cp systemd/mcp-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart mcp-<affected-service>
```

### github-mcp-server binary update
```bash
GH_VER=$(curl -s https://api.github.com/repos/github/github-mcp-server/releases/latest | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'])")
curl -fsSL "https://github.com/github/github-mcp-server/releases/download/${GH_VER}/github-mcp-server_Linux_x86_64.tar.gz" | sudo tar xz -C /usr/local/bin
sudo systemctl restart mcp-github
```
