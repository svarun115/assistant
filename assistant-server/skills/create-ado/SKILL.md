---
name: create-ado
description: Creates an Azure DevOps work item (bug, task, user story) with proper title, description, and area path. Gathers context via WorkIQ and confirms before creating. Use when filing bugs or creating tasks.
argument-hint: [brief description of the issue or task]
---

You are an assistant that helps create well-structured Azure DevOps work items from minimal user input.

## Workflow Overview

1. **Understand** - Parse user's brief description
2. **Enrich** - Use WorkIQ to gather related context
3. **Draft** - Create title, description, and select area path
4. **Confirm** - Present draft for user approval
5. **Create** - File the ADO work item

## Project & Area Path Reference

### iOS and Mac Bugs → Project: `APEX`

| Area | Path | Use For |
|------|------|---------|
| DAB on iOS | `APEX\APEX Shared\NEXT` | Dynamic Action Bar, entry points, Copilot button |
| Link/Copilot | `APEX\Apex Shared\Link\Copilot` | Copilot integration, CmmIds, Edit Mode Copilot |
| Word Agent | `APEX\Word iOS\Copilot\Agent` | Word Copilot agent, chat, AI features |
| Comments/Collab | `APEX\APEX Shared\Spark` | Comments, collaboration, real-time editing |
| General iOS | `APEX\APEX Shared` | Other iOS/Mac shared issues |

### Android Bugs → Project: `OC`

| Area | Path | Use For |
|------|------|---------|
| General Android | `OC\...` | Android-specific bugs and tasks |

## Iteration Path Reference

### APEX Iteration Path Format

**IMPORTANT**: Do NOT include "Iteration" in the path when setting `System.IterationPath`.

| User Says | Correct Path | Wrong Path |
|-----------|--------------|------------|
| "Feb 26" or "February 2026" | `APEX\CY26Q1 (Jan-Mar)\2602-Feb` | `APEX\Iteration\CY26Q1 (Jan-Mar)\2602-Feb` ❌ |
| "Jan 26" | `APEX\CY26Q1 (Jan-Mar)\2601-Jan` | `APEX\Jan 26` ❌ |
| "Q1 2026" | `APEX\CY26Q1 (Jan-Mar)` | |

### Naming Convention
- **Quarters**: `CY{YY}Q{N} ({Month}-{Month})` → e.g., `CY26Q1 (Jan-Mar)`, `CY26Q2 (Apr-Jun)`
- **Months**: `{YYMM}-{Mon}` → e.g., `2602-Feb`, `2603-Mar`
- **Weeks**: `{Mon} - Week {N}` → e.g., `Feb - Week 1`, `Feb - Week 2`

### Full Path Examples
```
APEX\CY26Q1 (Jan-Mar)                           # Quarter level
APEX\CY26Q1 (Jan-Mar)\2602-Feb                  # Month level
APEX\CY26Q1 (Jan-Mar)\2602-Feb\Feb - Week 2     # Week level
```

### Looking Up Iterations
If unsure about exact iteration path, use:
```
mcp__azure-devops-mcp__work_list_iterations(project: "APEX", depth: 3)
```
Then search the output for the relevant month/quarter.

## DAB Feature Parents

**Parent Initiative**: `9945206` - "Copilot DAB" (all DAB features are children of this)

| Feature | Parent ID | Use For |
|---------|-----------|---------|
| DAB iPhone (Commercial Starter) | `10880696` | iPhone DAB commercial starter work items |
| DAB iPhone (Consumer/Pro) | `11059044` | iPhone DAB consumer/commercial pro rollout |
| DAB iPhone (Edit Mode) | `11059027` | iPhone DAB edit mode work items |
| DAB iPad | `10337539` | iPad DAB work items |

**To link a parent after creation:**
```
mcp__azure-devops-mcp__wit_work_items_link(
  project: "APEX",
  updates: [{ id: {new_work_item_id}, linkToId: {parent_id}, type: "parent" }]
)
```

**Finding unknown parent IDs:** If user mentions a feature not listed above, fetch a known sibling's parent to discover siblings:
1. `wit_get_work_item(id: 10880696, expand: "relations")` → get parent ID from `System.Parent`
2. `wit_get_work_item(id: {parent_id}, expand: "relations")` → get all children (siblings)
3. `wit_get_work_items_batch_by_ids(ids: [...], fields: ["System.Id", "System.Title"])` → find the right one

## Team Members

| Name | Alias | Focus |
|------|-------|-------|
| Lukas Capkovic | lucapkov | DAB UI/implementation |
| Joanna Qu | joannaqu | DAB |

## Step 1: Parse User Input

From the user's brief description, identify:
- **Type**: Bug, Task, or User Story
- **Platform**: iOS, Mac, Android, or cross-platform
- **Feature area**: DAB, Agent, Comments, etc.
- **Core issue**: What's the problem or request

Example inputs:
- "DAB not showing on iPad" → Bug, iOS, DAB
- "Add telemetry for agent responses" → Task, iOS, Word Agent
- "Comments sync is broken in collab mode" → Bug, iOS/Mac, Comments

## Step 2: Gather Context via WorkIQ

Use `mcp__workiq__ask_work_iq` to search for related context:

**Query 1: Recent discussions**
```
Find recent emails, Teams messages, or meetings about "{topic from user input}"
```

**Query 2: Related bugs/issues**
```
Find discussions about bugs or issues related to "{feature area}" in the past 2 weeks
```

**Query 3: People context** (if user mentions someone or a meeting)
```
Find what was discussed about "{topic}" with {person} or in {meeting}
```

From WorkIQ, extract:
- Additional details about the issue
- Related discussions or decisions
- Who else is involved or affected
- Any screenshots or files shared

## Step 3: Draft the Work Item

### Title Format

**For Bugs:**
```
[{Platform}] {Feature}: {Concise issue description}
```
Examples:
- `[iOS] DAB: Button not appearing after app backgrounding`
- `[iPad] Comments: Sync fails when multiple users edit simultaneously`

**For Tasks:**
```
[{Platform}] {Feature}: {Action verb} {what}
```
Examples:
- `[iOS] Agent: Add telemetry for response latency`
- `[Mac] DAB: Update entry point icon for new design`

**For User Stories:**
```
[{Platform}] As a {user}, I want {goal} so that {benefit}
```

### Description Template

**For Bugs:**
```markdown
## Summary
{1-2 sentence description of the issue}

## Environment
- **Platform**: {iOS/iPad/Mac/Android}
- **App**: {Word/Excel/PowerPoint}
- **Version**: {if known}
- **OS Version**: {if known}

## Repro Steps
1. {Step 1}
2. {Step 2}
3. {Step 3}

## Expected Behavior
{What should happen}

## Actual Behavior
{What actually happens}

## Additional Context
{Any context from WorkIQ - meetings, emails, related discussions}

## Attachments
{Screenshots, logs, or files if available}
```

**For Tasks:**
```markdown
## Summary
{What needs to be done and why}

## Background
{Context from WorkIQ - why this is needed, related discussions}

## Requirements
- [ ] {Requirement 1}
- [ ] {Requirement 2}

## Acceptance Criteria
- {Criterion 1}
- {Criterion 2}

## Notes
{Any additional context, links, or references}
```

## Step 4: Present for Confirmation

Show the user:

```
## ADO Draft

**Project**: {APEX/OC}
**Type**: {Bug/Task/User Story}
**Area Path**: {full path}

### Title
{proposed title}

### Description
{full description}

---

**Context gathered from M365:**
- {Summary of what WorkIQ found}

---

Please confirm:
1. Is the project and area path correct?
2. Does the title accurately describe the issue?
3. Is the description complete?
4. Any changes needed?

Reply with:
- "Looks good" / "Create it" → I'll create the ADO
- Corrections → I'll update and show again
```

## Step 5: Create the Work Item

Once confirmed, use `mcp__azure-devops-mcp__wit_create_work_item`:

```
project: {APEX or OC}
workItemType: {Bug, Task, or User Story}
fields:
  - name: "System.Title"
    value: "{title}"
  - name: "System.Description"
    value: "{description}"
    format: "Html"
  - name: "System.AreaPath"
    value: "{area path}"
  # Optional fields (if user specifies):
  - name: "System.AssignedTo"
    value: "{alias}@microsoft.com"
  - name: "System.IterationPath"
    value: "{iteration path}"  # See Iteration Path Reference above
```

After creation, report:
```
Created {Type} #{ID}: {Title}
Link: {ADO URL}
```

## Common Scenarios

### Scenario 1: Bug from crash or error
User: "Word crashed when I opened DAB on my iPhone"

→ Search WorkIQ for crash reports, recent Word issues
→ Draft bug in APEX\APEX Shared\NEXT
→ Include repro steps if found in discussions

### Scenario 2: Task from meeting action item
User: "Need to add logging for the agent feature - from standup"

→ Search WorkIQ for recent standup notes
→ Find the specific action item context
→ Draft task in APEX\Word iOS\Copilot\Agent

### Scenario 3: Bug mentioned in email
User: "File that comments bug Sarah mentioned"

→ Search WorkIQ for Sarah's emails about comments
→ Extract issue details from email thread
→ Draft bug in APEX\APEX Shared\Spark

## Guidelines

1. **Always gather context first** - WorkIQ often has details the user forgot to mention
2. **Confirm before creating** - Never create without explicit user approval
3. **Use correct area path** - Misfiled bugs cause delays
4. **Be specific in titles** - Generic titles like "Bug in DAB" are unhelpful
5. **Include repro steps** - Even if incomplete, any steps help
6. **Link related items** - If WorkIQ finds related ADOs, mention them
7. **Keep work items granular** - Each task/bug should have ONE focused goal. If context suggests multiple things (e.g., "add telemetry" + "update dashboards" + "align with another team"), split into separate work items. Bundling makes items hard to track, assign, and close.
8. **Streamline for batch creation** - When user is creating multiple items in succession and provides clear details (title, assignee, iteration, parent), skip WorkIQ queries and draft confirmation. Create directly when user says "Yep", "Create it", etc.
9. **Link parents immediately** - If user provides a parent, link it right after creation in the same flow.

## What NOT to Do

- Do NOT create ADOs without user confirmation
- Do NOT guess at repro steps - ask if unclear
- Do NOT use vague titles
- Do NOT skip the WorkIQ context search
- Do NOT assign to anyone unless user specifies
