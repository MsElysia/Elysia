# REST API Server Documentation

**File**: `project_guardian/api_server.py`  
**Status**: ✅ IMPLEMENTED

---

## Overview

The REST API Server provides external access to the Elysia system via HTTP REST endpoints. This enables integration with external systems, monitoring tools, and custom applications.

---

## Endpoints

### Health & Status

#### `GET /api/health`
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-01T12:00:00",
  "api_version": "1.0"
}
```

---

#### `GET /api/system/status`
Get comprehensive system status.

**Response**:
```json
{
  "initialized": true,
  "running": true,
  "components": {...},
  "operational_stats": {...}
}
```

---

#### `GET /api/system/stats`
Get system statistics including API usage.

**Response**:
```json
{
  "uptime": "2025-11-01T10:00:00",
  "api_requests": {
    "total": 150,
    "successful": 145,
    "failed": 5
  },
  "system": {...}
}
```

---

### Mutations

#### `GET /api/mutations`
List all mutation proposals.

**Response**:
```json
{
  "mutations": [
    {
      "mutation_id": "...",
      "target_module": "...",
      "status": "approved",
      ...
    }
  ]
}
```

---

#### `GET /api/mutations/<mutation_id>`
Get specific mutation proposal.

**Response**:
```json
{
  "mutation_id": "...",
  "target_module": "...",
  "proposed_code": "...",
  "status": "approved",
  ...
}
```

---

### Trust Registry

#### `GET /api/trust/nodes`
List all nodes in trust registry.

**Response**:
```json
{
  "nodes": [
    {
      "node_id": "...",
      "general_trust": 0.85,
      "mutation_trust": 0.9,
      ...
    }
  ]
}
```

---

#### `GET /api/trust/nodes/<node_id>`
Get trust data for specific node.

**Response**:
```json
{
  "node_id": "...",
  "general_trust": 0.85,
  "mutation_trust": 0.9,
  "total_tasks": 100,
  "successful_tasks": 95,
  ...
}
```

---

### Franchises

#### `GET /api/franchises`
List all franchises.

**Response**:
```json
{
  "franchises": [
    {
      "agreement_id": "...",
      "franchise_id": "...",
      "status": "active",
      "created_at": "..."
    }
  ]
}
```

---

#### `GET /api/franchises/<franchise_id>`
Get comprehensive franchise report.

**Response**:
```json
{
  "franchise_id": "...",
  "financial_terms": {...},
  "revenue_summary": {...},
  "compliance": {...},
  "master_control": {...}
}
```

---

### Revenue

#### `GET /api/revenue/summary?days=30`
Get master revenue summary.

**Query Parameters**:
- `days` (optional): Number of days to analyze (default: 30)

**Response**:
```json
{
  "period_days": 30,
  "total_master_revenue": 1500.0,
  "total_slave_revenue": 3500.0,
  "master_revenue_by_slave": {...},
  "pending_verification": 2
}
```

---

### Tasks

#### `POST /api/tasks`
Submit a task to the system.

**Request Body**:
```json
{
  "function": "task_function_name",
  "priority": 8,
  "module": "api",
  "kwargs": {
    "param1": "value1"
  }
}
```

**Response**:
```json
{
  "success": true,
  "task_id": "...",
  "message": "Task submitted successfully"
}
```

---

### Memory

#### `POST /api/memory/search`
Search memories by keyword.

**Request Body**:
```json
{
  "keyword": "search_term",
  "limit": 10
}
```

**Response**:
```json
{
  "memories": [
    {
      "time": "...",
      "thought": "...",
      "category": "..."
    }
  ]
}
```

---

## Usage

### Starting the Server

```python
from project_guardian.api_server import APIServer
from project_guardian.system_orchestrator import SystemOrchestrator

# Initialize system
orchestrator = SystemOrchestrator()
await orchestrator.initialize()

# Create API server
api_server = APIServer(
    orchestrator=orchestrator,
    host="0.0.0.0",
    port=8080,
    enable_cors=True
)

# Start server (runs in background thread)
api_server.start(threaded=True)
```

### Example API Calls

```bash
# Health check
curl http://localhost:8080/api/health

# Get system status
curl http://localhost:8080/api/system/status

# List mutations
curl http://localhost:8080/api/mutations

# Get franchise report
curl http://localhost:8080/api/franchises/franchise_001

# Search memory
curl -X POST http://localhost:8080/api/memory/search \
  -H "Content-Type: application/json" \
  -d '{"keyword": "task", "limit": 5}'
```

---

## Security Considerations

### Current Implementation
- No authentication (development mode)
- CORS enabled for web access
- Basic error handling

### Production Recommendations
1. **Authentication**: Add API key or JWT authentication
2. **Rate Limiting**: Implement request rate limiting
3. **HTTPS**: Use HTTPS in production
4. **Input Validation**: Enhanced input validation
5. **Access Control**: Role-based access control (RBAC)
6. **Audit Logging**: Log all API access

---

## Integration Examples

### Python Client

```python
import requests

API_BASE = "http://localhost:8080/api"

# Get system status
response = requests.get(f"{API_BASE}/system/status")
status = response.json()

# Submit task
task_data = {
    "function": "process_data",
    "priority": 8,
    "kwargs": {"data": "..."}
}
response = requests.post(f"{API_BASE}/tasks", json=task_data)
result = response.json()
```

### JavaScript/TypeScript Client

```typescript
const API_BASE = 'http://localhost:8080/api';

// Get system status
const status = await fetch(`${API_BASE}/system/status`).then(r => r.json());

// Submit task
const taskResponse = await fetch(`${API_BASE}/tasks`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    function: 'process_data',
    priority: 8,
    kwargs: { data: '...' }
  })
});
const result = await taskResponse.json();
```

---

## Statistics

The API server tracks:
- Total requests
- Successful requests
- Failed requests
- Success rate
- Uptime

Access via `GET /api/system/stats`

---

## Error Handling

All endpoints return appropriate HTTP status codes:
- `200`: Success
- `201`: Created (task submission)
- `400`: Bad Request (invalid input)
- `404`: Not Found
- `500`: Internal Server Error
- `503`: Service Unavailable (component not initialized)

Error responses include JSON with error message:
```json
{
  "error": "Error description"
}
```

---

## Future Enhancements

- [ ] Authentication and authorization
- [ ] Rate limiting
- [ ] WebSocket support for real-time updates
- [ ] GraphQL endpoint
- [ ] API versioning
- [ ] Request/response logging
- [ ] Metrics export (Prometheus format)
- [ ] API documentation (OpenAPI/Swagger)

