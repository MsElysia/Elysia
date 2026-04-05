#!/usr/bin/env python3
"""
Example: WebScout and Architect-Core Integration
Demonstrates how Elysia-WebScout and Architect-Core work together.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core_modules.elysia_core_comprehensive.architect_core import ArchitectCore
from project_guardian.webscout_agent import ResearchSource


def main():
    """Demonstrate WebScout and Architect-Core integration"""
    
    print("=" * 60)
    print("WebScout and Architect-Core Integration Example")
    print("=" * 60)
    
    # Initialize Architect-Core with WebScout and proposals enabled
    print("\n1. Initializing Architect-Core with WebScout...")
    architect = ArchitectCore(enable_proposals=True, enable_webscout=True)
    
    # Get status report
    print("\n2. Getting status report...")
    status = architect.get_status_report()
    print(f"   - Modules registered: {status['ModuleArchitect']['count']}")
    print(f"   - WebScout status: {status['WebScout']['status']}")
    if status['WebScout']['status'] == 'active':
        print(f"   - WebScout agent: {status['WebScout']['agent_name']}")
        print(f"   - Existing proposals: {status['WebScout']['proposals_count']}")
    
    # Create a research proposal
    print("\n3. Creating a research proposal...")
    result = architect.create_research_proposal(
        task_description="Survey LangGraph, AutoGen, CrewAI for multi-agent orchestration patterns",
        topic="multi-agent-orchestration"
    )
    
    if result["status"] == "success":
        proposal_id = result["proposal_id"]
        print(f"   ✓ Created proposal: {proposal_id}")
        
        # Add research findings
        print("\n4. Adding research findings...")
        sources = [
            {
                "url": "https://langchain-ai.github.io/langgraph/",
                "title": "LangGraph Documentation",
                "relevance": "high",
                "extracted_patterns": [
                    "Task graphs for agent orchestration",
                    "State management across agents",
                    "Human-in-the-loop workflows"
                ],
                "summary": "LangGraph provides task graph orchestration for multi-agent systems"
            },
            {
                "url": "https://github.com/microsoft/autogen",
                "title": "AutoGen Framework",
                "relevance": "high",
                "extracted_patterns": [
                    "Multi-agent conversations",
                    "Tool routing and delegation",
                    "Agent memory and context"
                ],
                "summary": "AutoGen enables multi-agent conversations with tool use"
            }
        ]
        
        research_summary = """
        ## Research Summary: Multi-Agent Orchestration Patterns
        
        After surveying LangGraph, AutoGen, and CrewAI, key patterns emerge:
        
        1. **Task Graphs**: All frameworks use graph-based task orchestration
        2. **State Management**: Shared state across agents is critical
        3. **Tool Routing**: Agents need clear mechanisms to route tools and tasks
        4. **Human-in-the-Loop**: All frameworks support human intervention points
        
        ### Recommended Approach for Elysia:
        - Use task graphs for complex workflows
        - Implement shared state management
        - Add clear tool routing mechanisms
        - Support human approval checkpoints
        """
        
        result = architect.add_research_to_proposal(
            proposal_id,
            sources,
            research_summary
        )
        
        if result["status"] == "success":
            print(f"   ✓ Added research to proposal")
        
        # Add design documents
        print("\n5. Adding design documents...")
        architecture = """
        # Architecture Design: Multi-Agent Orchestration
        
        ## Overview
        Integrate task graph orchestration into Elysia's existing architecture.
        
        ## Components
        
        ### TaskGraphOrchestrator
        - Manages agent task graphs
        - Routes tasks between agents
        - Tracks state across agents
        
        ### AgentRouter
        - Routes tools to appropriate agents
        - Manages agent capabilities
        - Handles delegation
        
        ### StateManager
        - Shared state across agents
        - Context preservation
        - Memory management
        """
        
        integration = """
        # Integration Points
        
        ## With Architect-Core
        - Register TaskGraphOrchestrator as a module
        - Use ModuleArchitect for agent registration
        - Use PolicyArchitect for orchestration rules
        
        ## With ElysiaLoop
        - Integrate task graphs with event loop
        - Use loop for async task execution
        - Handle task scheduling
        
        ## With Project Guardian
        - Validate agent actions
        - Monitor agent behavior
        - Enforce safety policies
        """
        
        result = architect.add_design_to_proposal(
            proposal_id,
            architecture,
            integration
        )
        
        if result["status"] == "success":
            print(f"   ✓ Added design documents")
        
        # Add implementation plan
        print("\n6. Adding implementation plan...")
        todos = [
            {
                "task": "Create TaskGraphOrchestrator class",
                "priority": "high",
                "notes": "Core orchestration logic"
            },
            {
                "task": "Implement AgentRouter",
                "priority": "high",
                "notes": "Tool routing and delegation"
            },
            {
                "task": "Create StateManager for shared state",
                "priority": "medium",
                "notes": "State persistence across agents"
            },
            {
                "task": "Integrate with Architect-Core",
                "priority": "high",
                "notes": "Module registration and routing"
            },
            {
                "task": "Write tests",
                "priority": "medium",
                "notes": "Unit and integration tests"
            }
        ]
        
        result = architect.add_implementation_to_proposal(
            proposal_id,
            todos
        )
        
        if result["status"] == "success":
            print(f"   ✓ Added implementation plan")
        
        # Get proposal details
        print("\n7. Retrieving proposal details...")
        proposal = architect.get_proposal(proposal_id)
        if proposal:
            print(f"   - Title: {proposal.get('title')}")
            print(f"   - Status: {proposal.get('status')}")
            print(f"   - Created: {proposal.get('created_at')}")
            print(f"   - Research sources: {len(proposal.get('research_sources', []))}")
        
        # List all proposals
        print("\n8. Listing all proposals...")
        proposals = architect.get_proposals()
        print(f"   Total proposals: {len(proposals)}")
        for prop in proposals[:3]:  # Show first 3
            print(f"   - {prop.get('proposal_id')}: {prop.get('title')} ({prop.get('status')})")
    
    else:
        print(f"   ✗ Failed to create proposal: {result.get('message')}")
    
    # Final status
    print("\n9. Final status report...")
    final_status = architect.get_status_report()
    print(f"   - Modules: {final_status['ModuleArchitect']['count']}")
    print(f"   - Proposals: {final_status.get('ProposalSystem', {}).get('proposals_count', 0)}")
    print(f"   - WebScout: {final_status['WebScout']['status']}")
    
    print("\n" + "=" * 60)
    print("Integration example completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()

