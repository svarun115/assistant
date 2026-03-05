#!/usr/bin/env bash
# Personal Assistant — MCP Servers Deployment Runbook
# Run on an Azure Ubuntu 22.04 LTS VM.
# Idempotent: safe to re-run for updates.
#
# Commands:
#   ./deploy.sh              — full first-time deploy (venvs + systemd)
#   ./deploy.sh update       — git pull + reinstall deps + restart services
#   ./deploy.sh logs [svc]   — follow journal logs (e.g. logs mcp-garmin)
#   ./deploy.sh status       — systemd status + quick curl health check
#   ./deploy.sh restart [svc]— restart all services or one
#   ./deploy.sh stop         — stop all services
#   ./deploy.sh setup-nginx DOMAIN — install Nginx + configure TLS

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_DIR="$REPO_DIR/mcp-servers"

ALL_SERVICES=(
  mcp-auth-gateway
  mcp-journal-db
  mcp-garmin
  mcp-google-workspace
  mcp-google-places
  mcp-splitwise
  mcp-skills-data
  mcp-github
)

case "${1:-deploy}" in

  deploy)
    echo "=== MCP Servers — Deploy ==="

    echo "[1/6] Checking prerequisites..."
    [[ -f "$REPO_DIR/.env.production" ]] || { echo "ERROR: .env.production missing."; exit 1; }
    [[ -f "$REPO_DIR/tokens/google/token.json" ]] || { echo "ERROR: tokens/google/token.json missing."; exit 1; }
    [[ -f "$REPO_DIR/tokens/google/credentials.json" ]] || { echo "ERROR: tokens/google/credentials.json missing."; exit 1; }
    command -v python3.11 >/dev/null 2>&1 || { echo "ERROR: python3.11 not installed."; exit 1; }
    command -v node >/dev/null 2>&1 || { echo "ERROR: node not installed."; exit 1; }
    echo "  ✓ Prerequisites OK"

    echo "[2/6] Setting up token and data directories..."
    mkdir -p "$REPO_DIR/tokens/garmin"
    mkdir -p "$REPO_DIR/data/skills"
    # Google Workspace: auth.py resolves token at <repo>/token.json (Path(__file__).parent.parent)
    cp "$REPO_DIR/tokens/google/token.json" "$MCP_DIR/google-workspace-mcp-server/token.json"
    cp "$REPO_DIR/tokens/google/credentials.json" "$MCP_DIR/google-workspace-mcp-server/credentials.json"
    echo "  ✓ Tokens in place"

    echo "[3/6] Creating Python virtualenvs and installing dependencies..."

    # auth-gateway
    echo "  auth-gateway..."
    cd "$MCP_DIR/mcp-auth-gateway"
    python3.11 -m venv .venv
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -r requirements.txt -q

    # google-workspace
    echo "  google-workspace..."
    cd "$MCP_DIR/google-workspace-mcp-server"
    python3.11 -m venv .venv
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install -r requirements.txt -q

    # journal-db: pre-install CPU-only torch to avoid 5GB CUDA download
    echo "  journal-db (CPU-only torch first)..."
    cd "$MCP_DIR/db-mcp-server"
    python3.11 -m venv .venv
    .venv/bin/pip install --upgrade pip -q
    .venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu -q
    .venv/bin/pip install -r requirements.txt -q
    .venv/bin/pip install -e . --no-deps -q

    # garmin + skills-data use hatchling
    for svc in garmin-mcp-server skills-data-mcp-server; do
      echo "  $svc..."
      cd "$MCP_DIR/$svc"
      python3.11 -m venv .venv
      .venv/bin/pip install --upgrade pip hatchling -q
      .venv/bin/pip install . -q
    done

    echo "  ✓ Python venvs ready"

    echo "[4/6] Installing Node dependencies..."
    for svc in googleplaces-mcp-server splitwise-mcp-server; do
      echo "  $svc..."
      cd "$MCP_DIR/$svc"
      npm ci --omit=dev --quiet
    done
    echo "  ✓ Node deps ready"

    echo "[5/6] Installing systemd unit files..."
    for unit in "$REPO_DIR/systemd"/mcp-*.service; do
      sudo cp "$unit" /etc/systemd/system/
    done
    sudo systemctl daemon-reload
    for svc in "${ALL_SERVICES[@]}"; do
      sudo systemctl enable "$svc"
    done
    sudo systemctl start "${ALL_SERVICES[@]}"
    echo "  ✓ Services started"

    echo "[6/6] Waiting for services to come up..."
    sleep 10
    "$0" status
    ;;

  update)
    echo "=== Rolling Update ==="
    cd "$REPO_DIR"
    echo "  Pulling framework..."
    git pull --quiet

    echo "  Pulling MCP servers..."
    for dir in "$MCP_DIR"/*/; do
      [[ -d "$dir/.git" ]] && git -C "$dir" pull --quiet && echo "  ✓ $(basename $dir)"
    done

    echo "  Pulling .claude..."
    [[ -d "$REPO_DIR/.claude/.git" ]] && git -C "$REPO_DIR/.claude" pull --quiet && echo "  ✓ .claude"

    echo "  Reinstalling Python deps..."
    for svc in mcp-auth-gateway google-workspace-mcp-server; do
      dir="$MCP_DIR/$svc"
      [[ -f "$dir/requirements.txt" ]] && "$dir/.venv/bin/pip" install -r "$dir/requirements.txt" -q
    done
    for svc in db-mcp-server garmin-mcp-server skills-data-mcp-server; do
      dir="$MCP_DIR/$svc"
      [[ -d "$dir/.venv" ]] && "$dir/.venv/bin/pip" install -e "$dir" --no-deps -q 2>/dev/null || true
    done

    echo "  Reinstalling Node deps..."
    for svc in googleplaces-mcp-server splitwise-mcp-server; do
      cd "$MCP_DIR/$svc" && npm ci --omit=dev --quiet
    done

    echo "  Copying updated systemd unit files..."
    for unit in "$REPO_DIR/systemd"/mcp-*.service; do
      sudo cp "$unit" /etc/systemd/system/
    done
    sudo systemctl daemon-reload

    echo "  Restarting services..."
    sudo systemctl restart "${ALL_SERVICES[@]}"
    sleep 5
    "$0" status
    ;;

  logs)
    svc="${2:-}"
    if [[ -n "$svc" ]]; then
      journalctl -u "$svc" -f
    else
      journalctl -u "mcp-*" -f
    fi
    ;;

  status)
    echo "=== Service status ==="
    for svc in "${ALL_SERVICES[@]}"; do
      status=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
      if [[ "$status" == "active" ]]; then
        echo "  ✓ $svc"
      else
        echo "  ✗ $svc — $status"
      fi
    done
    echo ""
    echo "=== Health checks ==="
    for name_port in "auth-gateway:8000" "journal-db:3333" "garmin:5555" "google-workspace:3000" "google-places:1111" "splitwise:4000" "skills-data:6666"; do
      name="${name_port%%:*}"
      port="${name_port##*:}"
      if curl -sf "http://localhost:$port/" >/dev/null 2>&1 || curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
        echo "  ✓ $name (:$port)"
      else
        echo "  ✗ $name (:$port) — not responding"
      fi
    done
    ;;

  restart)
    svc="${2:-}"
    if [[ -n "$svc" ]]; then
      sudo systemctl restart "$svc"
    else
      sudo systemctl restart "${ALL_SERVICES[@]}"
    fi
    ;;

  stop)
    sudo systemctl stop "${ALL_SERVICES[@]}"
    ;;

  setup-nginx)
    DOMAIN="${2:?Usage: ./deploy.sh setup-nginx YOUR-DOMAIN}"
    echo "=== Installing Nginx + Certbot for $DOMAIN ==="
    sudo apt-get update -q
    sudo apt-get install -y nginx certbot python3-certbot-nginx

    # Install config with domain substituted
    sudo cp "$REPO_DIR/nginx/assistant.conf" /etc/nginx/sites-available/assistant
    sudo sed -i "s/YOUR-DOMAIN/$DOMAIN/g" /etc/nginx/sites-available/assistant

    # Inject the API key from .env.production into nginx config
    MCP_API_KEY=$(grep -E '^MCP_API_KEY=' "$REPO_DIR/.env.production" | cut -d= -f2-)
    sudo sed -i "s/REPLACE_WITH_MCP_API_KEY/$MCP_API_KEY/g" /etc/nginx/sites-available/assistant

    sudo ln -sf /etc/nginx/sites-available/assistant /etc/nginx/sites-enabled/assistant
    sudo nginx -t
    sudo systemctl reload nginx

    echo "Getting TLS certificate..."
    sudo certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" || {
      echo "Certbot auto-config failed — run manually: sudo certbot --nginx -d $DOMAIN"
    }

    echo ""
    echo "=== Done ==="
    echo "MCP servers now accessible at:"
    echo "  https://$DOMAIN/journal-db/mcp"
    echo "  https://$DOMAIN/garmin/mcp"
    echo "  https://$DOMAIN/google/mcp"
    echo "  https://$DOMAIN/places/mcp"
    echo "  https://$DOMAIN/splitwise/mcp"
    ;;

  *)
    echo "Usage: $0 {deploy|update|logs [svc]|status|restart [svc]|stop|setup-nginx DOMAIN}"
    exit 1
    ;;
esac
