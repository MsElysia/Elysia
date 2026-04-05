# Proposal Management API Documentation

REST API endpoints for managing proposals via Architect-Core and WebScout.

## Base URL

```
http://localhost:5000
```

## Endpoints

### Health Check

**GET** `/health`

Check API health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "proposal-api"
}
```

---

### List Proposals

**GET** `/api/proposals`

List all proposals, optionally filtered by status.

**Query Parameters:**
- `status` (optional): Filter by status (`research`, `design`, `proposal`, `approved`, `rejected`, `implemented`)

**Response:**
```json
{
  "status": "success",
  "count": 2,
  "proposals": [
    {
      "proposal_id": "webscout-20250129-123456-multi-agent-orchestration",
      "title": "Research: Multi Agent Orchestration",
      "status": "proposal",
      "created_at": "2025-01-29T12:34:56",
      ...
    }
  ]
}
```

---

### Get Proposal

**GET** `/api/proposals/<proposal_id>`

Get details of a specific proposal.

**Response:**
```json
{
  "status": "success",
  "proposal": {
    "proposal_id": "webscout-20250129-123456-multi-agent-orchestration",
    "title": "Research: Multi Agent Orchestration",
    "description": "Survey LangGraph, AutoGen, CrewAI...",
    "status": "proposal",
    "created_by": "elysia-webscout",
    "created_at": "2025-01-29T12:34:56",
    "research_sources": [...],
    "design_impact": {...},
    ...
  }
}
```

---

### Create Proposal

**POST** `/api/proposals`

Create a new research proposal.

**Request Body:**
```json
{
  "task_description": "Survey LangGraph, AutoGen, CrewAI for multi-agent orchestration patterns",
  "topic": "multi-agent-orchestration"
}
```

**Response:**
```json
{
  "status": "success",
  "proposal_id": "webscout-20250129-123456-multi-agent-orchestration",
  "message": "Research proposal created: webscout-20250129-123456-multi-agent-orchestration"
}
```

---

### Add Research

**POST** `/api/proposals/<proposal_id>/research`

Add research findings to a proposal.

**Request Body:**
```json
{
  "sources": [
    {
      "url": "https://langchain-ai.github.io/langgraph/",
      "title": "LangGraph Documentation",
      "relevance": "high",
      "extracted_patterns": [
        "Task graphs for agent orchestration",
        "State management across agents"
      ],
      "summary": "LangGraph provides task graph orchestration..."
    }
  ],
  "summary": "Research summary text..."
}
```

**Response:**
```json
{
  "status": "success",
  "proposal_id": "webscout-20250129-123456-multi-agent-orchestration"
}
```

---

### Add Design

**POST** `/api/proposals/<proposal_id>/design`

Add design documents to a proposal.

**Request Body:**
```json
{
  "architecture": "# Architecture Design\n\n...",
  "integration": "# Integration Points\n\n...",
  "api_spec": "# API Specification\n\n..."  // optional
}
```

**Response:**
```json
{
  "status": "success",
  "proposal_id": "webscout-20250129-123456-multi-agent-orchestration"
}
```

---

### Add Implementation

**POST** `/api/proposals/<proposal_id>/implementation`

Add implementation plan to a proposal.

**Request Body:**
```json
{
  "todos": [
    {
      "task": "Create TaskGraphOrchestrator class",
      "priority": "high",
      "notes": "Core orchestration logic"
    },
    {
      "task": "Write tests",
      "priority": "medium",
      "notes": "Unit and integration tests"
    }
  ],
  "patches": ["patch content 1", "patch content 2"],  // optional
  "tests": "# Test Requirements\n\n..."  // optional
}
```

**Response:**
```json
{
  "status": "success",
  "proposal_id": "webscout-20250129-123456-multi-agent-orchestration"
}
```

---

### Approve Proposal

**POST** `/api/proposals/<proposal_id>/approve`

Approve a proposal for implementation.

**Request Body:**
```json
{
  "approver": "user@example.com"  // optional, defaults to "system"
}
```

**Response:**
```json
{
  "status": "success",
  "proposal_id": "webscout-20250129-123456-multi-agent-orchestration",
  "approved_by": "user@example.com"
}
```

---

### Reject Proposal

**POST** `/api/proposals/<proposal_id>/reject`

Reject a proposal.

**Request Body:**
```json
{
  "reason": "Does not align with current architecture priorities"
}
```

**Response:**
```json
{
  "status": "success",
  "proposal_id": "webscout-20250129-123456-multi-agent-orchestration",
  "rejection_reason": "Does not align with current architecture priorities"
}
```

---

### WebScout Status

**GET** `/api/webscout/status`

Get WebScout agent status.

**Response:**
```json
{
  "status": "active",
  "agent_name": "Elysia-WebScout",
  "role": "External Intelligence Officer",
  "proposals_count": 5,
  "proposals": [...]
}
```

---

### Architect Status

**GET** `/api/architect/status`

Get comprehensive Architect-Core status report.

**Response:**
```json
{
  "ModuleArchitect": {...},
  "MutationArchitect": {...},
  "PolicyArchitect": {...},
  "PersonaArchitect": {...},
  "ProposalSystem": {...},
  "WebScout": {...}
}
```

---

## Example Usage

### Using curl

```bash
# Create a proposal
curl -X POST http://localhost:5000/api/proposals \
  -H "Content-Type: application/json" \
  -d '{
    "task_description": "Survey multi-agent frameworks",
    "topic": "multi-agent-orchestration"
  }'

# List proposals
curl http://localhost:5000/api/proposals

# Get specific proposal
curl http://localhost:5000/api/proposals/webscout-20250129-123456-multi-agent-orchestration

# Approve proposal
curl -X POST http://localhost:5000/api/proposals/webscout-20250129-123456-multi-agent-orchestration/approve \
  -H "Content-Type: application/json" \
  -d '{"approver": "admin"}'
```

### Using Python requests

```python
import requests

BASE_URL = "http://localhost:5000"

# Create proposal
response = requests.post(f"{BASE_URL}/api/proposals", json={
    "task_description": "Survey multi-agent frameworks",
    "topic": "multi-agent-orchestration"
})
proposal_id = response.json()["proposal_id"]

# Add research
requests.post(f"{BASE_URL}/api/proposals/{proposal_id}/research", json={
    "sources": [...],
    "summary": "..."
})

# Approve
requests.post(f"{BASE_URL}/api/proposals/{proposal_id}/approve", json={
    "approver": "admin"
})
```

---

## Error Responses

All endpoints return error responses in the following format:

```json
{
  "status": "error",
  "message": "Error description"
}
```

Common HTTP status codes:
- `400`: Bad Request (missing or invalid parameters)
- `404`: Not Found (proposal doesn't exist)
- `500`: Internal Server Error

