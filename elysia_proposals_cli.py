#!/usr/bin/env python3
"""
Elysia Proposals CLI
Minimal command-line interface for proposal management and review.
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import getpass

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from project_guardian.proposal_system import ProposalSystem, ProposalLifecycleManager
    from project_guardian.proposal_domains import ProposalDomain, get_domain_config
except ImportError as e:
    print(f"Error importing proposal system: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)


def get_allowed_domains():
    """Get list of all allowed domains (canonical + extended)"""
    config = get_domain_config()
    return sorted(list(config.get_all_domains()))


class ProposalCLI:
    """Command-line interface for proposal management"""
    
    def __init__(self, proposals_root: Optional[Path] = None):
        self.proposals_root = proposals_root or Path("proposals")
        self.proposals_root.mkdir(exist_ok=True)
        self.proposal_system = ProposalSystem(proposals_root=self.proposals_root)
        self.lifecycle_manager = self.proposal_system.lifecycle_manager
    
    def setup_parser(self):
        """Setup command line argument parser"""
        parser = argparse.ArgumentParser(
            description="Elysia Proposals CLI - Manage and review proposals",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
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
            """
        )
        
        subparsers = parser.add_subparsers(dest="command", help="Available commands")
        
        # List command
        list_parser = subparsers.add_parser("list", help="List proposals")
        list_parser.add_argument("--status", 
                                choices=["research", "design", "proposal", "approved", "rejected", "implemented",
                                        "in_implementation", "implementation_failed", "implementation_partial",
                                        "rolled_back", "rework_required"],
                                help="Filter by status")
        # Get allowed domains for choices
        allowed_domains = get_allowed_domains()
        list_parser.add_argument("--domain", choices=allowed_domains,
                                help="Filter by domain")
        list_parser.add_argument("--priority", choices=["low", "medium", "high"],
                                help="Filter by priority")
        
        # Show command
        show_parser = subparsers.add_parser("show", help="Show proposal details")
        show_parser.add_argument("proposal_id", help="Proposal ID")
        show_parser.add_argument("--design", action="store_true",
                                help="Show design document")
        show_parser.add_argument("--plan", action="store_true",
                                help="Show implementation plan")
        
        # Set-status command
        set_status_parser = subparsers.add_parser("set-status", help="Set proposal status")
        set_status_parser.add_argument("proposal_id", help="Proposal ID")
        set_status_parser.add_argument("status", 
                                      choices=["research", "design", "proposal", "approved", "rejected", "implemented",
                                              "in_implementation", "implementation_failed", "implementation_partial",
                                              "rolled_back", "rework_required"],
                                      help="New status")
        
        # Implement command
        implement_parser = subparsers.add_parser("implement", help="Implement a proposal")
        implement_parser.add_argument("proposal_id", nargs="?", help="Proposal ID")
        implement_parser.add_argument("--dry-run", action="store_true",
                                     help="Dry run mode (don't make actual changes)")
        
        # Implement-all command
        implement_all_parser = subparsers.add_parser("implement-all", help="Implement all approved proposals")
        implement_all_parser.add_argument("--dry-run", action="store_true",
                                         help="Dry run mode (don't make actual changes)")
        
        # Implementation-status command
        impl_status_parser = subparsers.add_parser("implementation-status", help="Show implementation status")
        impl_status_parser.add_argument("proposal_id", help="Proposal ID")
        
        # Approve command
        approve_parser = subparsers.add_parser("approve", help="Approve a proposal")
        approve_parser.add_argument("proposal_id", help="Proposal ID")
        approve_parser.add_argument("--approver", default=None,
                                   help="Approver name (defaults to current user)")
        
        # Reject command
        reject_parser = subparsers.add_parser("reject", help="Reject a proposal")
        reject_parser.add_argument("proposal_id", help="Proposal ID")
        reject_parser.add_argument("--reason", required=True,
                                  help="Reason for rejection")
        
        # History command
        history_parser = subparsers.add_parser("history", help="Show proposal history")
        history_parser.add_argument("proposal_id", help="Proposal ID")
        
        return parser
    
    def format_table_row(self, row: List[str], widths: List[int]) -> str:
        """Format a table row with fixed column widths"""
        return "  ".join(f"{cell:<{width}}" for cell, width in zip(row, widths))
    
    def list_proposals(self, args):
        """List proposals with optional filters"""
        proposals = self.proposal_system.list_proposals(status_filter=args.status)
        
        # Apply additional filters
        if args.domain:
            proposals = [p for p in proposals if p.get("domain") == args.domain]
        if args.priority:
            proposals = [p for p in proposals if p.get("priority") == args.priority]
        
        if not proposals:
            print("No proposals found.")
            return
        
        # Table headers
        headers = ["ID", "Title", "Status", "Domain", "Priority", "Impact", "Effort", "Risk"]
        widths = [12, 40, 12, 18, 10, 6, 6, 8]
        
        print(self.format_table_row(headers, widths))
        print("-" * sum(widths + [len(widths) * 2 - 2]))
        
        # Table rows
        for prop in proposals:
            row = [
                prop.get("proposal_id", "N/A")[:12],
                prop.get("title", "N/A")[:40],
                prop.get("status", "N/A")[:12],
                prop.get("domain", "N/A")[:18],
                prop.get("priority", "N/A")[:10],
                str(prop.get("impact_score", "N/A")),
                str(prop.get("effort_score", "N/A")),
                prop.get("risk_level", "N/A")[:8]
            ]
            print(self.format_table_row(row, widths))
        
        print(f"\nTotal: {len(proposals)} proposal(s)")
    
    def show_proposal(self, args):
        """Show proposal details"""
        proposal = self.proposal_system.get_proposal(args.proposal_id)
        
        if not proposal:
            print(f"Error: Proposal '{args.proposal_id}' not found.")
            sys.exit(1)
        
        # Print metadata
        print(f"\n{'='*60}")
        print(f"Proposal: {proposal.get('proposal_id', 'N/A')}")
        print(f"{'='*60}\n")
        
        print(f"Title:       {proposal.get('title', 'N/A')}")
        print(f"Status:      {proposal.get('status', 'N/A')}")
        print(f"Domain:      {proposal.get('domain', 'N/A')}")
        print(f"Priority:    {proposal.get('priority', 'N/A')}")
        print(f"Impact:      {proposal.get('impact_score', 'N/A')}/5")
        print(f"Effort:      {proposal.get('effort_score', 'N/A')}/5")
        print(f"Risk:        {proposal.get('risk_level', 'N/A')}")
        print(f"Created:     {proposal.get('created_at', 'N/A')}")
        print(f"Updated:     {proposal.get('updated_at', 'N/A')}")
        print(f"Created by:  {proposal.get('created_by', 'N/A')}")
        print(f"Updated by:  {proposal.get('last_updated_by', 'N/A')}")
        
        if proposal.get('approved_by'):
            print(f"Approved by: {proposal.get('approved_by')} at {proposal.get('approved_at', 'N/A')}")
        
        if proposal.get('rejection_reason'):
            print(f"Rejected:    {proposal.get('rejection_reason')}")
        
        print(f"\nDescription:\n{proposal.get('description', 'N/A')}\n")
        
        # Tags
        tags = proposal.get('tags', [])
        if tags:
            print(f"Tags: {', '.join(tags)}\n")
        
        # Show design document if requested
        if args.design:
            design_path = self.proposals_root / args.proposal_id / "design" / "architecture.md"
            if design_path.exists():
                print(f"\n{'='*60}")
                print("Design Document:")
                print(f"{'='*60}\n")
                with open(design_path, 'r', encoding='utf-8') as f:
                    print(f.read())
            else:
                print("\nDesign document not found.")
        
        # Show implementation plan if requested
        if args.plan:
            plan_path = self.proposals_root / args.proposal_id / "design" / "implementation_plan.md"
            if plan_path.exists():
                print(f"\n{'='*60}")
                print("Implementation Plan:")
                print(f"{'='*60}\n")
                with open(plan_path, 'r', encoding='utf-8') as f:
                    print(f.read())
            else:
                print("\nImplementation plan not found.")
        
        # Show full metadata as JSON if neither design nor plan requested
        if not args.design and not args.plan:
            print(f"\n{'='*60}")
            print("Full Metadata (JSON):")
            print(f"{'='*60}\n")
            print(json.dumps(proposal, indent=2))
    
    def set_status(self, args):
        """Set proposal status"""
        proposal = self.proposal_system.get_proposal(args.proposal_id)
        
        if not proposal:
            print(f"Error: Proposal '{args.proposal_id}' not found.")
            sys.exit(1)
        
        current_status = proposal.get("status")
        
        if current_status == args.status:
            print(f"Proposal is already in '{args.status}' status.")
            return
        
        # Handle lifecycle transitions
        username = f"human::{getpass.getuser()}"
        
        if args.status == "approved":
            # Allow resetting from implementation_failed back to approved
            if current_status in ["implementation_failed", "rework_required"]:
                # Direct status update to reset
                proposal_path = self.proposals_root / args.proposal_id
                metadata_path = proposal_path / "metadata.json"
                
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                
                metadata["status"] = args.status
                metadata["updated_at"] = datetime.now().isoformat()
                metadata["last_updated_by"] = username
                
                # Add history entry
                if "history" not in metadata:
                    metadata["history"] = []
                metadata["history"].append({
                    "timestamp": datetime.now().isoformat(),
                    "actor": username,
                    "change_summary": f"Status reset from {current_status} to {args.status} for retry"
                })
                
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
                
                result = {"status": "success", "proposal_id": args.proposal_id, "new_status": args.status}
            else:
                result = self.lifecycle_manager.approve_proposal(args.proposal_id, username)
        elif args.status == "rejected":
            print("Error: Use 'reject' command with --reason to reject a proposal.")
            sys.exit(1)
        elif args.status == "design" and current_status == "research":
            result = self.lifecycle_manager.transition_to_design(args.proposal_id)
        elif args.status == "proposal" and current_status == "design":
            result = self.lifecycle_manager.transition_to_proposal(args.proposal_id)
        else:
            # Direct status update (for manual transitions)
            proposal_path = self.proposals_root / args.proposal_id
            metadata_path = proposal_path / "metadata.json"
            
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            
            metadata["status"] = args.status
            metadata["updated_at"] = datetime.now().isoformat()
            metadata["last_updated_by"] = username
            
            # Add history entry
            if "history" not in metadata:
                metadata["history"] = []
            metadata["history"].append({
                "timestamp": datetime.now().isoformat(),
                "actor": username,
                "change_summary": f"Status changed from {current_status} to {args.status}"
            })
            
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            result = {"status": "success", "proposal_id": args.proposal_id, "new_status": args.status}
        
        if result.get("status") == "error":
            print(f"Error: {result.get('message')}")
            sys.exit(1)
        
        print(f"Proposal {args.proposal_id} status changed to '{args.status}'")
    
    def approve_proposal(self, args):
        """Approve a proposal"""
        approver = args.approver or f"human::{getpass.getuser()}"
        result = self.lifecycle_manager.approve_proposal(args.proposal_id, approver)
        
        if result.get("status") == "error":
            print(f"Error: {result.get('message')}")
            sys.exit(1)
        
        print(f"Proposal {args.proposal_id} approved by {approver}")
    
    def reject_proposal(self, args):
        """Reject a proposal"""
        result = self.lifecycle_manager.reject_proposal(args.proposal_id, args.reason)
        
        if result.get("status") == "error":
            print(f"Error: {result.get('message')}")
            sys.exit(1)
        
        print(f"Proposal {args.proposal_id} rejected: {args.reason}")
    
    def show_history(self, args):
        """Show proposal history"""
        proposal = self.proposal_system.get_proposal(args.proposal_id)
        
        if not proposal:
            print(f"Error: Proposal '{args.proposal_id}' not found.")
            sys.exit(1)
        
        history = proposal.get("history", [])
        
        if not history:
            print(f"No history entries for proposal {args.proposal_id}.")
            return
        
        print(f"\n{'='*60}")
        print(f"History for Proposal: {args.proposal_id}")
        print(f"{'='*60}\n")
        
        # Sort by timestamp (newest first)
        history_sorted = sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)
        
        for entry in history_sorted:
            timestamp = entry.get("timestamp", "N/A")
            actor = entry.get("actor", "N/A")
            change = entry.get("change_summary", "N/A")
            
            print(f"[{timestamp}] {actor}")
            print(f"  {change}\n")
    
    def implement_proposal(self, args):
        """Implement a proposal"""
        try:
            from elysia.agents.implementer import ImplementerAgent
            from pathlib import Path
            
            if not args.proposal_id:
                print("Error: proposal_id is required")
                sys.exit(1)
            
            # Initialize Elysia ImplementerAgent
            implementer = ImplementerAgent(
                repo_root=Path("."),
                proposal_system=self.proposal_system,
                event_bus=None,  # CLI doesn't need event bus
                dry_run=args.dry_run
            )
            
            print(f"Implementing proposal: {args.proposal_id}")
            if args.dry_run:
                print("  [DRY RUN MODE - No changes will be made]")
            
            result = implementer.run_for_proposal(args.proposal_id)
            
            print(f"\n{'='*60}")
            print("Implementation Result:")
            print(f"{'='*60}")
            if result.get("success"):
                print(f"  Status: ✅ Success")
                print(f"  Steps: {result.get('steps_completed', 0)}/{result.get('steps_total', 0)} completed")
            else:
                print(f"  Status: ❌ Failed")
                print(f"  Steps: {result.get('steps_completed', 0)}/{result.get('steps_total', 0)} completed")
                if result.get("error"):
                    print(f"  Error: {result.get('error')}")
            
            if result.get("step_results"):
                print(f"\n  Step Results:")
                for step_result in result.get("step_results", []):
                    status_icon = "✅" if step_result.get("success") else "❌"
                    step_type = step_result.get("step_type", "unknown")
                    print(f"    {status_icon} {step_type}")
        
        except ImportError as e:
            print(f"Error: Implementer module not available: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error implementing proposal: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def implement_all_proposals(self, args):
        """Implement all approved proposals"""
        try:
            from elysia.agents.implementer import ImplementerAgent
            from pathlib import Path
            
            # Initialize Elysia ImplementerAgent
            implementer = ImplementerAgent(
                repo_root=Path("."),
                proposal_system=self.proposal_system,
                event_bus=None,
                dry_run=args.dry_run
            )
            
            if args.dry_run:
                print("[DRY RUN MODE - No changes will be made]")
            
            print("Finding eligible proposals...")
            result = implementer.run_batch()
            
            print(f"\n{'='*60}")
            print("Batch Implementation Summary:")
            print(f"{'='*60}")
            print(f"  Total: {result.get('total', 0)}")
            print(f"  Successful: {result.get('successful', 0)}")
            print(f"  Failed: {result.get('failed', 0)}")
            
            if result.get("results"):
                print(f"\n  Results:")
                for r in result.get("results", []):
                    proposal_id = r.get("proposal_id", "unknown")
                    status = "✅" if r.get("success") else "❌"
                    steps = f"{r.get('steps_completed', 0)}/{r.get('steps_total', 0)}"
                    print(f"    {status} {proposal_id}: {steps} steps")
        
        except ImportError as e:
            print(f"Error: Implementer module not available: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error implementing proposals: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    def show_implementation_status(self, args):
        """Show implementation status for a proposal"""
        proposal = self.proposal_system.get_proposal(args.proposal_id)
        
        if not proposal:
            print(f"Error: Proposal '{args.proposal_id}' not found.")
            sys.exit(1)
        
        print(f"\n{'='*60}")
        print(f"Implementation Status: {args.proposal_id}")
        print(f"{'='*60}\n")
        
        impl_status = proposal.get("implementation_status", "not_started")
        last_implemented = proposal.get("last_implemented_at", "N/A")
        last_result = proposal.get("last_implementation_result", "N/A")
        
        print(f"Implementation Status: {impl_status}")
        print(f"Last Implemented:     {last_implemented}")
        print(f"Last Result:          {last_result}")
        
        # Show recent implementer history entries
        history = proposal.get("history", [])
        implementer_entries = [
            h for h in history
            if h.get("actor") == "Elysia-Implementer"
        ]
        
        if implementer_entries:
            print(f"\nRecent Implementation History:")
            # Show last 5 entries
            for entry in sorted(implementer_entries, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]:
                timestamp = entry.get("timestamp", "N/A")
                change = entry.get("change_summary", "N/A")
                print(f"  [{timestamp}] {change}")
    
    def run(self):
        """Run the CLI"""
        parser = self.setup_parser()
        args = parser.parse_args()
        
        if not args.command:
            parser.print_help()
            sys.exit(1)
        
        # Route to appropriate handler
        if args.command == "list":
            self.list_proposals(args)
        elif args.command == "show":
            self.show_proposal(args)
        elif args.command == "set-status":
            self.set_status(args)
        elif args.command == "approve":
            self.approve_proposal(args)
        elif args.command == "reject":
            self.reject_proposal(args)
        elif args.command == "history":
            self.show_history(args)
        elif args.command == "implement":
            self.implement_proposal(args)
        elif args.command == "implement-all":
            self.implement_all_proposals(args)
        elif args.command == "implementation-status":
            self.show_implementation_status(args)
        else:
            parser.print_help()
            sys.exit(1)


def main():
    """Main entry point"""
    cli = ProposalCLI()
    cli.run()


if __name__ == "__main__":
    main()

