/**
 * Streamable HTTP transport for Google Places MCP (Model Context Protocol).
 * 
 * Implements the official MCP Streamable HTTP specification:
 * - Single /mcp endpoint for all JSON-RPC communication
 * - POST /mcp: accepts JSON-RPC requests, responds with JSON or SSE
 * - GET /mcp: optional persistent SSE stream for server notifications
 * - /healthz: health check endpoint (separate from /mcp)
 * 
 * This module wraps tool handlers with HTTP transport.
 */

import express, { Request, Response, Express } from 'express';
import { isValidJsonRpc, isNotification, createSuccessResponse, createErrorResponse, JsonRpcError, validateMcpProtocolVersion } from '../utils/jsonrpc.js';
import { formatSseEvent } from '../utils/sse.js';

const GOOGLE_PLACES_API_KEY = process.env.GOOGLE_PLACES_API_KEY;
const PLACES_API_BASE = 'https://places.googleapis.com/v1';

// Tool handler functions (reused from main server)
async function handleSearchPlaces(args: any) {
  const { query, location, radius = 5000 } = args;
  console.error(`[DEBUG] Searching places for: "${query}"`);
  
  const requestBody: any = {
    textQuery: query,
  };

  if (location?.lat && location?.lng) {
    requestBody.locationBias = {
      circle: {
        center: {
          latitude: location.lat,
          longitude: location.lng,
        },
        radius: Math.min(radius, 50000),
      },
    };
  }

  const response = await fetch(`${PLACES_API_BASE}/places:searchText`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': GOOGLE_PLACES_API_KEY!,
      'X-Goog-FieldMask': 'places.name,places.displayName,places.formattedAddress,places.id,places.location,places.types,places.rating,places.userRatingCount,places.businessStatus',
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Places API error (${response.status}): ${errorText}`);
  }

  const data: any = await response.json();
  
  const results = (data.places || []).slice(0, 10).map((place: any) => {
    const resourceName = place.name || `places/${place.id}`;
    
    return {
      name: place.displayName?.text || 'Unknown',
      address: place.formattedAddress || 'No address',
      place_id: place.id,
      resource_name: resourceName,
      location: {
        lat: place.location?.latitude,
        lng: place.location?.longitude,
      },
      types: place.types || [],
      rating: place.rating,
      user_ratings_total: place.userRatingCount,
      business_status: place.businessStatus,
    };
  });

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          success: true,
          query: query,
          count: results.length,
          results: results,
        }, null, 2),
      },
    ],
  };
}

async function handleGetPlaceDetails(args: any) {
  const { place_id } = args;
  console.error(`[DEBUG] Getting details for place_id: ${place_id}`);

  const placeId = place_id.startsWith('places/') ? place_id.substring(7) : place_id;
  const fullUrl = `${PLACES_API_BASE}/places/${placeId}`;
  
  const response = await fetch(fullUrl, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-Goog-Api-Key': GOOGLE_PLACES_API_KEY!,
      'X-Goog-FieldMask': 'id,displayName,formattedAddress',
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Places API error (${response.status}): ${errorText}`);
  }

  const place: any = await response.json();

  const details = {
    name: place.displayName?.text || 'Unknown',
    address: place.formattedAddress || 'No address',
    place_id: place.id,
    location: {
      lat: place.location?.latitude,
      lng: place.location?.longitude,
    },
  };

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          success: true,
          details: details,
        }, null, 2),
      },
    ],
  };
}

async function handleGetWeather(args: any) {
  const { location, units = 'metric' } = args;
  const { lat, lng } = location;
  console.error(`[DEBUG] Getting weather for location: ${lat}, ${lng}`);

  const unitsSystem = units === 'imperial' ? 'IMPERIAL' : 'METRIC';
  const weatherUrl = `https://weather.googleapis.com/v1/currentConditions:lookup?key=${GOOGLE_PLACES_API_KEY}&location.latitude=${lat}&location.longitude=${lng}&unitsSystem=${unitsSystem}`;
  
  const weatherResponse = await fetch(weatherUrl);

  if (!weatherResponse.ok) {
    const errorText = await weatherResponse.text();
    throw new Error(`Google Weather API error (${weatherResponse.status}): ${errorText}`);
  }

  const weatherData: any = await weatherResponse.json();

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          success: true,
          data: weatherData,
        }, null, 2),
      },
    ],
  };
}

async function handleGetElevation(args: any) {
  const { locations } = args;
  console.error(`[DEBUG] Getting elevation for ${locations.length} location(s)`);

  const locationsParam = locations.map((loc: any) => `${loc.lat},${loc.lng}`).join('|');
  const elevationUrl = `https://maps.googleapis.com/maps/api/elevation/json?locations=${encodeURIComponent(locationsParam)}&key=${GOOGLE_PLACES_API_KEY}`;
  
  const response = await fetch(elevationUrl);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Elevation API error (${response.status}): ${errorText}`);
  }

  const data: any = await response.json();

  if (data.status !== 'OK') {
    throw new Error(`Elevation API error: ${data.status}`);
  }

  const results = data.results.map((result: any) => ({
    elevation: result.elevation,
    location: {
      lat: result.location.lat,
      lng: result.location.lng,
    },
  }));

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          success: true,
          count: results.length,
          results: results,
        }, null, 2),
      },
    ],
  };
}

// Tool definitions
const TOOLS = [
  {
    name: 'search_places',
    description: 'Search for places using text query to get suggestions with Google Place IDs.',
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query (e.g., "Starbucks near Seattle")',
        },
        location: {
          type: 'object',
          description: 'Optional location bias {lat: number, lng: number}',
          properties: {
            lat: { type: 'number' },
            lng: { type: 'number' },
          },
        },
        radius: {
          type: 'number',
          description: 'Search radius in meters (default: 5000, max: 50000)',
        },
      },
      required: ['query'],
    },
  },
  {
    name: 'get_place_details',
    description: 'Get detailed information about a specific place using its Google Place ID.',
    inputSchema: {
      type: 'object',
      properties: {
        place_id: {
          type: 'string',
          description: 'Google Place ID from search results',
        },
      },
      required: ['place_id'],
    },
  },
  {
    name: 'get_weather',
    description: 'Get current weather conditions for a location.',
    inputSchema: {
      type: 'object',
      properties: {
        location: {
          type: 'object',
          description: 'Location coordinates {lat: number, lng: number}',
          properties: {
            lat: { type: 'number' },
            lng: { type: 'number' },
          },
          required: ['lat', 'lng'],
        },
        units: {
          type: 'string',
          description: 'Temperature units: "metric", "imperial", or "standard". Default: metric',
          enum: ['metric', 'imperial', 'standard'],
        },
      },
      required: ['location'],
    },
  },
  {
    name: 'get_elevation',
    description: 'Get elevation data for one or more locations.',
    inputSchema: {
      type: 'object',
      properties: {
        locations: {
          type: 'array',
          description: 'Array of location coordinates [{lat: number, lng: number}]',
          items: {
            type: 'object',
            properties: {
              lat: { type: 'number' },
              lng: { type: 'number' },
            },
            required: ['lat', 'lng'],
          },
        },
      },
      required: ['locations'],
    },
  },
];

/**
 * Handle a single MCP JSON-RPC request.
 */
async function handleMcpRequest(requestData: any): Promise<any> {
  const method = requestData.method;
  const params = requestData.params || {};
  const requestId = requestData.id;

  try {
    if (method === 'initialize') {
      const result = {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {},
        },
        serverInfo: {
          name: 'googleplaces-mcp-server',
          version: '1.0.0',
        },
      };
      return createSuccessResponse(requestId, result);
    } else if (method === 'ping') {
      return null;
    } else if (method === 'tools/list') {
      return createSuccessResponse(requestId, { tools: TOOLS });
    } else if (method === 'tools/call') {
      const toolName = params.name;
      const toolArgs = params.arguments || {};

      // Log tool call for monitoring
      console.log(`[TOOL_CALL] ${toolName}`);

      if (!toolName) {
        return createErrorResponse(requestId, JsonRpcError.INVALID_PARAMS, 'Missing tool name');
      }

      let result;
      if (toolName === 'search_places') {
        result = await handleSearchPlaces(toolArgs);
      } else if (toolName === 'get_place_details') {
        result = await handleGetPlaceDetails(toolArgs);
      } else if (toolName === 'get_weather') {
        result = await handleGetWeather(toolArgs);
      } else if (toolName === 'get_elevation') {
        result = await handleGetElevation(toolArgs);
      } else {
        return createErrorResponse(requestId, JsonRpcError.METHOD_NOT_FOUND, `Unknown tool: ${toolName}`);
      }

      return createSuccessResponse(requestId, result);
    } else if (method === 'notifications/initialized') {
      return null;
    } else {
      return createErrorResponse(requestId, JsonRpcError.METHOD_NOT_FOUND, `Unknown method: ${method}`);
    }
  } catch (error) {
    console.error(`[DEBUG] Error handling method ${method}:`, error);
    const message = error instanceof Error ? error.message : String(error);
    return createErrorResponse(requestId, JsonRpcError.INTERNAL_ERROR, message);
  }
}

/**
 * Create and run the HTTP transport server.
 */
export function createHttpServer(port: number = 3000): Express {
  const app = express();
  app.use(express.json());

  // POST /mcp - Main MCP endpoint
  app.post('/mcp', async (req: Request, res: Response) => {
    const mcpProtocolVersion = req.get('MCP-Protocol-Version');

    // Validate protocol version if provided
    if (mcpProtocolVersion && !validateMcpProtocolVersion(mcpProtocolVersion)) {
      return res.status(400).json(
        createErrorResponse(
          null,
          JsonRpcError.INVALID_REQUEST,
          `Unsupported MCP protocol version: ${mcpProtocolVersion}`
        )
      );
    }

    const body = req.body;

    // Validate JSON-RPC structure
    if (!isValidJsonRpc(body)) {
      return res.status(400).json(
        createErrorResponse(body?.id, JsonRpcError.INVALID_REQUEST, 'Invalid JSON-RPC request')
      );
    }

    // Check if notification
    if (isNotification(body)) {
      handleMcpRequest(body).catch((error) => {
        console.error('[DEBUG] Error handling notification:', error);
      });
      return res.status(202).send();
    }

    // Handle request
    const response = await handleMcpRequest(body);

    if (!response) {
      return res.status(202).send();
    }

    res.json(response);
  });

  // GET /mcp - Optional SSE stream
  app.get('/mcp', (req: Request, res: Response) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // Keep alive with periodic comments
    const interval = setInterval(() => {
      res.write(': keepalive\n\n');
    }, 30000);

    req.on('close', () => {
      clearInterval(interval);
      res.end();
    });
  });

  // Health check endpoint
  app.get('/healthz', (req: Request, res: Response) => {
    res.json({
      status: 'healthy',
      app: 'initialized',
    });
  });

  return app;
}

/**
 * Run the HTTP server.
 */
export function runHttpServer(port: number = 3000): void {
  const app = createHttpServer(port);

  app.listen(port, () => {
    console.log(`Google Places MCP Server (HTTP) listening on http://localhost:${port}/mcp`);
    console.error(`[DEBUG] Server initialized on port ${port}`);
  });

  process.on('SIGINT', () => {
    console.error('[DEBUG] Shutting down...');
    process.exit(0);
  });
}
