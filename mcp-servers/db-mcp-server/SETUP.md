# Complete Setup & Installation Guide

This guide covers all installation and deployment scenarios for the Journal MCP Server.

## 📋 Table of Contents

- [Quick Start (Local Development)](#quick-start-local-development)
- [PostgreSQL Installation](#postgresql-installation)
- [Package Installation](#package-installation)
- [Configuration](#configuration)
- [VS Code Extension Setup](#vs-code-extension-setup)
- [Claude Desktop Setup](#claude-desktop-setup)
- [HTTP Mode Setup (Web Clients)](#http-mode-setup-web-clients)
- [Azure Deployment](#azure-deployment)
- [Security & Best Practices](#security--best-practices)
- [Troubleshooting](#troubleshooting)

---

## Quick Start (Local Development)

### Prerequisites

- **Python 3.10+**
- **PostgreSQL 15+**
- **pip** (comes with Python)

### 3-Minute Setup

```bash
# 1. Clone/navigate to project
cd PostGreSQL_MCP_Server

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure database
cp .env.example .env
# Edit .env with your database credentials

# 4. Initialize database
python init_db.py init
python init_db.py seed  # Optional: add sample data

# 5. Start server

# Stdio mode (for Claude Desktop, VS Code Extension)
python server.py
# or
journal-mcp-server

# HTTP mode (for web clients, remote access)
python server.py --http
# or
journal-mcp-http
```

**🎉 Done!** Server is running and ready for LLM queries.

---

## PostgreSQL Installation

### Windows

**1. Download PostgreSQL:**
- Visit: https://www.postgresql.org/download/windows/
- Download the latest installer (PostgreSQL 15 or 16)
- Download the Windows x86-64 installer

**2. Run Installer:**
- Double-click the `.exe` file
- Keep default installation directory: `C:\Program Files\PostgreSQL\XX`
- Select all components (PostgreSQL Server, pgAdmin 4, Command Line Tools)

**3. Set Password:**
- **IMPORTANT:** Choose a strong password for the `postgres` superuser
- **Write it down!** You'll need this for your `.env` file

**4. Port Configuration:**
- Keep default port: `5432`

**5. Complete Installation:**
- Uncheck "Stack Builder" (not needed)
- Click "Finish"

**6. Verify Installation:**

```bash
# Check if PostgreSQL is running
services.msc  # Look for "postgresql-x64-XX" service

# Test connection
psql -U postgres
# Enter your password when prompted
\q  # Exit
```

### macOS

```bash
# Install via Homebrew
brew install postgresql@15

# Start PostgreSQL service
brew services start postgresql@15

# Create your user (optional)
createuser -s postgres

# Test connection
psql postgres
```

### Linux (Ubuntu/Debian)

```bash
# Install PostgreSQL
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start service
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Set password for postgres user
sudo -u postgres psql
ALTER USER postgres PASSWORD 'your_password';
\q

# Test connection
psql -U postgres -h localhost
```

### Create Database

**Option A: Using pgAdmin (GUI - Easier)**

1. Open pgAdmin 4 from Start menu
2. Connect to "PostgreSQL XX" server (enter password)
3. Right-click "Databases" → "Create" → "Database"
4. Database name: `assistant_db_test` (or any name you prefer)
5. Click "Save"

**Option B: Using Command Line**

```bash
# Connect as postgres user
psql -U postgres

# Create database
CREATE DATABASE assistant_db_test;

# Verify
\l

# Exit
\q
```

**Note:** Use the same database name in your `.env` file as `DB_NAME`.

---

## Package Installation

### Install as Python Package

Installing the server as a package makes it path-independent and easier to use:

```bash
cd PostGreSQL_MCP_Server
pip install -e .
```

This creates a `journal-mcp-server` command in your PATH.

**Benefits:**
- ✅ No absolute paths needed
- ✅ Works from any directory
- ✅ Survives code refactoring
- ✅ Standard Python package management

### Verify Installation

```bash
# Check command is available
journal-mcp-server

# Or check installation location
which journal-mcp-server   # macOS/Linux
where journal-mcp-server   # Windows

# View package info
pip show journal-mcp-server
```

### Uninstall

```bash
pip uninstall journal-mcp-server
```

---

## Configuration

### Configuration Priority System

The server uses a **3-tier configuration system**:

1. **Environment Variables** (highest priority) - Set by MCP clients
2. **`.env` File** (fallback) - For local development
3. **Default Values** (lowest priority) - Hardcoded defaults

**How It Works:**

```python
load_dotenv(override=False)  # Respects existing env vars
```

This means:
- ✅ VS Code/Claude Desktop settings override `.env`
- ✅ `.env` used when no env vars set
- ✅ Defaults used if nothing specified

### Environment Variables

**Required:**
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=assistant_db_test
DB_USER=postgres
DB_PASSWORD=your_password
```

**Optional:**
```bash
APP_ENV=development            # development/test/production
DB_SSL_MODE=prefer             # disable/prefer/require
DB_MIN_POOL_SIZE=2             # Connection pool min
DB_MAX_POOL_SIZE=10            # Connection pool max
```

### Create `.env` File

```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env  # or use your favorite editor
```

**Example `.env`:**

```bash
# Application Environment
APP_ENV=development

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=assistant_db_test
DB_USER=postgres
DB_PASSWORD=your_secure_password
DB_SSL_MODE=prefer

# Connection Pool Settings
DB_MIN_POOL_SIZE=2
DB_MAX_POOL_SIZE=10
```

**🔒 Security Note:**

Your `.env` file is in `.gitignore` - passwords are never committed to git!

### Verify Configuration

```bash
python show_config.py
```

Shows:
- Current environment mode
- Database connection details
- Which config source is being used

### Test Database Configuration

For running tests, you can override database settings:

```bash
# .env file
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=yourpassword

# Optional test overrides
TEST_DB_NAME=my_custom_test_db
TEST_DB_HOST=localhost
TEST_DB_PORT=5432
```

When `APP_ENV=test` (automatically set by test runner), the system uses `TEST_DB_*` variables or defaults to `personal_journal_test`.

---

## VS Code Extension Setup

The Journal MCP Server can be integrated with VS Code via the MCP extension.

### 1. Install the Package

```bash
cd PostGreSQL_MCP_Server
pip install -e .
```

### 2. Add Python Scripts to PATH

**Windows:**

```bash
# Add to PATH environment variable:
C:\Users\<username>\AppData\Local\Programs\Python\Python3X\Scripts
```

**macOS/Linux:**

Usually already in PATH. If not, add to `~/.bashrc` or `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

### 3. Configure VS Code Settings

Add to `.vscode/settings.json` or User Settings:

```json
{
  "journalMcp.serverCommand": "journal-mcp-server",
  "journalMcp.environment": "development",
  "journalMcp.database.host": "localhost",
  "journalMcp.database.port": 5432,
  "journalMcp.database.user": "postgres",
  "journalMcp.database.password": "your_password",
  "journalMcp.database.name": "assistant_db_test"
}
```

**Available Settings:**

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `journalMcp.serverCommand` | string | `journal-mcp-server` | Command to run server |
| `journalMcp.environment` | string | `development` | Environment mode |
| `journalMcp.database.host` | string | `localhost` | PostgreSQL host |
| `journalMcp.database.port` | number | `5432` | PostgreSQL port |
| `journalMcp.database.user` | string | `postgres` | Database user |
| `journalMcp.database.password` | string | | Database password |
| `journalMcp.database.name` | string | `journal_db` | Database name |

### 4. Reload VS Code

Press `Ctrl+Shift+P` → "Reload Window"

### 5. Test Connection

The extension passes database credentials as environment variables to the server, which take precedence over your `.env` file.

### Using HTTP Mode with VS Code

For remote or HTTP-based connections, you can configure VS Code to connect via the Streamable HTTP transport:

**1. Start the HTTP server:**
```bash
python server.py --http --port 3333
```

**2. Update VS Code MCP configuration (`mcp.json`):**
```json
{
  "mcpServers": {
    "Personal Journal": {
      "type": "http",
      "url": "http://localhost:3333/mcp"
    }
  }
}
```

**3. Reload VS Code and test**

This is useful for:
- Remote server connections
- Debugging HTTP mode
- Connecting multiple clients to one server
- Testing MCP HTTP compliance

---

## Claude Desktop Setup

### 1. Install the Package

```bash
cd PostGreSQL_MCP_Server
pip install -e .
```

Verify:
```bash
journal-mcp-server  # Should start the server
```

### 2. Configure Claude Desktop

Claude Desktop reads MCP configuration from:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

**Edit the config file:**

```json
{
  "mcpServers": {
    "personal-journal": {
      "command": "journal-mcp-server",
      "env": {
        "APP_ENV": "development"
      }
    }
  }
}
```

**Note:** The server will load database credentials from `.env.development` in the server directory. Ensure that file exists and contains the correct `DB_PASSWORD`.

**Multiple Environments (Optional):**

```json
{
  "mcpServers": {
    "journal-dev": {
      "command": "journal-mcp-server",
      "env": {
        "APP_ENV": "development"
      }
    },
    "journal-test": {
      "command": "journal-mcp-server",
      "env": {
        "APP_ENV": "test"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

Close and reopen Claude Desktop completely.

### 4. Verify Connection

In Claude, try:
```
Can you show me my recent workouts?
```

Claude should now have access to your journal database!

### Alternative: Full Python Path

If `journal-mcp-server` is not in PATH:

**Windows:**
```json
{
  "mcpServers": {
    "personal-journal": {
      "command": "C:\\Users\\<username>\\AppData\\Local\\Programs\\Python\\Python310\\Scripts\\journal-mcp-server.exe",
      "env": { /* ... */ }
    }
  }
}
```

**macOS/Linux:**
```json
{
  "mcpServers": {
    "personal-journal": {
      "command": "/usr/local/bin/journal-mcp-server",
      "env": { /* ... */ }
    }
  }
}
```

### Using with Other MCP Clients

**Continue.dev Configuration:**

Add to `~/.continue/config.json`:

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "journal-mcp-server",
          "env": {
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
            "DB_USER": "postgres",
            "DB_PASSWORD": "your_password",
            "DB_NAME": "assistant_db_test"
          }
        }
      }
    ]
  }
}
```

**Custom Python Client:**

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="journal-mcp-server",
    env={
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_USER": "postgres",
        "DB_PASSWORD": "your_password",
        "DB_NAME": "assistant_db_test"
    }
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        # Use session to interact with server
        result = await session.call_tool("execute_sql_query", {"query": "SELECT * FROM workouts LIMIT 5"})
```

---

## HTTP Mode Setup (Web Clients)

The server can run in HTTP mode using **Streamable HTTP** transport per the MCP specification. This provides a single endpoint for all JSON-RPC communication, ideal for web applications, remote clients, and API integrations.

### Starting the HTTP Server

```bash
# Command-line flag with options
python server.py --http --port 3333 --host 127.0.0.1

# Using just defaults (port 3333, host 127.0.0.1)
python server.py --http
```

### Configuration

**Environment Variables:**
```bash
# Database configuration (same as stdio mode)
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=personal_journal
export DB_USER=postgres
export DB_PASSWORD=your_password
```

**Command-line Options:**
- `--http` - Enable HTTP mode (Streamable HTTP transport)
- `--port` - Port to listen on (default: 3333)
- `--host` - Host to bind to (default: 127.0.0.1)

### Available Endpoints

Once running on `http://localhost:3333`:

**Main MCP Endpoint (POST):**
```bash
POST /mcp
Content-Type: application/json
MCP-Protocol-Version: 2024-11-05

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "get_database_schema",
    "arguments": {}
  }
}
```

**Main MCP Endpoint (GET) - Optional SSE stream:**
```bash
GET /mcp
Accept: text/event-stream
```

**Health Check (separate endpoint):**
```bash
GET /healthz
```

### Testing the HTTP Server

**Using curl:**
```bash
# Health check
curl http://localhost:3333/healthz

# Initialize connection
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -H "MCP-Protocol-Version: 2024-11-05" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "test", "version": "1.0"}
    }
  }'

# List available tools
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'

# Call a tool
curl -X POST http://localhost:3333/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "get_database_schema",
      "arguments": {}
    }
  }'
```

**Using Python:**
```python
import requests

# Health check
response = requests.get("http://localhost:3333/healthz")
print(response.json())

# Initialize
response = requests.post("http://localhost:3333/mcp", json={
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "python-client", "version": "1.0"}
    }
})
print(response.json())

# Call a tool
response = requests.post("http://localhost:3333/mcp", json={
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "search_people",
        "arguments": {"search_term": "John"}
    }
})
print(response.json())
```

### Supported JSON-RPC Methods

All standard MCP methods are supported via the `/mcp` endpoint:

- `initialize` - Initialize MCP session
- `ping` - Keep-alive notification
- `notifications/initialized` - Client ready notification
- `tools/list` - List all available tools
- `tools/call` - Execute a specific tool
- `prompts/list` - List available prompts
- `prompts/get` - Get a specific prompt
- `resources/list` - List available resources
- `resources/read` - Read resource content

### Feature Parity

Both stdio and HTTP modes use the **same handlers and tools**:

| Feature | Stdio Mode | HTTP Mode (Streamable HTTP) |
|---------|-----------|-----------|
| Connection | stdin/stdout | HTTP (single /mcp endpoint) |
| Transport | Standard MCP stdio | Standard MCP Streamable HTTP |
| Use Case | Claude Desktop, VS Code local | Web apps, APIs, VS Code remote |
| Auth | Process-level | Add middleware |
| Concurrent Clients | No (1:1) | Yes (many:1) |
| Tool Execution | ✅ Identical | ✅ Identical |
| Performance | Low latency | Network latency |
| Streaming | Built-in | SSE in HTTP responses |

### Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install -e .

EXPOSE 3333

CMD ["python", "server.py", "--http", "--host", "0.0.0.0", "--port", "3333"]
```

**Build and run:**
```bash
docker build -t journal-mcp-http .
docker run -p 3333:3333 \
  -e DB_HOST=your-db-host \
  -e DB_NAME=personal_journal \
  -e DB_USER=postgres \
  -e DB_PASSWORD=your_password \
  journal-mcp-http
```

### Security Considerations

For production deployments:

1. **Authentication**: Add JWT or API key middleware in `server/transport/http.py`
2. **Origin Validation**: Implement Origin header validation for production
3. **HTTPS**: Use TLS certificates for encrypted connections
4. **Rate Limiting**: Prevent abuse with rate limiting middleware
5. **Reverse Proxy**: Deploy behind nginx or traefik
6. **Environment Variables**: Use secrets management (Azure Key Vault, AWS Secrets Manager)
7. **Protocol Version**: Validate MCP-Protocol-Version header

**Example Origin validation:**
```python
# In server/transport/http.py
ALLOWED_ORIGINS = ["https://yourdomain.com", "https://app.example.com"]

@app.post("/mcp")
async def mcp_post_endpoint(request: Request, ...):
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse(
            status_code=403,
            content={"error": "Origin not allowed"}
        )
    # ... rest of handler
```

### Troubleshooting

**Port already in use:**
```bash
# Change the port
python server.py --http --port 3334
```

**Cannot connect to database:**
```bash
# Verify database environment variables
python show_config.py

# Test database connection
psql -h $DB_HOST -U $DB_USER -d $DB_NAME
```

**Missing dependencies:**
```bash
# Install HTTP mode dependencies
pip install fastapi uvicorn

# Or reinstall the package
pip install -e .
```

**VS Code cannot connect:**
```bash
# Ensure correct URL format in mcp.json
{
  "mcpServers": {
    "Personal Journal": {
      "type": "http",
      "url": "http://localhost:3333/mcp"
    }
  }
}

# Verify server is running
curl http://localhost:3333/healthz
```

---

## Azure Deployment

### Prerequisites

- Azure subscription
- Azure CLI installed
- PostgreSQL Flexible Server (recommended)

### 1. Install Azure CLI

**Windows:**
```powershell
winget install Microsoft.AzureCLI
```

**macOS:**
```bash
brew install azure-cli
```

**Linux:**
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### 2. Login to Azure

```bash
az login
az account set --subscription "<your-subscription-id>"
```

### 3. Set Variables

```bash
RESOURCE_GROUP="journal-rg"
LOCATION="eastus"
DB_SERVER_NAME="journal-db-$(whoami)"
DB_NAME="journal_db"
DB_ADMIN_USER="dbadmin"
DB_ADMIN_PASSWORD="SecurePassword123!"  # Change this!
```

### 4. Create Resource Group

```bash
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
```

### 5. Create PostgreSQL Flexible Server

```bash
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $DB_SERVER_NAME \
  --location $LOCATION \
  --admin-user $DB_ADMIN_USER \
  --admin-password $DB_ADMIN_PASSWORD \
  --sku-name Standard_B2s \
  --tier Burstable \
  --storage-size 128 \
  --version 15 \
  --public-access 0.0.0.0 \
  --storage-auto-grow Enabled
```

**Pricing Tiers:**
- `Standard_B1ms` - 1 vCore, 2 GB RAM (~$12/month) - Development
- `Standard_B2s` - 2 vCore, 4 GB RAM (~$60/month) - Production
- `Standard_D2s_v3` - 2 vCore, 8 GB RAM (~$140/month) - High Performance

### 6. Configure Firewall

**Allow your IP:**

```bash
MY_IP=$(curl -s https://api.ipify.org)

az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $DB_SERVER_NAME \
  --rule-name AllowMyIP \
  --start-ip-address $MY_IP \
  --end-ip-address $MY_IP
```

**Allow Azure services:**

```bash
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $DB_SERVER_NAME \
  --rule-name AllowAzure \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

### 7. Create Database

```bash
az postgres flexible-server db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $DB_SERVER_NAME \
  --database-name $DB_NAME
```

### 8. Configure SSL/TLS

**Download SSL certificate:**

```bash
curl -o root.crt https://dl.cacerts.digicert.com/DigiCertGlobalRootCA.crt.pem
```

### 9. Update `.env` for Azure

```bash
APP_ENV=production
DB_HOST=${DB_SERVER_NAME}.postgres.database.azure.com
DB_PORT=5432
DB_NAME=journal_db
DB_USER=${DB_ADMIN_USER}
DB_PASSWORD=${DB_ADMIN_PASSWORD}
DB_SSL_MODE=require
```

### 10. Initialize Azure Database

```bash
# Verify configuration
python show_config.py

# Initialize schema
python init_db.py init

# Optional: seed data
python init_db.py seed
```

### 11. Deploy Server (Optional)

**Option A: Azure Container Instances**

```bash
# Create container registry
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name journalregistry \
  --sku Basic

# Build and push image
az acr build \
  --registry journalregistry \
  --image journal-mcp-server:latest \
  --file Dockerfile .

# Deploy container
az container create \
  --resource-group $RESOURCE_GROUP \
  --name journal-mcp-server \
  --image journalregistry.azurecr.io/journal-mcp-server:latest \
  --environment-variables \
    APP_ENV=production \
    DB_HOST=${DB_SERVER_NAME}.postgres.database.azure.com \
    DB_PORT=5432 \
    DB_USER=${DB_ADMIN_USER} \
    DB_PASSWORD=${DB_ADMIN_PASSWORD} \
    DB_NAME=$DB_NAME \
    DB_SSL_MODE=require \
  --ports 8000
```

**Option B: Azure App Service**

```bash
# Create App Service plan
az appservice plan create \
  --resource-group $RESOURCE_GROUP \
  --name journal-plan \
  --sku B1 \
  --is-linux

# Create web app
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan journal-plan \
  --name journal-mcp-app \
  --runtime "PYTHON:3.11"

# Configure app settings
az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name journal-mcp-app \
  --settings \
    APP_ENV=production \
    DB_HOST=${DB_SERVER_NAME}.postgres.database.azure.com \
    DB_PORT=5432 \
    DB_USER=${DB_ADMIN_USER} \
    DB_PASSWORD=${DB_ADMIN_PASSWORD} \
    DB_NAME=$DB_NAME \
    DB_SSL_MODE=require

# Deploy code
az webapp up \
  --resource-group $RESOURCE_GROUP \
  --name journal-mcp-app \
  --runtime PYTHON:3.11
```

### 12. Secure Secrets with Key Vault (Recommended)

```bash
# Create Key Vault
az keyvault create \
  --resource-group $RESOURCE_GROUP \
  --name journal-kv \
  --location $LOCATION

# Store database password
az keyvault secret set \
  --vault-name journal-kv \
  --name db-password \
  --value $DB_ADMIN_PASSWORD

# Store connection string
CONNECTION_STRING="postgresql://${DB_ADMIN_USER}:${DB_ADMIN_PASSWORD}@${DB_SERVER_NAME}.postgres.database.azure.com:5432/${DB_NAME}?sslmode=require"

az keyvault secret set \
  --vault-name journal-kv \
  --name db-connection-string \
  --value $CONNECTION_STRING
```

**Retrieve in application:**

```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()
client = SecretClient(vault_url="https://journal-kv.vault.azure.net/", credential=credential)

db_password = client.get_secret("db-password").value
```

---

## Security & Best Practices

### Password Security

**❌ Don't do this:**

```json
{
  "env": {
    "DB_PASSWORD": "plaintext_password_in_config"
  }
}
```

**✅ Better approaches:**

1. **Use environment variables:**
   ```bash
   export DB_PASSWORD=your_password
   journal-mcp-server
   ```

2. **Restrict file permissions:**
   ```bash
   chmod 600 claude_desktop_config.json  # Owner read/write only
   chmod 600 .env
   ```

3. **Use Azure Key Vault** (for production)

4. **Use PostgreSQL `.pgpass` file** (for local development)

### Read-Only Database User

For production, create a read-only user:

```sql
-- Create read-only user
CREATE USER journal_readonly WITH PASSWORD 'secure_password';

-- Grant read-only permissions
GRANT CONNECT ON DATABASE assistant_db_test TO journal_readonly;
GRANT USAGE ON SCHEMA public TO journal_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO journal_readonly;

-- Auto-grant for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public 
GRANT SELECT ON TABLES TO journal_readonly;
```

Use this in your MCP config:
```json
{
  "env": {
    "DB_USER": "journal_readonly",
    "DB_PASSWORD": "secure_password"
  }
}
```

### Network Security

**Azure:**
- ✅ Enable SSL/TLS (`DB_SSL_MODE=require`)
- ✅ Use private endpoints (no public IP)
- ✅ Whitelist specific IPs only
- ✅ Enable Azure Defender for PostgreSQL

**Local:**
- ✅ Use `localhost` only (not `0.0.0.0`)
- ✅ Enable firewall rules
- ✅ Use SSL even for local connections

### Connection Pooling

For production workloads:

```bash
DB_MIN_POOL_SIZE=5
DB_MAX_POOL_SIZE=20
```

Monitor with:
```sql
SELECT * FROM pg_stat_activity;
```

---

## Troubleshooting

### PostgreSQL Connection Issues

**Error: Connection refused**

```bash
# Check if PostgreSQL is running (Windows)
services.msc  # Look for "postgresql-x64-XX"

# Check if PostgreSQL is running (Linux/Mac)
sudo systemctl status postgresql

# Test connection manually
psql -h localhost -U postgres
```

**Error: Password authentication failed**

```bash
# Reset password (as postgres user)
sudo -u postgres psql
ALTER USER postgres PASSWORD 'new_password';
\q

# Update .env file with new password
```

**Error: Database does not exist**

```bash
# List databases
psql -U postgres -l

# Create database
psql -U postgres
CREATE DATABASE assistant_db_test;
\q
```

### Package Installation Issues

**Error: journal-mcp-server command not found**

```bash
# Check if installed
pip show journal-mcp-server

# Check PATH
echo $PATH  # Linux/Mac
echo %PATH%  # Windows

# Reinstall
pip uninstall journal-mcp-server
pip install -e /path/to/PostGreSQL_MCP_Server

# Add Scripts to PATH (Windows)
# C:\Users\<username>\AppData\Local\Programs\Python\Python3X\Scripts
```

**Error: Permission denied**

```bash
# Run as administrator (Windows)
# Or use --user flag
pip install --user -e .
```

### Configuration Issues

**Wrong database being used**

```bash
# Check current configuration
python show_config.py

# Set environment explicitly
export APP_ENV=development
python show_config.py
```

**Environment variables not loading**

```bash
# Verify .env file location
ls -la .env

# Test environment variable priority
DB_HOST=override-test python -c "from dotenv import load_dotenv; import os; load_dotenv(override=False); print(os.getenv('DB_HOST'))"
```

### Claude Desktop Issues

**Server not starting**

1. **Check logs:**
   - Windows: Event Viewer or Claude Desktop logs
   - macOS/Linux: `~/.config/Claude/logs/`

2. **Test manually:**
   ```bash
   export DB_HOST=localhost
   export DB_PORT=5432
   export DB_USER=postgres
   export DB_PASSWORD=your_password
   export DB_NAME=assistant_db_test
   
   journal-mcp-server
   ```

3. **Validate JSON config:**
   ```bash
   cat claude_desktop_config.json | python -m json.tool
   ```

**Configuration not loading**

1. **Verify config file location:**
   ```bash
   # Windows
   echo %APPDATA%\Claude\claude_desktop_config.json
   
   # macOS
   echo ~/Library/Application\ Support/Claude/claude_desktop_config.json
   
   # Linux
   echo ~/.config/Claude/claude_desktop_config.json
   ```

2. **Check Claude Desktop version:**
   - MCP support requires Claude Desktop 0.7.0+

### Azure Deployment Issues

**Error: Cannot connect to Azure PostgreSQL**

```bash
# Check firewall rules
az postgres flexible-server firewall-rule list \
  --resource-group $RESOURCE_GROUP \
  --name $DB_SERVER_NAME

# Add your current IP
MY_IP=$(curl -s https://api.ipify.org)
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $DB_SERVER_NAME \
  --rule-name MyCurrentIP \
  --start-ip-address $MY_IP \
  --end-ip-address $MY_IP
```

**Error: SSL required**

```bash
# Ensure SSL mode is set
export DB_SSL_MODE=require

# Download certificate if needed
curl -o root.crt https://dl.cacerts.digicert.com/DigiCertGlobalRootCA.crt.pem
```

**High costs**

```bash
# Switch to lower tier
az postgres flexible-server update \
  --resource-group $RESOURCE_GROUP \
  --name $DB_SERVER_NAME \
  --sku-name Standard_B1ms

# Enable auto-shutdown (if supported)
# Or manually stop when not in use
az postgres flexible-server stop \
  --resource-group $RESOURCE_GROUP \
  --name $DB_SERVER_NAME
```

### Test Database Issues

**Error: Test database not found**

```bash
# Create test database
python run_tests.py --setup-only

# Or manually
psql -U postgres
CREATE DATABASE personal_journal_test;
\q
```

**Tests using wrong database**

```bash
# Verify APP_ENV is set
python show_config.py

# Run tests (automatically sets APP_ENV=test)
python run_tests.py

# Manual override
export APP_ENV=test
python run_tests.py
```

---

## Getting Help

If you encounter issues not covered here:

1. **Check logs:**
   - Server: Check terminal output
   - Claude Desktop: `~/.config/Claude/logs/`
   - PostgreSQL: Check database logs

2. **Verify configuration:**
   ```bash
   python show_config.py
   ```

3. **Test components individually:**
   ```bash
   # Test database connection
   psql -h localhost -U postgres
   
   # Test package installation
   journal-mcp-server
   
   # Test Python imports
   python -c "from database import init_database"
   ```

4. **Open a GitHub issue** with:
   - Error messages
   - Configuration (redact passwords!)
   - Steps to reproduce
   - Operating system and versions

---

**For project overview and usage examples, see [README.md](README.md).**
