# Google Places MCP Server

WebSocket-based Model Context Protocol server for Google Places API integration. Provides location search, place details, weather data, and elevation information using JSON-RPC 2.0 communication protocol.

## Features

- **Search Places**: Find places using natural language queries with location bias
- **Get Place Details**: Retrieve comprehensive information using Google Place ID
- **Get Weather**: Current weather conditions using Google Weather API (part of Google Maps Platform)
- **Get Elevation**: Elevation data for locations using Google Elevation API
- **Single API Key**: All features use the same Google API key

## Quick Start

See [SETUP.md](SETUP.md) for detailed installation and configuration instructions.

```bash
# 1. Get your API key from Google Cloud Console
# 2. Set environment variable
export GOOGLE_PLACES_API_KEY="your_api_key"

# 3. Start the server
googleplaces-mcp-server
```

The server runs on `http://localhost:3000` by default.

## Available Tools

### 1. search_places

Search for places and get Google Place IDs.

**Parameters:**
- `query` (required): Search query (e.g., "Starbucks near me", "Italian restaurants")
- `location` (optional): `{lat: number, lng: number}` - Location bias
- `radius` (optional): Search radius in meters (default: 5000, max: 50000)

**Returns:**
- List of places with `place_id`, name, address, coordinates, rating

**Example:**
```json
{
  "query": "coffee shops in Seattle",
  "location": {"lat": 47.6062, "lng": -122.3321},
  "radius": 2000
}
```

### 2. get_place_details

Get full details about a place using its Google Place ID.

**Parameters:**
- `place_id` (required): Google Place ID from search results

**Returns:**
- Complete place information including phone, website, hours, ratings

### 3. get_weather

Get current weather conditions using Google Weather API.

**Parameters:**
- `location` (required): `{lat: number, lng: number}` - Location coordinates
- `units` (optional): "metric" (Celsius/km), "imperial" (Fahrenheit/miles). Default: metric

**Returns:**
- Current weather: temperature, feels like, dew point, heat index, wind chill
- Humidity, UV index, precipitation (probability, type, amount)
- Thunderstorm probability, air pressure
- Wind: direction (degrees & cardinal), speed, gust
- Visibility, cloud cover
- 24-hour history: temperature changes, min/max temps, precipitation

**Example:**
```json
{
  "location": {"lat": 47.6062, "lng": -122.3321},
  "units": "imperial"
}
```

**Note:** Uses the same Google API key as Places and Elevation APIs.

### 4. get_elevation

Get elevation data for one or more locations.

**Parameters:**
- `locations` (required): Array of `{lat: number, lng: number}` coordinates

**Returns:**
- Elevation in meters above sea level for each location
- Resolution (accuracy) of elevation data

**Example:**
```json
{
  "locations": [
    {"lat": 47.6062, "lng": -122.3321},
    {"lat": 47.6205, "lng": -122.3493}
  ]
}
```

## Example Use Case

Link locations to your application data:

1. **Search**: User mentions a location (e.g., "Starbucks on 5th Ave")
2. **Get Suggestions**: Call `search_places` with the query
3. **User Selects**: Present results, user picks the correct location
4. **Store**: Save the `place_id` in your database
5. **Retrieve**: Use `get_place_details` anytime to fetch current information

The `place_id` provides a persistent reference to a real-world location that stays valid even if the place changes names or moves slightly.

## Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Run in development mode
npm run dev

# Test
npm test
```

## License

MIT
