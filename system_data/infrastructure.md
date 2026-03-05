# Infrastructure — Personal Assistant VM

## VM Facts
- **Provider**: Azure, Resource Group: `assistant-rg`, Region: `eastus`
- **VM Name**: `assistant-vm` (Standard_B2ms: 2 vCPU, 8GB RAM)
- **Public IP**: `20.39.61.95`
- **FQDN**: `assistant-vm.eastus.cloudapp.azure.com`
- **OS**: Ubuntu 22.04 LTS
- **User**: `ubuntu`
- **SSH key**: `~/.ssh/id_rsa`
- **Disk**: 30GB OS disk (`/dev/root`)
- **Repo dir** (RDIR): `/home/ubuntu/assistant`

## Runtime Stack (post-migration: 2026-03-05)
- **Python**: 3.11.15 (via deadsnakes PPA)
- **Node**: 20.20.0 (via nodesource)
- **TypeScript**: 5.9.3 (global: `sudo npm install -g typescript`)
- **github-mcp-server**: v0.31.0 at `/usr/local/bin/github-mcp-server`
- **Process manager**: systemd (migrated from Docker Compose 2026-03-05)
- **Docker**: REMOVED (uninstalled 2026-03-05 to free disk)

## MCP Container Table (now systemd services)

| Service Name          | Port  | Runtime | Working Dir                                      | Entry Point |
|-----------------------|-------|---------|--------------------------------------------------|-------------|
| mcp-auth-gateway      | 8000  | Python  | mcp-servers/mcp-auth-gateway                     | .venv/bin/python server.py |
| mcp-journal-db        | 3333  | Python  | mcp-servers/db-mcp-server                        | .venv/bin/python server.py |
| mcp-garmin            | 5555  | Python  | mcp-servers/garmin-mcp-server                    | .venv/bin/python -m garmin_mcp --http |
| mcp-google-workspace  | 3000  | Python  | mcp-servers/google-workspace-mcp-server          | .venv/bin/python src/server.py |
| mcp-google-places     | 1111  | Node    | mcp-servers/googleplaces-mcp-server              | node dist/index.js |
| mcp-splitwise         | 4000  | Node    | mcp-servers/splitwise-mcp-server                 | node dist/index.js |
| mcp-skills-data       | 6666  | Python  | mcp-servers/skills-data-mcp-server               | .venv/bin/python -m skills_data_mcp |
| mcp-github            | 2222  | Binary  | /usr/local/bin/github-mcp-server                 | github-mcp-server http --port 2222 |

## Token / Data Locations
- **Garmin tokens**: `/home/ubuntu/assistant/tokens/garmin/` (oauth1_token.json, oauth2_token.json)
- **Google tokens**: `/home/ubuntu/assistant/tokens/google/` (token.json, credentials.json)
- **Google workspace copy**: `/home/ubuntu/assistant/mcp-servers/google-workspace-mcp-server/` (auth.py resolves at repo root)
- **Skills data**: `/home/ubuntu/assistant/data/skills/`
- **Env**: `/home/ubuntu/assistant/.env.production`

## Nginx
- Config: `/etc/nginx/sites-available/assistant`
- Proxies all MCP services under HTTPS domain

## Sudoers
- File: `/etc/sudoers.d/ubuntu-mcp`
- Allows ubuntu to restart/start/stop/status/enable `mcp-*` services and run `daemon-reload` without password

## Known Failure Modes

### Port conflicts on startup
- **Symptom**: Service `activating` / `EADDRINUSE` in journal logs
- **Root cause**: Old Docker containers holding the port, or Docker service auto-restarting
- **Fix**: `sudo systemctl stop docker docker.socket containerd && sudo systemctl disable docker docker.socket`

### github-mcp-server `unknown flag: --transport`
- **Symptom**: mcp-github fails with "unknown flag: --transport"
- **Root cause**: The binary uses subcommands now. Old flag `--transport sse --port N` is invalid in v0.31.0+
- **Fix**: Use `github-mcp-server http --port 2222` in ExecStart
- **Fixed in**: systemd/mcp-github.service (2026-03-05)

### googleplaces TypeScript build: missing dist/transport
- **Symptom**: `ERR_MODULE_NOT_FOUND` for `dist/transport/http.js`
- **Root cause**: Committed dist/ only had `index.js`; `npm ci --omit=dev` skips `@types/*` devDeps causing tsc errors but output still generated
- **Fix**: `npm install -g typescript && cd mcp-servers/googleplaces-mcp-server && tsc`
- **Note**: tsc emits errors about missing `@types/node`, `@types/express`, `@types/ws` but still compiles successfully

### journal-db slow start (~60-90s)
- **Symptom**: HTTP health check fails for 60-90s after start
- **Root cause**: Downloads/loads sentence-transformers model on first boot
- **Normal**: Wait before checking health

### Disk pressure
- **Symptom**: venv creation fails, `df -h /` shows >90% used
- **Root cause**: Multiple Docker rebuilds, or large pip packages (torch)
- **Fix (Docker era)**: `docker system prune -af` — safe, preserves named volumes
- **Fix (systemd era)**: Docker is removed; run `pip cache purge` or clean old venvs

### Garmin tokens missing
- **Symptom**: mcp-garmin crashes with auth error
- **Root cause**: Volume data not migrated, or token expired
- **Fix**: Copy from `~/.garminconnect/` or `~/.garth/` on local machine to VM `tokens/garmin/`
- **Cannot auto-fix**: Requires human if tokens need re-auth

### Google OAuth token expired
- **Symptom**: mcp-google-workspace returns 401/403
- **Fix**: Re-run OAuth flow locally, copy new token.json to VM
- **Cannot auto-fix**: Requires human

## Diagnosis Runbook

1. **Check service status**: `systemctl is-active mcp-*`
2. **Get logs**: `journalctl -u mcp-<service> -n 50 --no-pager`
3. **Check ports**: `ss -tlnp | grep -E ':1111|:2222|:3000|:3333|:4000|:5555|:6666|:8000'`
4. **HTTP health**: `curl -s http://localhost:<port>/health` or `curl -s http://localhost:<port>/`
5. **Disk**: `df -h /`
6. **Restart service**: `sudo systemctl restart mcp-<service>`
7. **Restart all**: `cd /home/ubuntu/assistant && ./deploy.sh restart`
