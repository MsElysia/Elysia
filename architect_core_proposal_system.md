# Architect-Core Proposal System Specification

## Overview

This system integrates with Elysia-WebScout to manage the proposal lifecycle from research to implementation. It expects structured outputs from WebScout and provides approval workflows.

## Canonical Design Folder Structure

```
proposals/
├── {proposal_id}/
│   ├── README.md              # Proposal overview and status
│   ├── research/
│   │   ├── summary.md        # Research summary
│   │   ├── sources.md         # Source citations with URLs
│   │   └── patterns.md        # Extracted patterns and best practices
│   ├── design/
│   │   ├── architecture.md    # Architecture design
│   │   ├── integration.md     # Integration points with Elysia
│   │   ├── api.md            # API specifications
│   │   └── diagrams/         # Architecture diagrams (optional)
│   ├── implementation/
│   │   ├── todos.md           # TODO list with priorities
│   │   ├── patches/           # Proposed code patches (.patch files)
│   │   ├── tests.md           # Test requirements
│   │   └── migration.md       # Migration plan (if applicable)
│   └── metadata.json          # Proposal metadata (JSON schema)
```

## Proposal Metadata Schema

```json
{
  "proposal_id": "webscout-{timestamp}-{topic-slug}",
  "title": "Human-readable proposal title",
  "description": "Brief description of the proposal",
  "status": "research|design|proposal|approved|rejected|implemented",
  "created_by": "elysia-webscout",
  "created_at": "2025-11-29T01:00:00Z",
  "updated_at": "2025-11-29T01:00:00Z",
  "research_sources": [
    {
      "url": "https://example.com",
      "title": "Source Title",
      "relevance": "high|medium|low",
      "extracted_patterns": ["pattern1", "pattern2"]
    }
  ],
  "design_impact": {
    "modules_affected": ["module1", "module2"],
    "complexity": "low|medium|high",
    "estimated_effort_hours": 40,
    "breaking_changes": false,
    "dependencies": ["dependency1", "dependency2"]
  },
  "approval_status": "pending|approved|rejected",
  "approved_by": null,
  "approved_at": null,
  "rejection_reason": null,
  "implementation_status": "not_started|in_progress|completed",
  "implementation_notes": []
}
```

## Proposal Lifecycle

### Phase 1: Research
**Trigger**: WebScout receives a research task

**Actions**:
1. WebScout creates proposal folder with `proposal_id`
2. WebScout researches and populates `research/` folder
3. WebScout creates initial `metadata.json` with status="research"
4. Architect-Core detects new proposal and validates structure

**Validation**:
- Folder structure exists
- Research files are populated
- Sources are cited
- Metadata is valid JSON

### Phase 2: Design
**Trigger**: Research phase complete, WebScout moves to design

**Actions**:
1. WebScout creates `design/` folder
2. WebScout designs architecture based on research
3. WebScout updates metadata.json: status="design"
4. Architect-Core evaluates design against Elysia architecture

**Validation**:
- Design files are complete
- Integration points are identified
- Architecture is compatible with Elysia
- No breaking changes without justification

### Phase 3: Proposal
**Trigger**: Design phase complete, ready for review

**Actions**:
1. WebScout creates `implementation/` folder with TODOs and patches
2. WebScout updates metadata.json: status="proposal"
3. Architect-Core creates proposal review workflow
4. Human review required

**Validation**:
- TODOs are prioritized
- Patches are provided (if code changes needed)
- Test requirements are defined
- Migration plan exists (if needed)

### Phase 4: Approval
**Trigger**: Human review and decision

**Actions**:
1. Human reviews proposal
2. Architect-Core updates metadata.json:
   - approval_status="approved" or "rejected"
   - approved_by="username"
   - approved_at="timestamp"
3. If approved: status="approved", move to implementation
4. If rejected: status="rejected", rejection_reason added

### Phase 5: Implementation
**Trigger**: Proposal approved

**Actions**:
1. Architect-Core updates metadata.json: status="implemented", implementation_status="in_progress"
2. Development team implements based on proposal
3. Architect-Core tracks progress
4. On completion: implementation_status="completed"

## Architect-Core Integration Points

### Proposal Watcher
```python
class ProposalWatcher:
    """Monitors proposals/ folder for new/updated proposals"""
    
    def watch_proposals(self):
        """Watch for new proposals from WebScout"""
        # Monitor proposals/ folder
        # Parse metadata.json
        # Validate structure
        # Trigger lifecycle transitions
```

### Proposal Validator
```python
class ProposalValidator:
    """Validates proposal structure and content"""
    
    def validate_structure(self, proposal_path):
        """Validate folder structure"""
        
    def validate_metadata(self, metadata):
        """Validate metadata.json schema"""
        
    def validate_design(self, proposal):
        """Validate design against Elysia architecture"""
```

### Proposal Lifecycle Manager
```python
class ProposalLifecycleManager:
    """Manages proposal lifecycle transitions"""
    
    def transition_to_design(self, proposal_id):
        """Move from research to design"""
        
    def transition_to_proposal(self, proposal_id):
        """Move from design to proposal"""
        
    def approve_proposal(self, proposal_id, approver):
        """Approve proposal"""
        
    def reject_proposal(self, proposal_id, reason):
        """Reject proposal"""
```

### Approval Workflow
```python
class ApprovalWorkflow:
    """Manages approval workflow for proposals"""
    
    def create_review(self, proposal_id):
        """Create review request"""
        
    def notify_reviewers(self, proposal_id):
        """Notify human reviewers"""
        
    def process_approval(self, proposal_id, decision):
        """Process approval/rejection decision"""
```

## API Endpoints (for Web UI)

### GET /api/proposals
List all proposals with status filter

### GET /api/proposals/{proposal_id}
Get proposal details

### POST /api/proposals/{proposal_id}/approve
Approve a proposal

### POST /api/proposals/{proposal_id}/reject
Reject a proposal

### GET /api/proposals/{proposal_id}/research
Get research files

### GET /api/proposals/{proposal_id}/design
Get design files

### GET /api/proposals/{proposal_id}/implementation
Get implementation files

## Implementation Checklist

- [ ] Create `proposals/` folder structure
- [ ] Implement ProposalWatcher
- [ ] Implement ProposalValidator
- [ ] Implement ProposalLifecycleManager
- [ ] Implement ApprovalWorkflow
- [ ] Create API endpoints
- [ ] Add Web UI for proposal review
- [ ] Integrate with Elysia-WebScout
- [ ] Add notification system
- [ ] Create proposal templates

## Example Proposal Flow

1. **WebScout receives task**: "Research multi-agent orchestration patterns"
2. **WebScout creates**: `proposals/webscout-20251129-001-multi-agent-orchestration/`
3. **WebScout researches**: Populates `research/` folder
4. **Architect-Core detects**: Validates structure, status="research"
5. **WebScout designs**: Creates `design/` folder, status="design"
6. **Architect-Core validates**: Checks against Elysia architecture
7. **WebScout proposes**: Creates `implementation/` folder, status="proposal"
8. **Human reviews**: Via Web UI or CLI
9. **Architect-Core approves**: Updates metadata, status="approved"
10. **Team implements**: Based on proposal, status="implemented"

## Benefits

1. **Structured Research**: All research is organized and citable
2. **Design Validation**: Designs are validated against Elysia architecture
3. **Approval Workflow**: Clear process for human review
4. **Implementation Tracking**: Track progress from proposal to completion
5. **Knowledge Base**: All proposals become part of Elysia's knowledge base

