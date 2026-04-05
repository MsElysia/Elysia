# CLI Review UI Implementation

## ✅ Status: Complete

Minimal CLI review UI for proposal management has been successfully implemented.

## Features

### Commands

1. **`list`** - List proposals with optional filters
   - `--status` - Filter by status (research, design, proposal, approved, rejected, implemented)
   - `--domain` - Filter by domain (elysia_core, hestia_scraping, etc.)
   - `--priority` - Filter by priority (low, medium, high)
   - Output: Table with ID, Title, Status, Domain, Priority, Impact, Effort, Risk

2. **`show <proposal_id>`** - Show proposal details
   - `--design` - Include design document
   - `--plan` - Include implementation plan
   - Output: Full metadata, description, tags, and optionally design/plan documents

3. **`set-status <proposal_id> <status>`** - Set proposal status
   - Validates lifecycle transitions
   - Records history entry with actor (human::username)
   - Supports: research, design, proposal, approved, rejected, implemented

4. **`approve <proposal_id>`** - Approve a proposal
   - `--approver` - Optional approver name (defaults to current user)
   - Validates proposal is in "proposal" status
   - Records approval in metadata and history

5. **`reject <proposal_id> --reason <reason>`** - Reject a proposal
   - Requires rejection reason
   - Validates proposal is in "proposal" status
   - Records rejection in metadata and history

6. **`history <proposal_id>`** - Show proposal history
   - Displays all history entries in reverse chronological order
   - Shows timestamp, actor, and change summary

## Usage Examples

```bash
# List all proposals
python elysia_proposals_cli.py list

# List proposals by status
python elysia_proposals_cli.py list --status proposal

# List proposals by domain
python elysia_proposals_cli.py list --domain elysia_core

# Show proposal details
python elysia_proposals_cli.py show prop-0001

# Show proposal with design document
python elysia_proposals_cli.py show prop-0001 --design

# Show proposal with implementation plan
python elysia_proposals_cli.py show prop-0001 --plan

# Set proposal status
python elysia_proposals_cli.py set-status prop-0001 proposal

# Approve a proposal
python elysia_proposals_cli.py approve prop-0001

# Reject a proposal
python elysia_proposals_cli.py reject prop-0001 --reason "Not aligned with current priorities"

# Show proposal history
python elysia_proposals_cli.py history prop-0001
```

## Implementation Details

- **File**: `elysia_proposals_cli.py`
- **Dependencies**: Uses `ProposalSystem` and `ProposalLifecycleManager` from `project_guardian.proposal_system`
- **Domain Support**: Dynamically loads canonical and extended domains from config
- **History Tracking**: All status changes are recorded with actor and timestamp
- **Error Handling**: Validates proposals exist and status transitions are valid

## Integration

The CLI integrates with:
- `ProposalSystem` - For listing and getting proposals
- `ProposalLifecycleManager` - For status transitions, approvals, and rejections
- `ProposalDomain` - For domain validation and filtering
- File system - For reading design documents and implementation plans

## Next Steps

The CLI is ready for use. Future enhancements could include:
- Interactive mode with prompts
- Batch operations
- Export to JSON/CSV
- Search functionality
- Color-coded output

---

**Implementation Date**: November 28, 2025
**Status**: ✅ Complete and tested

