#!/usr/bin/env node

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ErrorCode,
  McpError,
} from '@modelcontextprotocol/sdk/types.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
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

// Start the server
async function main() {
  const useHttp = process.argv.includes('--http');
  const useStdio = process.argv.includes('--stdio');

  // Parse port from command line args or environment
  let PORT = 3001;
  const portIndex = process.argv.indexOf('--port');
  if (portIndex !== -1 && portIndex + 1 < process.argv.length) {
    PORT = parseInt(process.argv[portIndex + 1]);
  } else if (process.env.PORT) {
    PORT = parseInt(process.env.PORT);
  }

  if (useHttp) {
    // Run in HTTP mode (Streamable HTTP per MCP spec)
    const { runHttpServer } = await import('./transport/http.js');
    console.error(`[DEBUG] Starting in HTTP mode (Streamable HTTP) on localhost:${PORT}/mcp...`);
    runHttpServer(PORT);
  } else {
    // Run in stdio mode (default)
    console.error('[DEBUG] Starting in Stdio mode...');
    const app = new Server({
      name: 'googleplaces-mcp-server',
      version: '1.0.0',
    });

    app.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: TOOLS,
    }));

    app.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;
      console.error(`[DEBUG] Calling tool: ${name}`);

      let result: any;

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

      return result;
    });

    const transport = new StdioServerTransport();
    await app.connect(transport);

    console.error('[DEBUG] Google Places MCP server connected on stdio');
  }
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});
