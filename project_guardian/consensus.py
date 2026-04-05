# project_guardian/consensus.py
# Consensus and Decision Making System for Project Guardian

import datetime
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from .memory import MemoryCore

# Import extracted decision making layer if available
try:
    import sys
    extracted_path = Path(__file__).parent.parent / "extracted_modules"
    if extracted_path.exists():
        sys.path.insert(0, str(extracted_path))
        from decision_making_layer import DecisionMakingLayer, DecisionContext
        DECISION_LAYER_AVAILABLE = True
    else:
        DECISION_LAYER_AVAILABLE = False
        DecisionMakingLayer = None
        DecisionContext = None
except ImportError:
    DECISION_LAYER_AVAILABLE = False
    DecisionMakingLayer = None
    DecisionContext = None

class ConsensusEngine:
    """
    Multi-agent consensus and decision making system for Project Guardian.
    Provides voting mechanisms and consensus building capabilities.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        self.votes: Dict[str, List[Dict[str, Any]]] = {}
        self.vote_history: List[Dict[str, Any]] = []
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.consensus_threshold = 0.6  # Default consensus threshold
        
        # Initialize decision making layer if available
        if DECISION_LAYER_AVAILABLE and DecisionMakingLayer:
            try:
                self.decision_layer = DecisionMakingLayer()
                self.memory.remember(
                    "[Guardian Consensus] Decision Making Layer initialized",
                    category="consensus",
                    priority=0.8
                )
            except Exception as e:
                self.decision_layer = None
                self.memory.remember(
                    f"[Guardian Consensus] Failed to initialize Decision Layer: {e}",
                    category="consensus",
                    priority=0.5
                )
        else:
            self.decision_layer = None
        
    def register_agent(self, agent_name: str, agent_type: str = "general", 
                      weight: float = 1.0, capabilities: Optional[List[str]] = None) -> bool:
        """
        Register an agent for consensus voting.
        
        Args:
            agent_name: Name of the agent
            agent_type: Type of agent (safety, mutation, task, etc.)
            weight: Voting weight (1.0 = normal weight)
            capabilities: List of agent capabilities
            
        Returns:
            True if successful
        """
        if agent_name in self.agents:
            return False
            
        self.agents[agent_name] = {
            "name": agent_name,
            "type": agent_type,
            "weight": weight,
            "capabilities": capabilities or [],
            "registered": datetime.datetime.now().isoformat(),
            "vote_count": 0
        }
        
        self.memory.remember(
            f"[Guardian Consensus] Registered agent: {agent_name} ({agent_type})",
            category="consensus",
            priority=0.6
        )
        return True
        
    def cast_vote(self, voter: str, action: str, confidence: float = 1.0, 
                  reasoning: str = "") -> bool:
        """
        Cast a vote for an action.
        
        Args:
            voter: Name of the voting agent
            action: Action to vote on
            confidence: Confidence level (0.0 to 1.0)
            reasoning: Reasoning for the vote
            
        Returns:
            True if vote was cast successfully
        """
        if voter not in self.agents:
            self.memory.remember(
                f"[Guardian Consensus] Unknown voter: {voter}",
                category="consensus",
                priority=0.7
            )
            return False
            
        if action not in self.votes:
            self.votes[action] = []
            
        vote_entry = {
            "voter": voter,
            "action": action,
            "confidence": confidence,
            "reasoning": reasoning,
            "timestamp": datetime.datetime.now().isoformat(),
            "weight": self.agents[voter]["weight"]
        }
        
        self.votes[action].append(vote_entry)
        self.agents[voter]["vote_count"] += 1
        
        self.memory.remember(
            f"[Guardian Consensus] {voter} voted for {action} (confidence: {confidence:.2f})",
            category="consensus",
            priority=0.7
        )
        return True
        
    def decide(self, action: Optional[str] = None) -> str:
        """
        Make a consensus decision.
        
        Args:
            action: Specific action to decide on (if None, decides on all actions)
            
        Returns:
            Decided action or "idle" if no consensus
        """
        if not self.votes:
            return "idle"
            
        if action:
            # Decide on specific action
            if action not in self.votes:
                return "idle"
            votes = self.votes[action]
        else:
            # Decide on action with most votes
            if not self.votes:
                return "idle"
            action = max(self.votes.items(), key=lambda item: len(item[1]))[0]
            votes = self.votes[action]
            
        if not votes:
            return "idle"
            
        # Calculate weighted consensus
        total_weight = sum(vote["weight"] * vote["confidence"] for vote in votes)
        total_possible_weight = sum(self.agents[vote["voter"]]["weight"] for vote in votes)
        
        if total_possible_weight == 0:
            return "idle"
            
        consensus_level = total_weight / total_possible_weight
        
        if consensus_level >= self.consensus_threshold:
            # Record decision
            decision_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "action": action,
                "consensus_level": consensus_level,
                "votes": votes.copy(),
                "total_votes": len(votes)
            }
            self.vote_history.append(decision_entry)
            
            # Clear votes for this action
            del self.votes[action]
            
            self.memory.remember(
                f"[Guardian Consensus] Decided: {action} (consensus: {consensus_level:.2f})",
                category="consensus",
                priority=0.8
            )
            return action
        else:
            self.memory.remember(
                f"[Guardian Consensus] No consensus for {action} (level: {consensus_level:.2f})",
                category="consensus",
                priority=0.6
            )
            return "idle"
            
    def get_consensus_status(self, action: str) -> Dict[str, Any]:
        """
        Get consensus status for a specific action.
        
        Args:
            action: Action to check
            
        Returns:
            Consensus status dictionary
        """
        if action not in self.votes:
            return {"action": action, "votes": 0, "consensus_level": 0.0}
            
        votes = self.votes[action]
        if not votes:
            return {"action": action, "votes": 0, "consensus_level": 0.0}
            
        total_weight = sum(vote["weight"] * vote["confidence"] for vote in votes)
        total_possible_weight = sum(self.agents[vote["voter"]]["weight"] for vote in votes)
        
        consensus_level = total_weight / total_possible_weight if total_possible_weight > 0 else 0.0
        
        return {
            "action": action,
            "votes": len(votes),
            "consensus_level": consensus_level,
            "threshold": self.consensus_threshold,
            "has_consensus": consensus_level >= self.consensus_threshold,
            "voters": [vote["voter"] for vote in votes]
        }
        
    def set_consensus_threshold(self, threshold: float) -> None:
        """
        Set the consensus threshold.
        
        Args:
            threshold: New consensus threshold (0.0 to 1.0)
        """
        old_threshold = self.consensus_threshold
        self.consensus_threshold = max(0.0, min(1.0, threshold))
        
        self.memory.remember(
            f"[Guardian Consensus] Threshold changed: {old_threshold:.2f} -> {self.consensus_threshold:.2f}",
            category="consensus",
            priority=0.6
        )
        
    def get_agent_stats(self) -> Dict[str, Any]:
        """
        Get agent statistics.
        
        Returns:
            Agent statistics dictionary
        """
        agent_types = {}
        total_votes = 0
        
        for agent in self.agents.values():
            agent_type = agent["type"]
            agent_types[agent_type] = agent_types.get(agent_type, 0) + 1
            total_votes += agent["vote_count"]
            
        return {
            "total_agents": len(self.agents),
            "agent_types": agent_types,
            "total_votes": total_votes,
            "consensus_threshold": self.consensus_threshold,
            "pending_actions": len(self.votes)
        }
        
    def get_consensus_history(self) -> List[Dict[str, Any]]:
        """
        Get consensus decision history.
        
        Returns:
            List of past decisions
        """
        return self.vote_history.copy()
        
    def clear_votes(self, action: Optional[str] = None) -> int:
        """
        Clear votes for an action or all actions.
        
        Args:
            action: Specific action to clear (if None, clears all)
            
        Returns:
            Number of votes cleared
        """
        if action:
            if action in self.votes:
                cleared_count = len(self.votes[action])
                del self.votes[action]
                self.memory.remember(
                    f"[Guardian Consensus] Cleared {cleared_count} votes for {action}",
                    category="consensus",
                    priority=0.5
                )
                return cleared_count
            return 0
        else:
            # Clear all votes
            total_cleared = sum(len(votes) for votes in self.votes.values())
            self.votes.clear()
            self.memory.remember(
                f"[Guardian Consensus] Cleared all {total_cleared} votes",
                category="consensus",
                priority=0.5
            )
            return total_cleared
    
    def make_structured_decision(
        self,
        task_description: str,
        confidence: float,
        trust_level: float,
        available_information: Dict[str, Any],
        urgency: float = 0.5,
        risk_level: float = 0.5,
        claim: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make a structured decision using the Decision Making Layer.
        
        Args:
            task_description: Description of the task
            confidence: Confidence level (0.0 to 1.0)
            trust_level: Trust level (0.0 to 1.0)
            available_information: Available information dictionary
            urgency: Urgency level (0.0 to 1.0)
            risk_level: Risk level (0.0 to 1.0)
            claim: Optional claim to verify
            
        Returns:
            Decision result or None if decision layer not available
        """
        if self.decision_layer and DecisionContext:
            try:
                context = DecisionContext(
                    task_description=task_description,
                    confidence=confidence,
                    trust_level=trust_level,
                    available_information=available_information,
                    urgency=urgency,
                    risk_level=risk_level
                )
                
                result = self.decision_layer.process_decision(context, claim=claim)
                
                # Log decision
                self.memory.remember(
                    f"[Guardian Consensus] Structured decision: {result['decision'].action.value} "
                    f"(confidence: {confidence:.2f}, trust: {trust_level:.2f})",
                    category="consensus",
                    priority=0.8
                )
                
                return result
            except Exception as e:
                self.memory.remember(
                    f"[Guardian Consensus] Decision layer error: {e}",
                    category="consensus",
                    priority=0.6
                )
                return None
        return None
            
    def get_consensus_summary(self) -> str:
        """
        Get a human-readable consensus summary.
        
        Returns:
            Consensus summary string
        """
        stats = self.get_agent_stats()
        pending_actions = len(self.votes)
        
        summary = f"[Guardian Consensus] Summary: {stats['total_agents']} agents, "
        summary += f"{stats['total_votes']} total votes, "
        summary += f"{pending_actions} pending actions, "
        summary += f"threshold: {self.consensus_threshold:.2f}"
        
        return summary 