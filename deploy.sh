#!/usr/bin/env bash
# Personal Assistant — MCP Servers Deployment Runbook
# Run on an Azure Ubuntu 22.04 LTS VM.
# Idempotent: safe to re-run for updates.
#
# Commands:
#   ./deploy.sh              — full first-time deploy
#   ./deploy.sh update       — git pull + rebuild + restart
#   ./deploy.sh logs         — tail all containers
#   ./deploy.sh logs garmin  — tail one container
#   ./deploy.sh status       — container health + quick curl check
#   ./deploy.sh restart [svc]— restart all or one service
#   ./deploy.sh stop         — stop all containers
#   ./deploy.sh setup-docker — install Docker (run once on fresh VM)
#   ./deploy.sh setup-nginx DOMAIN — install Nginx + configure TLS

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE="docker compose --env-file .env.production"

case "${1:-deploy}" in

  deploy)
    echo "=== MCP Servers — Deploy ==="

    echo "[1/4] Checking prerequisites..."
    command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker not installed. Run: ./deploy.sh setup-docker"; exit 1; }
    [[ -f "$REPO_DIR/.env.production" ]] || { echo "ERROR: .env.production missing. Copy .env.production.example and fill in."; exit 1; }
    [[ -f "$REPO_DIR/tokens/google/token.json" ]] || { echo "ERROR: tokens/google/token.json missing. Copy from your local machine."; exit 1; }
    [[ -f "$REPO_DIR/tokens/google/credentials.json" ]] || { echo "ERROR: tokens/google/credentials.json missing. Copy from your local machine."; exit 1; }
    echo "  ✓ Prerequisites OK"

    echo "[2/4] Building Docker images..."
    cd "$REPO_DIR"
    $COMPOSE build --parallel

    echo "[3/4] Starting containers..."
    $COMPOSE up -d

    echo "[4/4] Waiting for health checks..."
    sleep 10
    $COMPOSE ps

    echo ""
    echo "=== Verify each server ==="
    for name_port in "journal-db:3333" "garmin:5555" "google-workspace:3000" "google-places:1111" "splitwise:4000"; do
      name="${name_port%%:*}"
      port="${name_port##*:}"
      if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
        echo "  ✓ $name (:$port)"
      else
        echo "  ✗ $name (:$port) — not responding yet (may still be starting)"
      fi
    done

    echo ""
    echo "Next: configure Nginx + TLS with ./deploy.sh setup-nginx YOUR-DOMAIN"
    ;;

  update)
    echo "=== Rolling Update ==="
    cd "$REPO_DIR"
    echo "  Pulling framework..."
    git pull
    echo "  Pulling MCP servers..."
    for dir in mcp-servers/*/; do
      [[ -d "$REPO_DIR/$dir/.git" ]] && git -C "$REPO_DIR/$dir" pull --quiet && echo "  ✓ $dir"
    done
    echo "  Pulling .claude..."
    [[ -d "$REPO_DIR/.claude/.git" ]] && git -C "$REPO_DIR/.claude" pull --quiet && echo "  ✓ .claude"
    $COMPOSE build --parallel
    $COMPOSE up -d
    $COMPOSE ps
    ;;

  logs)
    cd "$REPO_DIR"
    $COMPOSE logs -f "${2:-}"
    ;;

  status)
    cd "$REPO_DIR"
    echo "=== Container status ==="
    $COMPOSE ps
    echo ""
    echo "=== Health checks ==="
    for name_port in "journal-db:3333" "garmin:5555" "google-workspace:3000" "google-places:1111" "splitwise:4000"; do
      name="${name_port%%:*}"
      port="${name_port##*:}"
      if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
        echo "  ✓ $name (:$port)"
      else
        echo "  ✗ $name (:$port) — not responding"
      fi
    done
    ;;

  restart)
    cd "$REPO_DIR"
    $COMPOSE restart "${2:-}"
    ;;

  stop)
    cd "$REPO_DIR"
    $COMPOSE stop
    ;;

  setup-docker)
    echo "=== Installing Docker (Ubuntu 22.04) ==="
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    echo "  ✓ Done. Log out and back in so you can use docker without sudo."
    ;;

  setup-nginx)
    DOMAIN="${2:?Usage: ./deploy.sh setup-nginx YOUR-DOMAIN}"
    echo "=== Installing Nginx + Certbot for $DOMAIN ==="
    sudo apt-get update
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
    echo ""
    echo "Update ~/.claude.json on each client using mcp-servers.cloud.example.json"
    ;;

  *)
    echo "Usage: $0 {deploy|update|logs [svc]|status|restart [svc]|stop|setup-docker|setup-nginx DOMAIN}"
    exit 1
    ;;
esac
