#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ErrorCode,
  McpError,
} from '@modelcontextprotocol/sdk/types.js';
import express, { Request, Response } from 'express';
import { createServer as createHttpServer } from 'http';
import { WebSocketServer, WebSocket } from 'ws';

// Handle --version flag
if (process.argv.includes('--version')) {
  console.log('googleplaces-mcp-server version 1.0.0');
  process.exit(0);
}

// Get API key from environment
const GOOGLE_PLACES_API_KEY = process.env.GOOGLE_PLACES_API_KEY;

if (!GOOGLE_PLACES_API_KEY) {
  console.error('[ERROR] GOOGLE_PLACES_API_KEY environment variable is required');
  process.exit(1);
}

// New Places API base URL
const PLACES_API_BASE = 'https://places.googleapis.com/v1';

// Create the MCP server
const server = new Server(
  {
    name: 'googleplaces-mcp-server',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  console.error('[DEBUG] ListTools request received');
  
  return {
    tools: [
      {
        name: 'search_places',
        description: 'Search for places using text query to get suggestions with Google Place IDs. Returns place name, address, place_id, and location coordinates. Use this to help users find and select places to link to journal entries.',
        inputSchema: {
          type: 'object',
          properties: {
            query: {
              type: 'string',
              description: 'Search query (e.g., "Starbucks near Seattle", "restaurants in downtown")',
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
        description: 'Get detailed information about a specific place using its Google Place ID. Returns comprehensive details including name, address, coordinates, phone, website, rating, and opening hours.',
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
        description: 'Get current weather conditions and forecast for a location. Uses OpenWeatherMap API to provide temperature, conditions, humidity, wind speed, and forecast data.',
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
              description: 'Temperature units: "metric" (Celsius), "imperial" (Fahrenheit), or "standard" (Kelvin). Default: metric',
              enum: ['metric', 'imperial', 'standard'],
            },
          },
          required: ['location'],
        },
      },
      {
        name: 'get_elevation',
        description: 'Get elevation data for one or more locations using Google Elevation API. Returns elevation in meters above sea level.',
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
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    if (name === 'search_places') {
      return await handleSearchPlaces(args);
    } else if (name === 'get_place_details') {
      return await handleGetPlaceDetails(args);
    } else if (name === 'get_weather') {
      return await handleGetWeather(args);
    } else if (name === 'get_elevation') {
      return await handleGetElevation(args);
    } else {
      throw new McpError(
        ErrorCode.MethodNotFound,
        `Unknown tool: ${name}`
      );
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    
    if (errorMessage.includes('API_KEY')) {
      throw new McpError(
        ErrorCode.InvalidRequest,
        `Google Places API error: ${errorMessage}. Please check your API key.`
      );
    }
    
    throw new McpError(
      ErrorCode.InternalError,
      `Tool execution failed: ${errorMessage}`
    );
  }
});

async function handleSearchPlaces(args: any) {
  const { query, location, radius = 5000 } = args;

  console.error(`[DEBUG] Searching places for: "${query}"`);
  
  // Build request body for New Places API
  const requestBody: any = {
    textQuery: query,
  };

  // Add location bias if provided
  if (location?.lat && location?.lng) {
    requestBody.locationBias = {
      circle: {
        center: {
          latitude: location.lat,
          longitude: location.lng,
        },
        radius: Math.min(radius, 50000), // Max 50km
      },
    };
  }

  // Call New Places API (Text Search)
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
  
  // Log first result to debug
  if (data.places && data.places.length > 0) {
    console.error('[DEBUG] Sample place object keys:', Object.keys(data.places[0]));
    console.error('[DEBUG] Sample place.name:', data.places[0].name);
    console.error('[DEBUG] Sample place.id:', data.places[0].id);
  }
  
  const results = (data.places || []).slice(0, 10).map((place: any) => {
    // Use the name field (resource name) if available, otherwise construct from id
    const resourceName = place.name || `places/${place.id}`;
    
    return {
      name: place.displayName?.text || 'Unknown',
      address: place.formattedAddress || 'No address',
      place_id: place.id,
      resource_name: resourceName,  // Full resource name like "places/ChIJ..."
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
          message: `Found ${results.length} places for "${query}". Each result includes a place_id that can be stored in your journal database.`,
        }, null, 2),
      },
    ],
  };
}

async function handleGetPlaceDetails(args: any) {
  const { place_id } = args;

  console.error(`[DEBUG] Getting details for place_id: ${place_id}`);

  // The place_id could be:
  // 1. Just the ID: "ChIJ..."
  // 2. Full resource name: "places/ChIJ..."
  // For the API call, we need just the ID in the URL path
  const placeId = place_id.startsWith('places/') ? place_id.substring(7) : place_id;
  
  const fullUrl = `${PLACES_API_BASE}/places/${placeId}`;
  
  console.error(`[DEBUG] Place Details Request:`, {
    placeId,
    fullUrl,
    apiKeyPresent: !!GOOGLE_PLACES_API_KEY,
    apiKeyLength: GOOGLE_PLACES_API_KEY?.length,
  });
  
  // Call New Places API (Place Details) - exact same format as the working browser test
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
    const errorDetails = {
      status: response.status,
      url: fullUrl,
      headers: Object.fromEntries(response.headers.entries()),
      error: errorText
    };
    console.error(`[DEBUG] Place Details API error:`, errorDetails);
    throw new Error(`Places API error (${response.status}) at ${fullUrl}: ${errorText.substring(0, 200)}`);
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
    phone: place.internationalPhoneNumber,
    website: place.websiteUri,
    rating: place.rating,
    user_ratings_total: place.userRatingCount,
    price_level: place.priceLevel,
    types: place.types || [],
    opening_hours: place.regularOpeningHours
      ? {
          open_now: place.regularOpeningHours.openNow,
          weekday_text: place.regularOpeningHours.weekdayDescriptions,
        }
      : null,
  };

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          success: true,
          place_id: place_id,
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

  // Use Google Weather API (part of Google Maps Platform)
  const unitsSystem = units === 'imperial' ? 'IMPERIAL' : 'METRIC';
  
  // Call Google Weather API - Current Conditions
  const weatherUrl = `https://weather.googleapis.com/v1/currentConditions:lookup?key=${GOOGLE_PLACES_API_KEY}&location.latitude=${lat}&location.longitude=${lng}&unitsSystem=${unitsSystem}`;
  
  const weatherResponse = await fetch(weatherUrl);

  if (!weatherResponse.ok) {
    const errorText = await weatherResponse.text();
    throw new Error(`Google Weather API error (${weatherResponse.status}): ${errorText}`);
  }

  const weatherData: any = await weatherResponse.json();

  const unitSymbol = unitsSystem === 'IMPERIAL' ? '°F' : '°C';
  const speedUnit = unitsSystem === 'IMPERIAL' ? 'mph' : 'km/h';
  const distanceUnit = unitsSystem === 'IMPERIAL' ? 'miles' : 'km';

  const result = {
    current: {
      time: weatherData.currentTime,
      timezone: weatherData.timeZone?.id,
      is_daytime: weatherData.isDaytime,
      weather: weatherData.weatherCondition?.type,
      description: weatherData.weatherCondition?.description?.text,
      icon_url: weatherData.weatherCondition?.iconBaseUri,
      temperature: weatherData.temperature?.degrees,
      feels_like: weatherData.feelsLikeTemperature?.degrees,
      dew_point: weatherData.dewPoint?.degrees,
      heat_index: weatherData.heatIndex?.degrees,
      wind_chill: weatherData.windChill?.degrees,
      humidity: weatherData.relativeHumidity,
      uv_index: weatherData.uvIndex,
      precipitation: {
        probability: weatherData.precipitation?.probability?.percent,
        type: weatherData.precipitation?.probability?.type,
        amount: weatherData.precipitation?.qpf?.quantity,
      },
      thunderstorm_probability: weatherData.thunderstormProbability,
      air_pressure: weatherData.airPressure?.meanSeaLevelMillibars,
      wind: {
        direction_degrees: weatherData.wind?.direction?.degrees,
        direction_cardinal: weatherData.wind?.direction?.cardinal,
        speed: weatherData.wind?.speed?.value,
        gust: weatherData.wind?.gust?.value,
      },
      visibility: weatherData.visibility?.distance,
      cloud_cover: weatherData.cloudCover,
      history_24h: {
        temperature_change: weatherData.currentConditionsHistory?.temperatureChange?.degrees,
        max_temperature: weatherData.currentConditionsHistory?.maxTemperature?.degrees,
        min_temperature: weatherData.currentConditionsHistory?.minTemperature?.degrees,
        precipitation: weatherData.currentConditionsHistory?.qpf?.quantity,
      },
      units: { 
        temperature: unitSymbol, 
        speed: speedUnit,
        distance: distanceUnit,
        pressure: 'mb',
      },
    },
  };

  return {
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          success: true,
          location: { lat, lng },
          data: result,
        }, null, 2),
      },
    ],
  };
}

async function handleGetElevation(args: any) {
  const { locations } = args;

  console.error(`[DEBUG] Getting elevation for ${locations.length} location(s)`);

  // Build locations parameter for Elevation API
  const locationsParam = locations.map((loc: any) => `${loc.lat},${loc.lng}`).join('|');

  // Call Google Elevation API
  const elevationUrl = `https://maps.googleapis.com/maps/api/elevation/json?locations=${encodeURIComponent(locationsParam)}&key=${GOOGLE_PLACES_API_KEY}`;
  const response = await fetch(elevationUrl);

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Elevation API error (${response.status}): ${errorText}`);
  }

  const data: any = await response.json();

  if (data.status !== 'OK') {
    throw new Error(`Elevation API error: ${data.status} - ${data.error_message || 'Unknown error'}`);
  }

  const results = data.results.map((result: any) => ({
    elevation: result.elevation,
    resolution: result.resolution,
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

// Start the server
async function main() {
  // Handle --version flag
  if (process.argv.includes('--version') || process.argv.includes('-v')) {
    console.log('googleplaces-mcp-server version 1.0.0');
    process.exit(0);
  }

  const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3000;
  const app = express();

  // Middleware
  app.use(express.json());
  
  // CORS headers for WebSocket
  app.use((req: Request, res: Response, next: any) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') {
      res.sendStatus(200);
    } else {
      next();
    }
  });

  // Health check endpoint
  app.get('/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', version: '1.0.0' });
  });

  // Legacy REST endpoints for backwards compatibility
  // MCP initialize endpoint
  app.post('/mcp/initialize', async (_req: Request, res: Response) => {
    try {
      console.error('[DEBUG] Initialize request received');
      res.json({
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {},
        },
        serverInfo: {
          name: 'googleplaces-mcp-server',
          version: '1.0.0',
        },
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      res.status(500).json({ error: errorMessage });
    }
  });

  // MCP list tools endpoint
  app.post('/mcp/tools/list', async (_req: Request, res: Response) => {
    try {
      console.error('[DEBUG] ListTools request received');

      const response = await (
        server.request(
          { method: 'tools/list' },
          ListToolsRequestSchema
        ) as any
      ).catch(() => ({
        tools: [
          {
            name: 'search_places',
            description: 'Search for places using text query to get suggestions with Google Place IDs. Returns place name, address, place_id, and location coordinates. Use this to help users find and select places to link to journal entries.',
            inputSchema: {
              type: 'object',
              properties: {
                query: {
                  type: 'string',
                  description: 'Search query (e.g., "Starbucks near Seattle", "restaurants in downtown")',
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
            description: 'Get detailed information about a specific place using its Google Place ID. Returns comprehensive details including name, address, coordinates, phone, website, rating, and opening hours.',
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
            description: 'Get current weather conditions and forecast for a location. Uses OpenWeatherMap API to provide temperature, conditions, humidity, wind speed, and forecast data.',
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
                  description: 'Temperature units: "metric" (Celsius), "imperial" (Fahrenheit), or "standard" (Kelvin). Default: metric',
                  enum: ['metric', 'imperial', 'standard'],
                },
              },
              required: ['location'],
            },
          },
          {
            name: 'get_elevation',
            description: 'Get elevation data for one or more locations using Google Elevation API. Returns elevation in meters above sea level.',
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
        ],
      }));

      res.json(response);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      res.status(500).json({ error: errorMessage });
    }
  });

  // MCP call tool endpoint
  app.post('/mcp/tools/call', async (req: Request, res: Response) => {
    try {
      const { name, arguments: args } = req.body;

      console.error(`[DEBUG] Tool call received: ${name}`);

      if (!name || !args) {
        res.status(400).json({ error: 'Missing tool name or arguments' });
        return;
      }

      if (name === 'search_places') {
        const result = await handleSearchPlaces(args);
        res.json(result);
      } else if (name === 'get_place_details') {
        const result = await handleGetPlaceDetails(args);
        res.json(result);
      } else if (name === 'get_weather') {
        const result = await handleGetWeather(args);
        res.json(result);
      } else if (name === 'get_elevation') {
        const result = await handleGetElevation(args);
        res.json(result);
      } else {
        res.status(404).json({
          error: `Unknown tool: ${name}`,
          code: ErrorCode.MethodNotFound,
        });
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);

      if (errorMessage.includes('API_KEY')) {
        res.status(400).json({
          error: `Google Places API error: ${errorMessage}. Please check your API key.`,
          code: ErrorCode.InvalidRequest,
        });
      } else {
        res.status(500).json({
          error: `Tool execution failed: ${errorMessage}`,
          code: ErrorCode.InternalError,
        });
      }
    }
  });

  const httpServer = createHttpServer(app);
  
  // Create WebSocket server
  const wss = new WebSocketServer({ server: httpServer });

  // Handle WebSocket connections
  wss.on('connection', (ws: WebSocket) => {
    console.error('[DEBUG] WebSocket client connected');

    // Handle incoming messages from client
    ws.on('message', async (data: any) => {
      try {
        const message = JSON.parse(data.toString());
        console.error('[DEBUG] Received JSON-RPC message:', message);

        // Handle JSON-RPC requests
        if (message.method) {
          let result: any;

          if (message.method === 'initialize') {
            result = {
              protocolVersion: '2024-11-05',
              capabilities: {
                tools: {},
              },
              serverInfo: {
                name: 'googleplaces-mcp-server',
                version: '1.0.0',
              },
            };
          } else if (message.method === 'tools/list') {
            result = await (
              server.request(
                { method: 'tools/list' },
                ListToolsRequestSchema
              ) as any
            ).catch(() => ({
              tools: [
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
              ],
            }));
          } else if (message.method === 'tools/call') {
            const { name, arguments: args } = message.params;

            if (name === 'search_places') {
              result = await handleSearchPlaces(args);
            } else if (name === 'get_place_details') {
              result = await handleGetPlaceDetails(args);
            } else if (name === 'get_weather') {
              result = await handleGetWeather(args);
            } else if (name === 'get_elevation') {
              result = await handleGetElevation(args);
            } else {
              throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`);
            }
          } else {
            throw new McpError(ErrorCode.MethodNotFound, `Unknown method: ${message.method}`);
          }

          // Send response back
          const response = {
            jsonrpc: '2.0',
            id: message.id,
            result: result,
          };
          ws.send(JSON.stringify(response));
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        const errorResponse = {
          jsonrpc: '2.0',
          id: (data as any).id || null,
          error: {
            code: -32603,
            message: 'Internal error',
            data: errorMessage,
          },
        };
        ws.send(JSON.stringify(errorResponse));
      }
    });

    ws.on('close', () => {
      console.error('[DEBUG] WebSocket client disconnected');
    });

    ws.on('error', (error: any) => {
      console.error('[DEBUG] WebSocket error:', error);
    });
  });

  httpServer.listen(PORT, () => {
    console.log(`Google Places MCP server running on http://localhost:${PORT}`);
    console.error(`[DEBUG] Server initialized on port ${PORT}`);
  });

  // Graceful shutdown
  process.on('SIGINT', () => {
    console.error('[DEBUG] Shutting down server...');
    httpServer.close(() => {
      console.error('[DEBUG] Server closed');
      process.exit(0);
    });
  });
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});
