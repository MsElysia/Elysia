# Canonical Proposal Domains Implementation

## ✅ Status: Complete

Canonical proposal domains have been implemented with enum-based validation and config support.

## What Was Implemented

### 1. **ProposalDomain Enum** (`project_guardian/proposal_domains.py`)
- 5 canonical domains:
  - `elysia_core` - Core Elysia orchestration, task management, and system architecture
  - `hestia_scraping` - Property data scraping, web automation, and data collection
  - `legal_pipeline` - Legal document analysis, evidence archive, and RAG workflows
  - `infra_observability` - Infrastructure monitoring, logging, and system observability
  - `persona_mutation` - Persona management, identity evolution, and mutation controls

### 2. **Domain Configuration System**
- `ProposalDomainConfig` class manages:
  - Canonical domains (hardcoded in enum)
  - Extended domains (loaded from config file)
  - Domain descriptions
- Config file: `config/proposal_domains.json`

### 3. **Validation Integration**
- **ProposalValidator**: Now validates domains against canonical list
- **WebScout Agent**: Requires valid domain when creating proposals
- **Error Messages**: Clear validation errors for invalid domains

### 4. **Test Coverage**
- 11 new tests in `tests/test_proposal_domains.py`
- All tests passing ✅
- Existing tests still pass (using valid domains)

## Files Created/Modified

### New Files
- `project_guardian/proposal_domains.py` - Domain enum and config system
- `config/proposal_domains.json` - Domain configuration
- `tests/test_proposal_domains.py` - Domain validation tests

### Modified Files
- `project_guardian/proposal_system.py` - Added domain validation
- `project_guardian/webscout_agent.py` - Requires and validates domains

## Usage

### Creating Proposals with Valid Domains

```python
from project_guardian.proposal_domains import ProposalDomain
from project_guardian.webscout_agent import ElysiaWebScout

scout = ElysiaWebScout()

# Valid - using enum value
proposal = scout.create_proposal(
    task_description="Improve task orchestration",
    topic="task-orchestration",
    domain=ProposalDomain.ELYSIA_CORE.value  # "elysia_core"
)

# Valid - using string
proposal = scout.create_proposal(
    task_description="Enhance scraping",
    topic="scraping-improvements",
    domain="hestia_scraping"
)

# Invalid - will raise ValueError
proposal = scout.create_proposal(
    task_description="Test",
    topic="test",
    domain="invalid_domain"  # ❌ Raises ValueError
)
```

### Validating Domains

```python
from project_guardian.proposal_domains import validate_domain, ProposalDomain

# Check if domain is valid
is_valid, error = validate_domain("elysia_core")
assert is_valid == True

is_valid, error = validate_domain("invalid")
assert is_valid == False
assert "Invalid domain" in error
```

### Getting Domain Information

```python
from project_guardian.proposal_domains import get_domain_config, ProposalDomain

config = get_domain_config()

# Get all valid domains
all_domains = config.get_all_domains()

# Get description
desc = config.get_description("elysia_core")
# Returns: "Core Elysia orchestration, task management, and system architecture"
```

## Benefits

1. **Prevents Domain Drift** - No more arbitrary domain strings
2. **Type Safety** - Enum provides autocomplete and type checking
3. **Filtering** - Easy to filter proposals by domain
4. **Parallelization** - Can assign work by domain
5. **Ownership** - Can assign domain owners
6. **Extensibility** - Extended domains via config (use sparingly)

## Validation Rules

- **Required**: All proposals must have a domain
- **Canonical Only**: Must be one of the 5 canonical domains (or extended from config)
- **Case Sensitive**: Domains are lowercase with underscores
- **No Variations**: "elysia-core" is invalid, must be "elysia_core"

## Testing

Run domain tests:
```bash
pytest tests/test_proposal_domains.py -v
```

All 11 tests pass ✅

## Next Steps

1. ✅ Canonical domains implemented
2. ⏳ Minimal CLI review UI (next priority)
3. ⏳ Feed WebScout real problems per domain
4. ⏳ Add domain-based filtering to proposal API

