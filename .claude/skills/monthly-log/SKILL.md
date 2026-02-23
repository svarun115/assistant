# Monthly Health Log

Generate aggregated monthly health data for the Google Sheet fitness tracker.

## Data Sources

- **Garmin MCP Server**: Primary source for workout/activity data
- **Personal Journal MCP Server**: Context on activities, location, and cross-verification

## Required Metrics

### Running
| Metric | Description |
|--------|-------------|
| Indoor/Treadmill Kilometres | Total distance run on indoor/treadmill |
| Indoor/Treadmill Run Count | Total number of indoor/treadmill runs |
| Outdoor Kilometres | Total distance run outdoors |
| Outdoor Run Count | Total number of outdoor runs |

### Other Cardio
| Metric | Description |
|--------|-------------|
| Biking Kilometres | Total distance biked |
| Biking Days | Total days with biking sessions |
| Swimming Days | Total days with swimming sessions |

### General Activity
| Metric | Description |
|--------|-------------|
| Workout Days | Days with strength/conditioning or cardio (excluding runs, bikes, swims) |
| Sport Days | Days on which a sport was played |
| Rest Days | Days with no exercise and active calories < 250 |

### Lifestyle
| Metric | Description |
|--------|-------------|
| Alcohol Days | Days on which alcohol was consumed |

## Rules

- **Timezone**: Garmin returns times in UTC. Convert to IST (UTC+5:30).
- **Cross-verification**: Use Personal Journal entries for context and to verify data consistency.
- **Discrepancies**: Call out any inconsistencies between data sources.
- **No Estimation**: Always query the actual data rather than estimating. For Rest Days, fetch the daily summary for each day without a recorded activity and verify active calories < 250. Do not skip data retrieval as a shortcut.

## Activity Type Mapping

Garmin logs sports and gym workouts under the generic "Cardio" activity type. To determine the actual type:
1. Query the Personal Journal for events on the same date/time
2. The journal entry will specify the actual activity (badminton, tennis, gym workout, etc.)
3. Use this to correctly categorise into "Workout Days" vs "Sport Days"

- **Sport Days**: badminton, tennis, squash, basketball, etc.
- **Workout Days**: gym/strength training or generic cardio not categorised as a sport
