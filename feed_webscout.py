#!/usr/bin/env python3
"""
Feed WebScout Real Problems
Creates proposals for each canonical domain to test the end-to-end system.
"""

import sys
from pathlib import Path
from project_guardian.webscout_agent import ElysiaWebScout
from project_guardian.proposal_domains import ProposalDomain

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def feed_webscout_problems():
    """Feed WebScout one real problem per canonical domain"""
    
    scout = ElysiaWebScout(proposals_root=Path("proposals"))
    
    # Define real problems per domain (from ChatGPT guidance)
    problems = [
        {
            "domain": ProposalDomain.ELYSIA_CORE.value,
            "topic": "better-internal-task-graph-orchestration",
            "description": "Research and design improvements for Elysia's internal task graph and orchestration system. Focus on multi-agent coordination patterns, task dependency management, and failure recovery strategies.",
            "tags": ["orchestration", "task-management", "multi-agent"]
        },
        {
            "domain": ProposalDomain.HESTIA_SCRAPING.value,
            "topic": "robust-multi-source-property-scraping",
            "description": "Enhance Hestia's property scraping capabilities with robust multi-source data collection, error handling, anti-bot strategies, and data normalization. Focus on Zillow, Redfin, and other property data sources.",
            "tags": ["scraping", "hestia", "property-data", "zillow"]
        },
        {
            "domain": ProposalDomain.LEGAL_PIPELINE.value,
            "topic": "end-to-end-rag-workflow-for-legal-docs",
            "description": "Design and implement an end-to-end RAG (Retrieval-Augmented Generation) workflow for legal document analysis. Cover ingest → index → query pipeline for transcripts, bodycam footage, and evidence archive.",
            "tags": ["legal", "rag", "document-analysis", "evidence"]
        },
        {
            "domain": ProposalDomain.INFRA_OBSERVABILITY.value,
            "topic": "system-observability-and-monitoring",
            "description": "Improve infrastructure monitoring, logging, and system observability for Elysia. Focus on metrics collection, distributed tracing, and alerting for AI agent systems.",
            "tags": ["observability", "monitoring", "logging", "metrics"]
        },
        {
            "domain": ProposalDomain.PERSONA_MUTATION.value,
            "topic": "persona-evolution-and-identity-management",
            "description": "Research persona management, identity evolution, and mutation controls for Elysia. Design systems for safe persona updates, version tracking, and rollback capabilities.",
            "tags": ["persona", "mutation", "identity", "evolution"]
        }
    ]
    
    print("=" * 60)
    print("Feeding WebScout Real Problems")
    print("=" * 60)
    print()
    
    created_proposals = []
    
    for problem in problems:
        print(f"Creating proposal for domain: {problem['domain']}")
        print(f"  Topic: {problem['topic']}")
        print(f"  Description: {problem['description'][:80]}...")
        
        try:
            result = scout.create_proposal(
                task_description=problem["description"],
                topic=problem["topic"],
                domain=problem["domain"],
                tags=problem["tags"],
                check_duplicates=True
            )
            
            proposal_id = result["proposal_id"]
            created_proposals.append(proposal_id)
            
            print(f"  ✅ Created: {proposal_id}")
            
            if result.get("similar_proposals"):
                print(f"  ⚠️  Found {len(result['similar_proposals'])} similar proposals")
            
            # Conduct research (this will use LLM if available, otherwise simulated)
            print(f"  🔍 Conducting research...")
            sources, summary = scout.conduct_web_research(problem["description"], max_sources=5)
            scout.add_research(proposal_id, sources, summary)
            print(f"  ✅ Research completed ({len(sources)} sources)")
            
            # Generate design (simplified - in real scenario would use LLM)
            print(f"  📐 Generating design...")
            architecture = f"""# Architecture Design

## Problem
{problem["description"]}

## Proposed Solution
This is a placeholder architecture design. In a real scenario, WebScout would use LLM to generate a comprehensive design based on research findings.

## Key Components
- Component 1: Description
- Component 2: Description
- Component 3: Description

## Integration Points
- Integration with existing Elysia modules
- API boundaries
- Data flow
"""
            integration = f"""# Integration Design

## Integration with Elysia
This proposal integrates with the following Elysia components:
- Architect-Core
- ElysiaLoop-Core
- Project Guardian

## Data Flow
[Describe data flow]

## API Contracts
[Describe API contracts]
"""
            scout.add_design(proposal_id, architecture, integration)
            print(f"  ✅ Design generated")
            
            # Create implementation plan
            print(f"  📋 Creating implementation plan...")
            todos = [
                {"task": "Research and analysis", "priority": "high", "notes": "Complete research phase"},
                {"task": "Design architecture", "priority": "high", "notes": "Create detailed design"},
                {"task": "Implement core functionality", "priority": "medium", "notes": "Build main features"},
                {"task": "Add tests", "priority": "medium", "notes": "Write unit and integration tests"},
                {"task": "Documentation", "priority": "low", "notes": "Update documentation"}
            ]
            scout.add_implementation(proposal_id, todos)
            print(f"  ✅ Implementation plan created")
            
            print()
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            print()
            continue
    
    print("=" * 60)
    print(f"Summary: Created {len(created_proposals)} proposals")
    print("=" * 60)
    print()
    
    if created_proposals:
        print("Created proposals:")
        for prop_id in created_proposals:
            print(f"  - {prop_id}")
        print()
        print("Use the CLI to review:")
        print(f"  python elysia_proposals_cli.py list")
        print(f"  python elysia_proposals_cli.py show {created_proposals[0]}")
    else:
        print("No proposals were created.")


if __name__ == "__main__":
    feed_webscout_problems()

