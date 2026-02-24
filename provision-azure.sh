#!/usr/bin/env bash
# Personal Assistant — Azure VM Provisioning Script
#
# Provisions an Azure B2ms VM, clones the monorepo, deploys all 5 MCP servers,
# and configures Nginx + TLS. Run this from your local machine.
#
# Prerequisites:
#   1. Azure CLI logged in:  az login
#   2. Repo pushed to GitHub as svarun115/assistant (private)
#   3. .env.production filled in (copy from .env.production.example)
#   4. tokens/google/token.json and credentials.json present locally
#      (at mcp-servers/google-workspace-mcp-server/ or tokens/google/)
#   5. SSH key at ~/.ssh/id_rsa  (generate: ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa)
#
# Usage:
#   chmod +x provision-azure.sh
#   ./provision-azure.sh           # full provision + deploy
#   ./provision-azure.sh deploy    # re-deploy to existing VM (skip provisioning)
#   ./provision-azure.sh ssh       # open SSH session to VM
#   ./provision-azure.sh ip        # print VM public IP
#   ./provision-azure.sh destroy   # delete VM and resource group

set -euo pipefail

# ─── Configuration ─────────────────────────────────────────────────────────
RESOURCE_GROUP="assistant-rg"
LOCATION="eastus"
VM_NAME="assistant-vm"
VM_SIZE="Standard_B2ms"       # 2 vCPU, 8GB, ~$55/month
VM_USER="ubuntu"
SSH_KEY_PATH="${HOME}/.ssh/id_rsa"

# Framework repo (assistant-server + deployment infra)
REPO="https://github.com/svarun115/assistant"

# Personal Claude config (private — skills, agents, plans)
CLAUDE_REPO="https://github.com/svarun115/claude-config"

# MCP servers (each has its own repo)
MCP_REPOS=(
  "mcp-servers/db-mcp-server|https://github.com/svarun115/journal-db-mcp-server.git"
  "mcp-servers/garmin-mcp-server|https://github.com/svarun115/garmin-mcp-server.git"
  "mcp-servers/google-workspace-mcp-server|https://github.com/svarun115/google-workspace-mcp-server.git"
  "mcp-servers/googleplaces-mcp-server|https://github.com/svarun115/googleplaces-mcp-server.git"
  "mcp-servers/splitwise-mcp-server|https://github.com/svarun115/splitwise-mcp-server.git"
)

# Domain for HTTPS.
#   Set to your own domain (e.g. "mcp.yourdomain.com") and add DNS A → VM IP.
#   Leave empty to use Azure's built-in FQDN (assistant-vm.eastus.cloudapp.azure.com).
DOMAIN=""

# ─── Helpers ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

get_vm_ip() {
  az vm show -g "$RESOURCE_GROUP" -n "$VM_NAME" --query "publicIps" -d -o tsv 2>/dev/null
}

ssh_run() {
  local ip="$1"; shift
  ssh $SSH_OPTS -i "$SSH_KEY_PATH" "$VM_USER@$ip" "$@"
}

wait_for_ssh() {
  local ip="$1"
  echo "  Waiting for SSH on $ip..."
  for i in {1..30}; do
    if ssh $SSH_OPTS -i "$SSH_KEY_PATH" "$VM_USER@$ip" "echo ok" >/dev/null 2>&1; then
      echo "  ✓ SSH ready"
      return 0
    fi
    sleep 10; echo "  ... ($i/30)"
  done
  echo "ERROR: SSH timed out"; exit 1
}

wait_for_cloud_init() {
  local ip="$1"
  echo "  Waiting for cloud-init (Docker install)..."
  for i in {1..30}; do
    if ssh_run "$ip" "test -f /tmp/cloud-init-done" >/dev/null 2>&1; then
      echo "  ✓ Docker ready"; return 0
    fi
    sleep 15; echo "  ... ($i/30)"
  done
  echo "ERROR: Cloud-init timed out. SSH in and check: sudo cloud-init status"; exit 1
}

# ─── Pre-flight checks ─────────────────────────────────────────────────────
preflight() {
  echo "[preflight] Checking prerequisites..."
  command -v az >/dev/null 2>&1 || { echo "ERROR: az CLI not installed."; exit 1; }
  az account show >/dev/null 2>&1 || { echo "ERROR: Not logged in. Run: az login"; exit 1; }
  [[ -f "$SCRIPT_DIR/.env.production" ]] || { echo "ERROR: .env.production missing."; exit 1; }
  [[ -f "${SSH_KEY_PATH}.pub" ]] || {
    echo "ERROR: SSH key not found at ${SSH_KEY_PATH}.pub"
    echo "  Generate: ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa"
    exit 1
  }
  # Find Google OAuth tokens (might be in mcp-servers dir or tokens/)
  GOOGLE_TOKEN_SRC=""
  for candidate in \
    "$SCRIPT_DIR/tokens/google/token.json" \
    "$SCRIPT_DIR/mcp-servers/google-workspace-mcp-server/token.json"; do
    [[ -f "$candidate" ]] && GOOGLE_TOKEN_SRC="$(dirname "$candidate")" && break
  done
  [[ -n "$GOOGLE_TOKEN_SRC" ]] || { echo "ERROR: Google token.json not found."; exit 1; }
  [[ -f "$GOOGLE_TOKEN_SRC/credentials.json" ]] || { echo "ERROR: Google credentials.json not found."; exit 1; }
  echo "  ✓ Prerequisites OK (Google tokens at $GOOGLE_TOKEN_SRC)"
}

# ─── Provision VM ──────────────────────────────────────────────────────────
provision() {
  echo ""
  echo "[1/3] Creating resource group '$RESOURCE_GROUP' in $LOCATION..."
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
  echo "  ✓ Resource group ready"

  echo ""
  echo "[2/3] Creating VM '$VM_NAME' ($VM_SIZE) with Docker pre-installed..."
  az vm create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --image Ubuntu2204 \
    --size "$VM_SIZE" \
    --admin-username "$VM_USER" \
    --ssh-key-values "${SSH_KEY_PATH}.pub" \
    --public-ip-sku Standard \
    --public-ip-address-dns-name "$VM_NAME" \
    --custom-data "$SCRIPT_DIR/cloud-init.yml" \
    --output none
  echo "  ✓ VM created"

  echo ""
  echo "[3/3] Opening ports 80 + 443..."
  az vm open-port -g "$RESOURCE_GROUP" -n "$VM_NAME" --port 80  --priority 1001 --output none
  az vm open-port -g "$RESOURCE_GROUP" -n "$VM_NAME" --port 443 --priority 1002 --output none
  echo "  ✓ Ports open"

  VM_IP=$(get_vm_ip)
  AZURE_FQDN="$VM_NAME.$LOCATION.cloudapp.azure.com"
  echo ""
  echo "  VM public IP : $VM_IP"
  echo "  Azure FQDN   : $AZURE_FQDN"
  if [[ -n "$DOMAIN" ]]; then
    echo ""
    echo "  ── ACTION NEEDED ─────────────────────────────────────────"
    echo "  Add DNS A record:  $DOMAIN  →  $VM_IP"
    echo "  ──────────────────────────────────────────────────────────"
  fi
}

# ─── Deploy ────────────────────────────────────────────────────────────────
deploy() {
  local ip; ip=$(get_vm_ip)

  echo ""
  echo "[4/6] Waiting for VM and Docker..."
  wait_for_ssh "$ip"
  wait_for_cloud_init "$ip"

  echo ""
  echo "[5/6] Cloning repos and copying secrets..."

  # Read GitHub token from local .env.production for authenticating private repos
  GITHUB_TOKEN=$(grep -E '^GITHUB_TOKEN=' "$SCRIPT_DIR/.env.production" | cut -d= -f2-)
  [[ -n "$GITHUB_TOKEN" ]] || { echo "ERROR: GITHUB_TOKEN missing from .env.production"; exit 1; }

  # Build authenticated URLs for private repos
  local auth_repo; auth_repo="${REPO/https:\/\//https:\/\/$GITHUB_TOKEN@}"
  local auth_claude; auth_claude="${CLAUDE_REPO/https:\/\//https:\/\/$GITHUB_TOKEN@}"

  # Helper: clone-or-pull that handles leftover non-git directories
  clone_or_pull() {
    local url="$1" dest="$2"
    ssh_run "$ip" "
      if [ -d '$dest/.git' ]; then
        echo 'pulling $dest'; git -C '$dest' pull
      else
        rm -rf '$dest'
        git clone '$url' '$dest'
      fi
    "
  }

  # Framework repo (private)
  echo "  Cloning framework..."
  clone_or_pull "$auth_repo" "~/assistant"

  # MCP servers (public — no token needed)
  ssh_run "$ip" "mkdir -p ~/assistant/mcp-servers"
  for entry in "${MCP_REPOS[@]}"; do
    subdir="${entry%%|*}"; url="${entry##*|}"
    echo "  Cloning $subdir..."
    clone_or_pull "$url" "~/assistant/$subdir"
  done

  # Personal Claude config (private)
  echo "  Cloning .claude (skills, agents, plans)..."
  clone_or_pull "$auth_claude" "~/assistant/.claude"

  # Copy secrets (gitignored — never in any repo)
  echo "  Copying .env.production..."
  scp $SSH_OPTS -i "$SSH_KEY_PATH" \
    "$SCRIPT_DIR/.env.production" \
    "$VM_USER@$ip:~/assistant/.env.production"

  echo "  Copying Google OAuth tokens..."
  ssh_run "$ip" "mkdir -p ~/assistant/tokens/google"
  scp $SSH_OPTS -i "$SSH_KEY_PATH" \
    "$GOOGLE_TOKEN_SRC/token.json" \
    "$GOOGLE_TOKEN_SRC/credentials.json" \
    "$VM_USER@$ip:~/assistant/tokens/google/"

  echo "  Copying user context data (.claude/data/)..."
  ssh_run "$ip" "mkdir -p ~/assistant/.claude/data"
  scp $SSH_OPTS -i "$SSH_KEY_PATH" -r \
    "$SCRIPT_DIR/.claude/data/" \
    "$VM_USER@$ip:~/assistant/.claude/"

  echo "  ✓ All files in place"

  echo ""
  echo "[6/6] Starting containers..."
  ssh_run "$ip" "cd ~/assistant && chmod +x deploy.sh && ./deploy.sh deploy"

  local effective_domain="${DOMAIN:-$VM_NAME.$LOCATION.cloudapp.azure.com}"
  echo ""
  echo "  Configuring Nginx + TLS for $effective_domain..."
  ssh_run "$ip" "cd ~/assistant && ./deploy.sh setup-nginx '$effective_domain'"

  MCP_API_KEY=$(grep -E '^MCP_API_KEY=' "$SCRIPT_DIR/.env.production" | cut -d= -f2-)
  echo ""
  echo "═══════════════════════════════════════════════════════════════"
  echo " ✓  Deployment complete!"
  echo ""
  echo "  MCP servers at:"
  echo "    https://$effective_domain/journal-db/mcp"
  echo "    https://$effective_domain/garmin/mcp"
  echo "    https://$effective_domain/google/mcp"
  echo "    https://$effective_domain/places/mcp"
  echo "    https://$effective_domain/splitwise/mcp"
  echo ""
  echo "  Update ~/.claude.json mcpServers block using mcp-servers.cloud.example.json"
  echo "  Domain:  $effective_domain"
  echo "  API key: $MCP_API_KEY"
  echo "═══════════════════════════════════════════════════════════════"
}

# ─── Subcommands ───────────────────────────────────────────────────────────
case "${1:-all}" in
  all)    preflight; provision; deploy ;;
  deploy) preflight; deploy ;;
  ssh)    ssh $SSH_OPTS -i "$SSH_KEY_PATH" "$VM_USER@$(get_vm_ip)" ;;
  ip)     get_vm_ip ;;
  destroy)
    echo "WARNING: This permanently deletes the VM and all container data."
    read -p "Type 'yes' to confirm: " confirm
    [[ "$confirm" == "yes" ]] || { echo "Aborted."; exit 1; }
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait
    echo "Deletion queued."
    ;;
  *) echo "Usage: $0 {all|deploy|ssh|ip|destroy}"; exit 1 ;;
esac
