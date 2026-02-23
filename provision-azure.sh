#!/usr/bin/env bash
# Personal Assistant — Azure VM Provisioning Script
#
# Provisions an Azure B2ms VM, deploys all 5 MCP servers, and configures
# Nginx + TLS. Run this from your local machine (not the VM).
#
# Prerequisites:
#   1. Azure CLI logged in:  az login
#   2. Repo pushed to GitHub: see "Push repo to GitHub" section below
#   3. .env.production filled in (copy from .env.production.example)
#   4. tokens/google/token.json and credentials.json present locally
#   5. SSH key at ~/.ssh/id_rsa (or set SSH_KEY_PATH below)
#
# Usage:
#   chmod +x provision-azure.sh
#   ./provision-azure.sh           # full provision + deploy
#   ./provision-azure.sh deploy    # re-deploy to existing VM (skip provisioning)
#   ./provision-azure.sh ssh       # open an SSH session to the VM

set -euo pipefail

# ─── Configuration — edit these ────────────────────────────────────────────
RESOURCE_GROUP="assistant-rg"
LOCATION="eastus"                       # az account list-locations for options
VM_NAME="assistant-vm"
VM_SIZE="Standard_B2ms"                 # 2 vCPU, 8GB, ~$55/month
VM_USER="ubuntu"
SSH_KEY_PATH="${HOME}/.ssh/id_rsa"

# Your GitHub repo URL (HTTPS). Set after pushing: https://github.com/YOU/assistant
REPO_URL=""

# Domain for HTTPS. Options:
#   a) Your own domain: "mcp.yourdomain.com" (set DNS A record to VM public IP)
#   b) Azure public DNS: leave empty — script auto-uses VM's *.cloudapp.azure.com FQDN
DOMAIN=""

# ─── Helpers ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_OPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

get_vm_ip() {
  az vm show -g "$RESOURCE_GROUP" -n "$VM_NAME" \
    --query "publicIps" -d -o tsv 2>/dev/null
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
    sleep 10
    echo "  ... ($i/30)"
  done
  echo "ERROR: SSH never became available"
  exit 1
}

wait_for_cloud_init() {
  local ip="$1"
  echo "  Waiting for cloud-init (Docker install) to complete..."
  for i in {1..30}; do
    if ssh_run "$ip" "test -f /tmp/cloud-init-done" >/dev/null 2>&1; then
      echo "  ✓ Cloud-init done"
      return 0
    fi
    sleep 15
    echo "  ... ($i/30)"
  done
  echo "ERROR: Cloud-init timed out. SSH in and check: sudo cloud-init status"
  exit 1
}

# ─── Pre-flight checks ──────────────────────────────────────────────────────
preflight() {
  echo "[preflight] Checking prerequisites..."

  command -v az >/dev/null 2>&1 || { echo "ERROR: Azure CLI not installed."; exit 1; }
  az account show >/dev/null 2>&1 || { echo "ERROR: Not logged in. Run: az login"; exit 1; }

  [[ -f "$SCRIPT_DIR/.env.production" ]] || {
    echo "ERROR: .env.production not found. Copy .env.production.example and fill it in."
    exit 1
  }
  [[ -f "$SCRIPT_DIR/tokens/google/token.json" ]] || {
    echo "ERROR: tokens/google/token.json not found. Copy from your local .claude dir."
    exit 1
  }
  [[ -f "$SCRIPT_DIR/tokens/google/credentials.json" ]] || {
    echo "ERROR: tokens/google/credentials.json not found."
    exit 1
  }
  [[ -f "${SSH_KEY_PATH}.pub" ]] || {
    echo "ERROR: SSH public key not found at ${SSH_KEY_PATH}.pub"
    echo "  Generate one: ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa"
    exit 1
  }

  echo "  ✓ All prerequisites met"
}

# ─── Provision VM ──────────────────────────────────────────────────────────
provision() {
  echo ""
  echo "[1/6] Creating resource group '$RESOURCE_GROUP' in $LOCATION..."
  az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
  echo "  ✓ Resource group ready"

  echo ""
  echo "[2/6] Creating VM '$VM_NAME' ($VM_SIZE)..."
  echo "  (Cloud-init will install Docker automatically — takes ~3 min)"
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
  echo "[3/6] Opening ports 80 (HTTP) and 443 (HTTPS)..."
  az vm open-port --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --port 80 --priority 1001 --output none
  az vm open-port --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --port 443 --priority 1002 --output none
  echo "  ✓ Ports open"

  VM_IP=$(get_vm_ip)
  AZURE_FQDN="$VM_NAME.$LOCATION.cloudapp.azure.com"

  echo ""
  echo "  VM public IP:   $VM_IP"
  echo "  Azure FQDN:     $AZURE_FQDN"
  if [[ -n "$DOMAIN" ]]; then
    echo ""
    echo "  ── ACTION NEEDED ──────────────────────────────────────────"
    echo "  Add this DNS A record before running setup-nginx:"
    echo "    $DOMAIN  →  $VM_IP"
    echo "  ─────────────────────────────────────────────────────────"
  fi
}

# ─── Deploy app ─────────────────────────────────────────────────────────────
deploy() {
  local ip
  ip=$(get_vm_ip)
  echo ""
  echo "[4/6] Waiting for VM and cloud-init..."
  wait_for_ssh "$ip"
  wait_for_cloud_init "$ip"

  echo ""
  echo "[5/6] Copying files to VM..."

  # Clone repo (if REPO_URL set) or rsync the project directory
  if [[ -n "$REPO_URL" ]]; then
    echo "  Cloning $REPO_URL..."
    ssh_run "$ip" "git clone '$REPO_URL' ~/assistant || git -C ~/assistant pull"
  else
    echo "  No REPO_URL set — syncing local directory via rsync..."
    echo "  (Set REPO_URL at the top of this script after pushing to GitHub)"
    rsync -az --progress \
      --exclude='.git' \
      --exclude='*.db' \
      --exclude='__pycache__' \
      --exclude='node_modules' \
      --exclude='.venv' \
      --exclude='venv' \
      --exclude='.env.production' \
      --exclude='tokens/' \
      --exclude='llm_logs/' \
      --exclude='logs/' \
      -e "ssh $SSH_OPTS -i $SSH_KEY_PATH" \
      "$SCRIPT_DIR/" \
      "$VM_USER@$ip:~/assistant/"
  fi

  # Copy secrets (never in git)
  echo "  Copying .env.production..."
  scp $SSH_OPTS -i "$SSH_KEY_PATH" \
    "$SCRIPT_DIR/.env.production" \
    "$VM_USER@$ip:~/assistant/.env.production"

  echo "  Copying Google OAuth tokens..."
  ssh_run "$ip" "mkdir -p ~/assistant/tokens/google"
  scp $SSH_OPTS -i "$SSH_KEY_PATH" \
    "$SCRIPT_DIR/tokens/google/token.json" \
    "$SCRIPT_DIR/tokens/google/credentials.json" \
    "$VM_USER@$ip:~/assistant/tokens/google/"

  echo "  ✓ Files copied"

  echo ""
  echo "[6/6] Running docker compose deploy..."
  ssh_run "$ip" "cd ~/assistant && chmod +x deploy.sh && ./deploy.sh deploy"

  # Nginx + TLS
  local effective_domain="${DOMAIN:-$VM_NAME.$LOCATION.cloudapp.azure.com}"
  echo ""
  echo "  Configuring Nginx + TLS for $effective_domain..."
  ssh_run "$ip" "cd ~/assistant && ./deploy.sh setup-nginx '$effective_domain'"

  echo ""
  echo "═══════════════════════════════════════════════════════════"
  echo " ✓  Deployment complete!"
  echo ""
  echo "  MCP servers accessible at:"
  echo "    https://$effective_domain/journal-db/mcp"
  echo "    https://$effective_domain/garmin/mcp"
  echo "    https://$effective_domain/google/mcp"
  echo "    https://$effective_domain/places/mcp"
  echo "    https://$effective_domain/splitwise/mcp"
  echo ""
  echo "  Next: update ~/.claude.json using mcp-servers.cloud.example.json"
  echo "  Replace YOUR-DOMAIN with: $effective_domain"
  MCP_API_KEY=$(grep -E '^MCP_API_KEY=' "$SCRIPT_DIR/.env.production" | cut -d= -f2-)
  echo "  Replace YOUR-MCP-API-KEY with: $MCP_API_KEY"
  echo "═══════════════════════════════════════════════════════════"
}

# ─── Subcommands ────────────────────────────────────────────────────────────
case "${1:-all}" in
  all)
    preflight
    provision
    deploy
    ;;

  deploy)
    # Re-deploy to existing VM (skip az vm create)
    preflight
    deploy
    ;;

  ssh)
    ip=$(get_vm_ip)
    echo "Connecting to $VM_USER@$ip..."
    ssh $SSH_OPTS -i "$SSH_KEY_PATH" "$VM_USER@$ip"
    ;;

  ip)
    get_vm_ip
    ;;

  destroy)
    echo "WARNING: This will delete the VM and all its data."
    read -p "Type 'yes' to confirm: " confirm
    [[ "$confirm" == "yes" ]] || { echo "Aborted."; exit 1; }
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait
    echo "Resource group deletion queued."
    ;;

  *)
    echo "Usage: $0 {all|deploy|ssh|ip|destroy}"
    exit 1
    ;;
esac
