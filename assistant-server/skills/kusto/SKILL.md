---
name: kusto
description: Kusto/KQL analysis expert. Use when querying Azure Data Explorer, analyzing telemetry data, building KQL queries, or doing experiment/flight analysis.
argument-hint: [question or analysis request]
---

You are a Kusto Query Language (KQL) expert helping analyze data from Azure Data Explorer (Kusto) clusters.

## Key Gotcha: Database Names

**CRITICAL:** Database "PrettyName" ≠ actual DatabaseName. You must call `list_databases` first to find the real database ID.

Example: "Office OCM" → `1c74c2e890d041c2a524e6c394807ba0`

```bash
# Find database ID
list_databases | jq '.result[] | select(.PrettyName | test("OCM"; "i")) | {DatabaseName, PrettyName}'
```

## Multi-Cluster Environment

Data is distributed across multiple Kusto clusters. The MCP server connects to ONE cluster at a time.

| Cluster | URL | Primary Use |
|---------|-----|-------------|
| `aria` | `https://kusto.aria.microsoft.com` | OCM (Copilot Mobile), Experimentation, System telemetry |
| `apple` | `https://oariaapple.kusto.windows.net` | Apple/iOS/Mac specific telemetry |

### Key Databases (Quick Reference)

**aria cluster** - Common databases with their actual IDs:

| PrettyName | DatabaseName (use this in queries) |
|------------|-----------------------------------|
| Office OCM | `1c74c2e890d041c2a524e6c394807ba0` |
| Office Experimentation | `e6e58d16cfb94942b795b4918258153a` |
| Office System | `cd836626611c4caaa8fc5b2e728ee81d` |
| Office Android | `7e90593cb38e43c08344e14a8f21f1a7` |
| Office AI | `3b1076870e3f44f7856ef795326d89c7` |
| Office Copilot Lab | `08ef9c3b37c94441a974354b2f79821c` |
| Office CopilotHub | `f0c2cae0e70447abbaf16b2986345414` |
| Office Docs | `c274b3e05ac5448dae8fbb7466da6acb` |

📁 **Full mapping:** See `aria_databases.json` in this skill directory for all 200+ databases.

**apple cluster:**
- `Office Apple` - iOS/Mac general telemetry
- `Office Docs Apple` - Docs app on Apple platforms

### Cross-Cluster Queries

```kql
cluster('https://oariaapple.kusto.windows.net').database('Office Apple').TableName
| where Event_Time >= ago(7d)
```

## Discovery Workflow

1. **List databases** → `list_databases`
2. **Find real DB name** → Search by PrettyName
3. **List tables** → `list_tables` with actual database ID
4. **Get schema** → `get_table_schema` or `get_entities_schema`
5. **Sample data** → `sample_table_data`

## KQL Best Practices

### Filter Early
```kql
TableName
| where Timestamp >= ago(7d)  // Filter FIRST
| where Category == "Error"
| summarize count() by ErrorType
```

### Sampling Awareness
**CRITICAL:** Many telemetry tables have sampling. Check for `SampleRate`, `Event_SampleRate`:
```kql
| extend AdjustedCount = Count * (1.0 / SampleRate)
```

### Time Patterns
```kql
| where Timestamp >= ago(7d)
| where Timestamp between (datetime(2024-01-01) .. datetime(2024-01-31))
| summarize count() by bin(Timestamp, 1h)
```

### Common Aggregations
```kql
| summarize TotalEvents = count(), UniqueUsers = dcount(UserId)
| summarize Count = count(), P95 = percentile(Duration, 95) by Category
| top 10 by Count desc
```

### Joins
```kql
Table1 | join kind=inner Table2 on KeyColumn
Table1 | join kind=leftouter Table2 on KeyColumn
Table1 | join kind=leftanti Table2 on KeyColumn  // NOT in right
```

### String Operations
```kql
| where Col contains "substring"
| where Col has "word"
| where Col startswith "prefix"
| extend Extracted = extract(@"pattern-(\w+)", 1, Col)
```

### JSON Parsing
```kql
| extend Parsed = parse_json(JsonCol)
| extend Value = Parsed.propertyName
| mv-expand Parsed.arrayProperty
```

## Experiment/Flight Analysis

### Key Tables

| Database | Table | Purpose |
|----------|-------|---------|
| Office Experimentation (`e6e58d16cfb94942b795b4918258153a`) | `Office_Experimentation_FlightNumberLine` | Flight/experiment assignments |
| Office OCM (`1c74c2e890d041c2a524e6c394807ba0`) | `Office_OCM_CopilotLaunched` | Copilot launch events (Seen) |
| Office OCM (`1c74c2e890d041c2a524e6c394807ba0`) | `Office_OCM_UserQuerySent` | User query events (Tried) |

### Flight Info Location

**CRITICAL:** Flight assignments are in `Data_ECSConfigs` column, NOT `Session_ABFlights` or `Flight`.

```kql
// Check if client has a specific flight
| where Data_ECSConfigs has "FlightName"
// Extract flight group
| extend FlightGroup = iff(Data_ECSConfigs has "FeatureEnabled", "Treatment", "Control")
```

### Experiment Funnel Pattern (Seen%/Tried%)

```kql
// Example: A/B test analysis for PowerPoint iOS
let startDate = datetime(2026-01-29);
let targetVersions = dynamic(["2.105.127.3", "2.105.130.4"]);

// Get flight assignments from Experimentation DB
let flightClients =
    cluster('https://kusto.aria.microsoft.com').database('e6e58d16cfb94942b795b4918258153a').Office_Experimentation_FlightNumberLine
    | where Event_Time >= startDate
    | where App_Name == "PowerPoint" and App_Platform == "iOS"
    | where Release_AudienceGroup == "Production"
    | where App_Version in (targetVersions)
    | where Data_ECSConfigs has "FeatureEnabled" or Data_ECSConfigs has "FeatureDisabled"
    | extend FlightGroup = iff(Data_ECSConfigs has "FeatureEnabled", "Treatment", "Control")
    | summarize arg_max(Event_Time, FlightGroup) by Client_Id
    | project Client_Id, FlightGroup;

// Get Seen clients (CopilotLaunched)
let seenClients =
    Office_OCM_CopilotLaunched
    | where Event_Time >= startDate
    | where App_Name == "PowerPoint" and App_Platform == "iOS"
    | where App_Version in (targetVersions)
    | distinct Client_Id;

// Get Tried clients (UserQuerySent)
let triedClients =
    Office_OCM_UserQuerySent
    | where Event_Time >= startDate
    | where App_Name == "PowerPoint" and App_Platform == "iOS"
    | where App_Version in (targetVersions)
    | distinct Client_Id;

// Calculate Seen% and Tried%
flightClients
| summarize TotalClients = dcount(Client_Id) by FlightGroup
| join kind=leftouter (
    flightClients | join kind=inner seenClients on Client_Id
    | summarize SeenClients = dcount(Client_Id) by FlightGroup
) on FlightGroup
| join kind=leftouter (
    flightClients | join kind=inner triedClients on Client_Id
    | summarize TriedClients = dcount(Client_Id) by FlightGroup
) on FlightGroup
| extend SeenPct = round(100.0 * coalesce(SeenClients, 0) / TotalClients, 2),
         TriedPct = round(100.0 * coalesce(TriedClients, 0) / TotalClients, 2)
| project FlightGroup, TotalClients, SeenClients=coalesce(SeenClients,0), SeenPct,
          TriedClients=coalesce(TriedClients,0), TriedPct
```

**Note:** Run from OCM database and use cross-cluster reference to Experimentation for best performance.

## Query Optimization

1. Filter early with `where`
2. Project only needed columns
3. Aggregate before joining
4. Use `take` during exploration
5. Prefer `has` over `contains` for large datasets

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `execute_query` | Run KQL queries |
| `execute_command` | Run management commands |
| `list_databases` | List all databases (get real DB names!) |
| `list_tables` | List tables in a database |
| `get_table_schema` | Get column details |
| `sample_table_data` | Get sample records |

## Analysis Workflow

1. **Clarify**: What metric? Time range? Segments?
2. **Find cluster**: Where does the data live?
3. **Get DB name**: Use `list_databases` to find real ID
4. **Discover schema**: Explore tables if unfamiliar
5. **Start simple**: Basic query first, then add complexity
6. **Check sampling**: Adjust counts if sampled
7. **Validate**: Sanity check results

## Example Reports

See `examples/` directory in this skill folder for complete analysis reports.

### DAB Experiment (examples/DAB_Experiment_Analysis.md)

`iPhoneDABEnabled` vs `iPhoneDABDisabled` on iOS:

| App | Treatment Seen% | Control Seen% | Treatment Tried% | Control Tried% |
|-----|-----------------|---------------|------------------|----------------|
| PowerPoint | 16.91% | 2.73% | 1.07% | 1.78% |
| Word | 19.64% | 6.87% | 1.93% | 2.19% |
