"""
Architect-Core
The high-level orchestrator for all Elysia architecture components.
Integrated from old modules.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ModuleArchitect:
    """Manages module registration, roles, and dependencies"""
    
    def __init__(self):
        self.modules = {}
    
    def register_module(self, module_data: Dict[str, Any]) -> Dict[str, Any]:
        name = module_data.get("name", "unknown")
        self.modules[name] = {
            "version": module_data.get("version", "1.0"),
            "role": module_data.get("role", "uncategorized"),
            "status": "registered",
            "dependencies": module_data.get("dependencies", []),
            "exposed_interfaces": module_data.get("exposed_interfaces", [])
        }
        return {"status": "registered", "module": name}
    
    def status_report(self) -> Dict[str, Any]:
        return {"modules": self.modules, "count": len(self.modules)}
    
    def receive_command(self, command: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if command == "register_module":
            return self.register_module(data)
        elif command == "list_modules":
            return {"modules": list(self.modules.keys())}
        elif command == "get_module":
            module_name = data.get("name")
            return self.modules.get(module_name, {"status": "not_found"})
        return {"status": "unknown_command", "command": command}


class MutationArchitect:
    """Oversees mutation logic, version tracking, and optimization planning"""
    
    def __init__(self):
        self.active_mutation_mode = "review_if_risky"
        self.mutation_log = []
    
    def status_report(self) -> Dict[str, Any]:
        return {
            "active_mode": self.active_mutation_mode,
            "recent_mutations": self.mutation_log[-5:],
            "total_mutations": len(self.mutation_log)
        }
    
    def receive_command(self, command: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if command == "set_mutation_mode":
            self.active_mutation_mode = data.get("mode", "manual")
            return {"status": "mode_updated", "new_mode": self.active_mutation_mode}
        elif command == "log_mutation":
            mutation_entry = {
                "timestamp": data.get("timestamp"),
                "module": data.get("module"),
                "type": data.get("type"),
                "status": data.get("status", "pending")
            }
            self.mutation_log.append(mutation_entry)
            return {"status": "mutation_logged", "entry": mutation_entry}
        elif command == "get_mutation_history":
            return {"mutations": self.mutation_log}
        return {"status": "unknown_command", "command": command}


class PolicyArchitect:
    """Manages system-wide rules and constraints"""
    
    def __init__(self):
        self.policies = {
            "banned_words": [],
            "trust_threshold": 0.7,
            "mutation_approval_required": True
        }
    
    def update_policy(self, name: str, rule: Any) -> Dict[str, Any]:
        self.policies[name] = rule
        return {"status": "policy_updated", "policy": name, "value": rule}
    
    def status_report(self) -> Dict[str, Any]:
        return {"policies": self.policies}
    
    def receive_command(self, command: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if command == "update_policy":
            return self.update_policy(data.get("name"), data.get("rule"))
        elif command == "get_policy":
            policy_name = data.get("name")
            return {"policy": policy_name, "value": self.policies.get(policy_name)}
        elif command == "list_policies":
            return {"policies": list(self.policies.keys())}
        return {"status": "unknown_command", "command": command}


class PersonaArchitect:
    """Maintains active persona configurations and tone presets"""
    
    def __init__(self):
        self.persona = {
            "name": "warm_guide",
            "tone": "encouraging",
            "style": "thoughtful",
            "voice_mode": "guardian"
        }
    
    def update_persona(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        self.persona.update(settings)
        return {"status": "persona_updated", "persona": self.persona}
    
    def status_report(self) -> Dict[str, Any]:
        return {"active_persona": self.persona}
    
    def receive_command(self, command: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if command == "update_persona":
            return self.update_persona(data)
        elif command == "get_persona":
            return {"persona": self.persona}
        return {"status": "unknown_command", "command": command}


class ArchitectCore:
    """
    The high-level orchestrator for all Elysia architecture components.
    Routes commands to appropriate sub-architects.
    """
    
    def __init__(self, enable_proposals: bool = True, enable_webscout: bool = True):
        self.module_architect = ModuleArchitect()
        self.mutation_architect = MutationArchitect()
        self.policy_architect = PolicyArchitect()
        self.persona_architect = PersonaArchitect()
        
        # Initialize proposal system if enabled
        self.proposal_system = None
        if enable_proposals:
            try:
                from project_guardian.proposal_system import ProposalSystem
                self.proposal_system = ProposalSystem()
            except ImportError:
                logger.warning("Proposal system not available (watchdog may not be installed)")
        
        # Initialize WebScout agent if enabled
        self.webscout = None
        if enable_webscout:
            try:
                from project_guardian.webscout_agent import ElysiaWebScout
                # Use same proposals root as proposal system if available
                proposals_root = None
                if self.proposal_system:
                    proposals_root = self.proposal_system.proposals_root
                # ElysiaWebScout will try to get web_reader from GuardianCore singleton if not provided
                self.webscout = ElysiaWebScout(web_reader=None, proposals_root=proposals_root)
                # Register WebScout as a module
                self.module_architect.register_module({
                    "name": "Elysia-WebScout",
                    "version": "1.0",
                    "role": "external_intelligence",
                    "dependencies": [],
                    "exposed_interfaces": [
                        "create_proposal",
                        "add_research",
                        "add_design",
                        "add_implementation",
                        "get_proposal",
                        "list_proposals"
                    ]
                })
                logger.info("Elysia-WebScout agent initialized and registered")
            except ImportError as e:
                logger.warning(f"WebScout agent not available: {e}")
        
        self.registry = {
            "modules": self.module_architect,
            "mutations": self.mutation_architect,
            "policies": self.policy_architect,
            "persona": self.persona_architect
        }
    
    def get_status_report(self) -> Dict[str, Any]:
        """Get comprehensive status report from all architects"""
        report = {
            "ModuleArchitect": self.module_architect.status_report(),
            "MutationArchitect": self.mutation_architect.status_report(),
            "PolicyArchitect": self.policy_architect.status_report(),
            "PersonaArchitect": self.persona_architect.status_report()
        }
        
        # Add proposal system status
        if self.proposal_system:
            proposals = self.proposal_system.list_proposals()
            report["ProposalSystem"] = {
                "status": "active",
                "proposals_count": len(proposals),
                "proposals_by_status": {
                    status: len([p for p in proposals if p.get("status") == status])
                    for status in ["research", "design", "proposal", "approved", "rejected", "implemented"]
                }
            }
        else:
            report["ProposalSystem"] = {"status": "not_available"}
        
        # Add WebScout status
        report["WebScout"] = self.get_webscout_status()
        
        return report
    
    def route_command(self, target: str, command: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Route a command to the appropriate architect.
        
        Args:
            target: Target architect ("modules", "mutations", "policies", "persona")
            command: Command to execute
            data: Optional data payload
        
        Returns:
            Response dictionary from the architect
        """
        if target not in self.registry:
            return {"status": "error", "message": f"Unknown target '{target}'. Available: {list(self.registry.keys())}"}
        handler = self.registry[target]
        return handler.receive_command(command, data or {})
    
    def register_new_module(self, module_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convenience method to register a new module"""
        return self.module_architect.register_module(module_data)
    
    def get_proposals(self, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get proposals from the proposal system"""
        if self.proposal_system:
            return self.proposal_system.list_proposals(status_filter)
        return []
    
    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific proposal"""
        if self.proposal_system:
            return self.proposal_system.get_proposal(proposal_id)
        return None
    
    def approve_proposal(self, proposal_id: str, approver: str) -> Dict[str, Any]:
        """Approve a proposal"""
        if self.proposal_system:
            return self.proposal_system.lifecycle_manager.approve_proposal(proposal_id, approver)
        return {"status": "error", "message": "Proposal system not available"}
    
    def reject_proposal(self, proposal_id: str, reason: str) -> Dict[str, Any]:
        """Reject a proposal"""
        if self.proposal_system:
            return self.proposal_system.lifecycle_manager.reject_proposal(proposal_id, reason)
        return {"status": "error", "message": "Proposal system not available"}
    
    def create_research_proposal(self, task_description: str, topic: str) -> Dict[str, Any]:
        """Create a new research proposal via WebScout"""
        if not self.webscout:
            return {"status": "error", "message": "WebScout agent not available"}
        
        try:
            proposal_id = self.webscout.create_proposal(task_description, topic)
            logger.info(f"Created research proposal: {proposal_id}")
            return {
                "status": "success",
                "proposal_id": proposal_id,
                "message": f"Research proposal created: {proposal_id}"
            }
        except Exception as e:
            logger.error(f"Failed to create proposal: {e}")
            return {"status": "error", "message": str(e)}
    
    def add_research_to_proposal(self, proposal_id: str, sources: List[Dict[str, Any]], summary: str) -> Dict[str, Any]:
        """Add research findings to a proposal via WebScout"""
        if not self.webscout:
            return {"status": "error", "message": "WebScout agent not available"}
        
        try:
            from project_guardian.webscout_agent import ResearchSource
            research_sources = [
                ResearchSource(
                    url=src.get("url", ""),
                    title=src.get("title", ""),
                    relevance=src.get("relevance", "medium"),
                    extracted_patterns=src.get("extracted_patterns", []),
                    summary=src.get("summary")
                )
                for src in sources
            ]
            self.webscout.add_research(proposal_id, research_sources, summary)
            logger.info(f"Added research to proposal: {proposal_id}")
            return {"status": "success", "proposal_id": proposal_id}
        except Exception as e:
            logger.error(f"Failed to add research: {e}")
            return {"status": "error", "message": str(e)}
    
    def add_design_to_proposal(self, proposal_id: str, architecture: str, integration: str, api_spec: Optional[str] = None) -> Dict[str, Any]:
        """Add design documents to a proposal via WebScout"""
        if not self.webscout:
            return {"status": "error", "message": "WebScout agent not available"}
        
        try:
            self.webscout.add_design(proposal_id, architecture, integration, api_spec)
            # Auto-transition to design phase if in research
            if self.proposal_system:
                proposal = self.proposal_system.get_proposal(proposal_id)
                if proposal and proposal.get("status") == "research":
                    self.proposal_system.lifecycle_manager.transition_to_design(proposal_id)
            logger.info(f"Added design to proposal: {proposal_id}")
            return {"status": "success", "proposal_id": proposal_id}
        except Exception as e:
            logger.error(f"Failed to add design: {e}")
            return {"status": "error", "message": str(e)}
    
    def add_implementation_to_proposal(self, proposal_id: str, todos: List[Dict[str, Any]], patches: Optional[List[str]] = None, tests: Optional[str] = None) -> Dict[str, Any]:
        """Add implementation plan to a proposal via WebScout"""
        if not self.webscout:
            return {"status": "error", "message": "WebScout agent not available"}
        
        try:
            self.webscout.add_implementation(proposal_id, todos, patches, tests)
            # Auto-transition to proposal phase if in design
            if self.proposal_system:
                proposal = self.proposal_system.get_proposal(proposal_id)
                if proposal and proposal.get("status") == "design":
                    self.proposal_system.lifecycle_manager.transition_to_proposal(proposal_id)
            logger.info(f"Added implementation plan to proposal: {proposal_id}")
            return {"status": "success", "proposal_id": proposal_id}
        except Exception as e:
            logger.error(f"Failed to add implementation: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_webscout_status(self) -> Dict[str, Any]:
        """Get WebScout agent status"""
        if not self.webscout:
            return {"status": "not_available", "message": "WebScout agent not initialized"}
        
        proposals = self.webscout.list_proposals()
        return {
            "status": "active",
            "agent_name": self.webscout.agent_name,
            "role": self.webscout.role,
            "proposals_count": len(proposals),
            "proposals": proposals[:5]  # Return last 5 proposals
        }


# Example usage
if __name__ == "__main__":
    architect = ArchitectCore()
    
    # Register a module
    result = architect.register_new_module({
        "name": "TestModule",
        "version": "1.0",
        "role": "testing",
        "exposed_interfaces": ["test_method"]
    })
    print("Module registration:", result)
    
    # Get status
    status = architect.get_status_report()
    print("\nArchitect Status:")
    import json
    print(json.dumps(status, indent=2))
    
    # Route a command
    result = architect.route_command("policies", "update_policy", {
        "name": "trust_threshold",
        "rule": 0.8
    })
    print("\nPolicy update:", result)

