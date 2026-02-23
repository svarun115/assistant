# DAB Entry Point Experiment Analysis

**Date:** February 4, 2026
**Platform:** iOS
**Flights:** `iPhoneDABEnabled` (Treatment) / `iPhoneDABDisabled` (Control)

---

## Results

### PowerPoint iOS (Dec 15, 2025 - Feb 4, 2026)

| Flight Group | Total Clients | Seen | Seen% | Tried | Tried% |
|--------------|---------------|------|-------|-------|--------|
| Treatment | 1,010,812 | 170,975 | 16.91% | 10,841 | 1.07% |
| Control | 1,007,107 | 27,505 | 2.73% | 17,918 | 1.78% |

### Word iOS (Dec 15, 2025 - Feb 4, 2026)

| Flight Group | Total Clients | Seen | Seen% | Tried | Tried% |
|--------------|---------------|------|-------|-------|--------|
| Treatment | 7,543,191 | 1,481,394 | 19.64% | 145,423 | 1.93% |
| Control | 7,115,067 | 488,892 | 6.87% | 155,991 | 2.19% |

---

## Summary

| App | Treatment Seen% | Control Seen% | Treatment Tried% | Control Tried% |
|-----|-----------------|---------------|------------------|----------------|
| PowerPoint | 16.91% | 2.73% | 1.07% | 1.78% |
| Word | 19.64% | 6.87% | 1.93% | 2.19% |

DAB increases Copilot discovery (Seen%) significantly. Tried% is lower in Treatment - users who find Copilot organically are more likely to engage.

---

## Methodology

### Data Sources

| Database | Table | Purpose |
|----------|-------|---------|
| Office Experimentation | `Office_Experimentation_FlightNumberLine` | Flight assignments via `Data_ECSConfigs` |
| Office OCM | `Office_OCM_CopilotLaunched` | Seen events |
| Office OCM | `Office_OCM_UserQuerySent` | Tried events |

### Definitions

- **Seen%** = Unique clients with `CopilotLaunched` / Total clients in flight
- **Tried%** = Unique clients with `UserQuerySent` / Total clients in flight

### Filters

- `Release_AudienceGroup == "Production"`
- `App_Platform == "iOS"`
- Flight assignment = latest `Data_ECSConfigs` per `Client_Id`

---

## Query Reference

```kql
let startDate = datetime(2025-12-15);

let flightClients =
    cluster('https://kusto.aria.microsoft.com')
    .database('e6e58d16cfb94942b795b4918258153a')
    .Office_Experimentation_FlightNumberLine
    | where Event_Time >= startDate
    | where App_Name == "Word" and App_Platform == "iOS"
    | where Release_AudienceGroup == "Production"
    | where Data_ECSConfigs has "iPhoneDABEnabled"
         or Data_ECSConfigs has "iPhoneDABDisabled"
    | extend FlightGroup = iff(Data_ECSConfigs has "iPhoneDABEnabled",
                               "Treatment", "Control")
    | summarize arg_max(Event_Time, FlightGroup) by Client_Id
    | project Client_Id, FlightGroup;

let seenClients =
    Office_OCM_CopilotLaunched
    | where Event_Time >= startDate
    | where App_Name == "Word" and App_Platform == "iOS"
    | distinct Client_Id;

let triedClients =
    Office_OCM_UserQuerySent
    | where Event_Time >= startDate
    | where App_Name == "Word" and App_Platform == "iOS"
    | distinct Client_Id;

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
| project FlightGroup, TotalClients,
          SeenClients=coalesce(SeenClients,0), SeenPct,
          TriedClients=coalesce(TriedClients,0), TriedPct
```
