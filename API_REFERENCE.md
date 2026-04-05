# API Reference - Project Guardian REST API

**Base URL**: `http://localhost:8080`  
**Version**: 1.0  
**Last Updated**: November 2, 2025

---

## 🔐 Authentication

Currently, the API does not require authentication for local use. For production deployments, implement authentication middleware.

**Recommended**: Use API key authentication or OAuth2 for production.

---

## 📋 Endpoints

### Health & Status

#### `GET /api/health`
Get system health status.

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-02T20:00:00Z",
  "components": {
    "api_server": "healthy",
    "runtime_loop": "healthy"
  },
  "resources": {
    "cpu_percent": 15.5,
    "memory_percent": 45.2,
    "disk_percent": 30.1
  }
}
```

**Status Codes**:
- `200 OK`: System healthy
- `503 Service Unavailable`: System degraded/unhealthy

---

#### `GET /api/metrics`
Get detailed system metrics.

**Response**:
```json
{
  "uptime_seconds": 3600,
  "total_requests": 150,
  "successful_requests": 148,
  "failed_requests": 2,
  "api_server": {
    "started_at": "2025-11-02T19:00:00Z",
    "total_requests": 150
  }
}
```

---

#### `GET /api/status`
Get comprehensive system status.

**Response**:
```json
{
  "initialized": true,
  "running": true,
  "uptime_seconds": 3600,
  "components": {
    "runtime_loop": true,
    "memory": true,
    "trust_registry": true
  }
}
```

---

### Mutations

#### `GET /api/mutations`
List all mutation proposals.

**Query Parameters**:
- `status` (optional): Filter by status (`pending`, `approved`, `rejected`)
- `limit` (optional): Limit results (default: 50)

**Response**:
```json
{
  "mutations": [
    {
      "mutation_id": "uuid-here",
      "target_module": "module.py",
      "status": "pending",
      "created_at": "2025-11-02T20:00:00Z",
      "description": "Add error handling"
    }
  ],
  "total": 10
}
```

---

#### `GET /api/mutations/{mutation_id}`
Get details of a specific mutation.

**Response**:
```json
{
  "mutation_id": "uuid-here",
  "target_module": "module.py",
  "status": "approved",
  "mutation_type": "code_modification",
  "description": "Add error handling",
  "created_at": "2025-11-02T20:00:00Z",
  "reviewed_at": "2025-11-02T20:05:00Z",
  "risk_level": "low",
  "trust_score": 0.8
}
```

---

#### `POST /api/mutations/propose`
Propose a new mutation.

**Request Body**:
```json
{
  "target_module": "project_guardian/test.py",
  "mutation_type": "code_modification",
  "description": "Add error handling",
  "proposed_code": "def new_function(): ...",
  "original_code": "def old_function(): ..."
}
```

**Response**:
```json
{
  "success": true,
  "mutation_id": "uuid-here",
  "status": "pending"
}
```

---

### Trust Registry

#### `GET /api/trust/nodes`
List all registered nodes.

**Response**:
```json
{
  "nodes": [
    {
      "node_id": "node-1",
      "trust_scores": {
        "mutation": 0.8,
        "overall": 0.75
      },
      "specialties": ["code_modification"],
      "registered_at": "2025-11-01T10:00:00Z"
    }
  ],
  "total": 5
}
```

---

#### `GET /api/trust/nodes/{node_id}`
Get details of a specific node.

**Response**:
```json
{
  "node_id": "node-1",
  "trust_scores": {
    "mutation": 0.8,
    "overall": 0.75,
    "financial": 0.6
  },
  "specialties": ["code_modification", "optimization"],
  "total_interactions": 150,
  "successful_interactions": 145,
  "registered_at": "2025-11-01T10:00:00Z",
  "last_seen": "2025-11-02T20:00:00Z"
}
```

---

#### `POST /api/trust/nodes/{node_id}/update`
Update trust scores for a node.

**Request Body**:
```json
{
  "trust_scores": {
    "mutation": 0.9,
    "overall": 0.85
  },
  "reason": "Successful mutations"
}
```

**Response**:
```json
{
  "success": true,
  "node_id": "node-1",
  "updated_scores": {
    "mutation": 0.9,
    "overall": 0.85
  }
}
```

---

### Franchises

#### `GET /api/franchises`
List all franchise agreements.

**Response**:
```json
{
  "franchises": [
    {
      "franchise_id": "franchise-1",
      "slave_id": "slave-1",
      "status": "active",
      "agreement_date": "2025-11-01T10:00:00Z",
      "royalty_rate": 0.15,
      "monthly_fee": 100.0
    }
  ],
  "total": 3
}
```

---

#### `GET /api/franchises/{franchise_id}`
Get franchise details.

**Response**:
```json
{
  "franchise_id": "franchise-1",
  "slave_id": "slave-1",
  "status": "active",
  "royalty_rate": 0.15,
  "monthly_fee": 100.0,
  "total_revenue": 5000.0,
  "master_share": 750.0,
  "franchise_share": 4250.0
}
```

---

### Financial

#### `GET /api/financial/credits`
Get credit balance and history.

**Response**:
```json
{
  "balance": 10000.0,
  "total_earned": 15000.0,
  "total_spent": 5000.0,
  "recent_transactions": [
    {
      "type": "earned",
      "amount": 100.0,
      "source": "task_completion",
      "timestamp": "2025-11-02T20:00:00Z"
    }
  ]
}
```

---

#### `GET /api/financial/assets`
Get asset portfolio.

**Response**:
```json
{
  "total_value": 50000.0,
  "assets": [
    {
      "type": "cash",
      "value": 30000.0,
      "currency": "USD"
    },
    {
      "type": "revenue_stream",
      "value": 20000.0,
      "monthly_recurring": true
    }
  ]
}
```

---

#### `GET /api/financial/revenue`
Get revenue statistics.

**Response**:
```json
{
  "total_revenue": 100000.0,
  "monthly_revenue": 5000.0,
  "master_share": 1500.0,
  "slave_shares": 3500.0,
  "revenue_streams": [
    {
      "stream_id": "stream-1",
      "type": "api_sales",
      "monthly": 5000.0
    }
  ]
}
```

---

### Tasks

#### `GET /api/tasks`
List tasks in the queue.

**Query Parameters**:
- `status` (optional): Filter by status
- `limit` (optional): Limit results

**Response**:
```json
{
  "tasks": [
    {
      "task_id": "task-1",
      "status": "queued",
      "priority": 7,
      "module": "mutation_engine",
      "created_at": "2025-11-02T20:00:00Z"
    }
  ],
  "total": 5,
  "queued": 3,
  "running": 1,
  "completed": 1
}
```

---

### Memory Search

#### `POST /api/memory/search`
Search memories by content.

**Request Body**:
```json
{
  "query": "user preferences",
  "limit": 10,
  "category": "preference"
}
```

**Response**:
```json
{
  "results": [
    {
      "memory_id": "mem-1",
      "content": "User prefers Python",
      "category": "preference",
      "importance": 0.8,
      "created_at": "2025-11-01T10:00:00Z",
      "relevance_score": 0.95
    }
  ],
  "total": 1
}
```

---

## 🔧 Error Responses

All errors follow this format:

```json
{
  "error": "Error message",
  "code": "ERROR_CODE",
  "details": {}
}
```

### Status Codes

- `200 OK`: Successful request
- `400 Bad Request`: Invalid request
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: System unavailable

---

## 📝 Examples

### cURL Examples

```bash
# Health check
curl http://localhost:8080/api/health

# Get system status
curl http://localhost:8080/api/status

# List mutations
curl http://localhost:8080/api/mutations

# Propose mutation
curl -X POST http://localhost:8080/api/mutations/propose \
  -H "Content-Type: application/json" \
  -d '{
    "target_module": "test.py",
    "mutation_type": "code_modification",
    "description": "Test mutation",
    "proposed_code": "def test(): return 42",
    "original_code": "def test(): return 0"
  }'

# Search memories
curl -X POST http://localhost:8080/api/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query": "user preferences", "limit": 10}'
```

### Python Examples

```python
import requests

BASE_URL = "http://localhost:8080"

# Health check
response = requests.get(f"{BASE_URL}/api/health")
health = response.json()
print(f"Status: {health['status']}")

# Propose mutation
mutation = {
    "target_module": "test.py",
    "mutation_type": "code_modification",
    "description": "Add error handling",
    "proposed_code": "def new(): ...",
    "original_code": "def old(): ..."
}
response = requests.post(f"{BASE_URL}/api/mutations/propose", json=mutation)
result = response.json()
print(f"Mutation ID: {result['mutation_id']}")
```

---

## 🔄 Rate Limiting

Currently no rate limiting implemented. Recommended for production:
- 100 requests/minute per IP
- 1000 requests/hour per IP

---

## 📊 WebSocket (Future)

Real-time updates via WebSocket:
- Mutation status updates
- Task completion notifications
- Health status changes

---

**Status**: Complete API reference documentation!




















