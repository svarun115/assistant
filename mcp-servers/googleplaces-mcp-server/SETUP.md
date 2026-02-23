# Setup Guide: Google Places HTTP MCP Server

This is a WebSocket-based MCP (Model Context Protocol) server using JSON-RPC for bidirectional communication. It provides access to Google Places API, Weather API, and Elevation API through a modern MCP-compliant interface.

## Prerequisites

1. **Node.js**: Version 18 or higher
2. **Google Cloud Account**: For Places API access
3. **Google Places API Key**: With Places API (New) enabled

## Step 1: Get Google Places API Key

### Create Google Cloud Project

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" → "New Project"
3. Name your project (e.g., "Google Places MCP")
4. Click "Create"

### Enable Required APIs

1. In the Cloud Console, go to "APIs & Services" → "Library"
2. Enable the following APIs (search and enable each):
   - **Places API (New)** - for place search and details
   - **Weather API** - for current weather conditions (optional)
   - **Elevation API** - for elevation data (optional)

**Note:** All three APIs use the same API key.

### Create API Key

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "API Key"
3. Copy your API key (starts with `AIza...`)
4. Click "Restrict Key" (recommended)
   - Under "API restrictions", select "Restrict key"
   - Check the APIs you enabled (Places API (New), Weather API, Elevation API)
   - Click "Save"

## Step 2: Install the MCP Server

```bash
cd "c:\Users\vasashid\AI Projects\Assistant\googleplaces-mcp-server"
npm install
npm run build
npm install -g .
```

Verify installation:
```bash
googleplaces-mcp-server --version
```

Expected output: `googleplaces-mcp-server version 1.0.0`

## Step 3: Configure API Key

### Option A: Environment Variable (Recommended)

**On Windows (bash.exe):**
```bash
export GOOGLE_PLACES_API_KEY="AIza..."
```

Then verify it's set:
```bash
echo $GOOGLE_PLACES_API_KEY
```

To make it permanent, add it to your `.bashrc`:
```bash
echo 'export GOOGLE_PLACES_API_KEY="AIza..."' >> ~/.bashrc
source ~/.bashrc
```

**On macOS/Linux:**
```bash
export GOOGLE_PLACES_API_KEY="AIza..."
```

Add to `.bashrc`, `.zshrc`, etc. for permanent setup.

**On Windows (PowerShell):**
```powershell
$env:GOOGLE_PLACES_API_KEY="AIza..."
```

For permanent setup, add to PowerShell profile:
```powershell
Add-Content $PROFILE 'export GOOGLE_PLACES_API_KEY="AIza..."'
```

### Option B: Pass as Environment Variable When Starting

**bash.exe (Windows):**
```bash
export GOOGLE_PLACES_API_KEY="AIza..."
googleplaces-mcp-server
```

**PowerShell (Windows):**
```powershell
$env:GOOGLE_PLACES_API_KEY="AIza..."
googleplaces-mcp-server
```

### Option C: Add to MCP Client Configuration

For clients that support HTTP MCP servers, configure the server URL:

**Example for Claude Desktop:**
```json
{
  "mcpServers": {
    "googleplaces": {
      "url": "http://localhost:3000",
      "env": {
        "GOOGLE_PLACES_API_KEY": "AIza..."
      }
    }
  }
}
```

## Step 4: Configure for Your MCP Client

### For VS Code (with MCP Client Extension)

1. Install the MCP Client extension in VS Code
2. Open VS Code settings (Ctrl+, or Cmd+,)
3. Search for "mcp" to find MCP client settings
4. Add a new server configuration:

```json
{
  "mcp.servers": {
    "googleplaces": {
      "url": "ws://localhost:3000",
      "env": {
        "GOOGLE_PLACES_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### For Claude Desktop

Edit `claude_desktop_config.json` (location varies by OS):

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
**Linux:** `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "googleplaces": {
      "url": "ws://localhost:3000",
      "env": {
        "GOOGLE_PLACES_API_KEY": "AIza..."
      }
    }
  }
}
```

## Step 5: Start the HTTP Server

In a terminal, start the server with:

**On macOS/Linux:**
```bash
GOOGLE_PLACES_API_KEY="AIza..." googleplaces-mcp-server
```

**On Windows (with bash.exe):**
```bash
export GOOGLE_PLACES_API_KEY="AIza..."
googleplaces-mcp-server
```

**On Windows (PowerShell):**
```powershell
$env:GOOGLE_PLACES_API_KEY="AIza..."
googleplaces-mcp-server
```

**On Windows (Command Prompt):**
```cmd
set GOOGLE_PLACES_API_KEY=AIza...
googleplaces-mcp-server
```

The server will start on `ws://localhost:3000` (WebSocket) by default.

To use a different port (bash.exe example):
```bash
export PORT=8080
export GOOGLE_PLACES_API_KEY="AIza..."
googleplaces-mcp-server
```

Keep this terminal running. Your MCP client will connect via WebSocket to `ws://localhost:3000`.

## Step 6: Test the Server

### Health Check

```bash
curl http://localhost:3000/health
```

Expected output:
```json
{"status":"ok","version":"1.0.0"}
```

### Test with WebSocket (Node.js)

Create a test file `test-ws.mjs`:

```javascript
import WebSocket from 'ws';

const ws = new WebSocket('ws://localhost:3000');

ws.on('open', () => {
  console.log('Connected to server');

  // Initialize
  ws.send(JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {}
  }));
});

ws.on('message', (data) => {
  const response = JSON.parse(data);
  console.log('Received:', JSON.stringify(response, null, 2));

  // After initialization, list tools
  if (response.id === 1) {
    ws.send(JSON.stringify({
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/list',
      params: {}
    }));
  }

  // After listing tools, call a tool
  if (response.id === 2) {
    ws.send(JSON.stringify({
      jsonrpc: '2.0',
      id: 3,
      method: 'tools/call',
      params: {
        name: 'search_places',
        arguments: {
          query: 'coffee shops',
          location: { lat: 47.6062, lng: -122.3321 },
          radius: 1000
        }
      }
    }));
  }

  // Close after tool response
  if (response.id === 3) {
    ws.close();
  }
});

ws.on('error', (error) => {
  console.error('WebSocket error:', error);
});
```

Run:
```bash
npm install ws
node test-ws.mjs
```

## API Endpoints

### WebSocket Connection (JSON-RPC 2.0)

Connect to `ws://localhost:3000` using a WebSocket client. All communication uses JSON-RPC 2.0 over the persistent WebSocket connection.

**Initialize Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

**List Tools Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

**Call Tool Request:**
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "search_places",
    "arguments": {
      "query": "coffee shops",
      "location": {"lat": 47.6062, "lng": -122.3321},
      "radius": 1000
    }
  }
}
```

**Response Format:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { "...": "..." }
}
```

### Health Check (HTTP)

```bash
curl http://localhost:3000/health
```

Expected output:
```json
{"status":"ok","version":"1.0.0"}
```

## Available Tools

For detailed tool descriptions, parameters, and examples, see [README.md](README.md#available-tools).

Quick reference:
- **search_places** - Find places by text query
- **get_place_details** - Get full place information by Place ID
- **get_weather** - Get current weather conditions for coordinates
- **get_elevation** - Get elevation data for locations

## Environment Variables

- `GOOGLE_PLACES_API_KEY` (required): Your Google Places API key
- `PORT` (optional): Port to run the server on (default: 3000)

## Troubleshooting

### "'export' is not recognized" error (Windows)

You're using Command Prompt or PowerShell, not bash. Use the correct syntax for your shell:

**Command Prompt:**
```cmd
set GOOGLE_PLACES_API_KEY=your_api_key
googleplaces-mcp-server
```

**PowerShell:**
```powershell
$env:GOOGLE_PLACES_API_KEY="your_api_key"
googleplaces-mcp-server
```

### "API key not found" error

- Check that `GOOGLE_PLACES_API_KEY` environment variable is set
- Verify the key is correctly copied (no extra spaces)
- Make sure you've restarted your terminal/VS Code

### "Places API has not been used" error

- Go to Google Cloud Console
- Verify "Places API (New)" is enabled (not the old "Places API")
- Wait a few minutes for changes to propagate

### "This API project is not authorized" error

- Check API key restrictions
- Ensure the API key is allowed to use Places API
- Verify your billing is enabled (Google requires it even for free tier)

### Port already in use

If port 3000 is already in use, specify a different port:
```bash
PORT=8080 GOOGLE_PLACES_API_KEY="AIza..." googleplaces-mcp-server
```

### Connection refused

- Ensure the server is running
- Check that you're using the correct host and port
- Verify firewall settings aren't blocking the connection

## API Usage Limits

Google Places API (New) has a free tier with usage limits:
- **Free tier**: $200 credit per month
- **Place Search**: ~$0.032 per request
- **Place Details**: ~$0.017 per request

With the free tier, you can make approximately:
- 6,250 place searches per month
- 11,764 place details requests per month

Monitor usage in Google Cloud Console → "APIs & Services" → "Dashboard"

## Next Steps

1. Integrate the HTTP server URL into your MCP client
2. Start making requests to the server endpoints
3. Set up error logging for production use
4. Consider caching place results to reduce API calls
5. Monitor API usage and costs in Google Cloud Console

## Support

For issues related to:
- **MCP Server**: Check GitHub issues at [svarun115/googleplaces-mcp-server](https://github.com/svarun115/googleplaces-mcp-server)
- **Google Places API**: See [official documentation](https://developers.google.com/maps/documentation/places/web-service/overview)
