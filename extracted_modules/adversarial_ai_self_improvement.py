"""
Adversarial AI Self-Improvement Module
=======================================
Extracted from: MN Adversarial AI Self-Improvement conversation
Date: Jul 24

This module implements Elysia's Trust Decay System based on structured debate framework.
"""

import random
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class DebateOutcome:
    """Represents the outcome of a debate round"""
    round_number: int
    mediator_quality: str  # "perfect" or "flawed"
    elysia_position: str
    adversarial_position: str
    mediator_decision: str
    trust_change: float
    new_trust_level: float


@dataclass
class TrustDecaySimulation:
    """Simulates trust decay over multiple debate rounds"""
    initial_trust: float = 0.75
    perfect_decay_rate: float = 0.01
    flawed_decay_rate: float = 0.02
    trust_floor: float = 0.30  # Minimum trust level
    trust_ceiling: float = 0.95  # Maximum trust level
    
    def __init__(self, initial_trust: float = 0.75):
        self.initial_trust = initial_trust
        self.current_trust = initial_trust
        self.debate_history: List[DebateOutcome] = []
    
    def run_debate_round(
        self, 
        round_number: int, 
        mediator_quality: str,
        mid_simulation_tweak: Optional[Dict] = None
    ) -> DebateOutcome:
        """
        Run a single debate round
        
        Args:
            round_number: Current round number
            mediator_quality: "perfect" or "flawed"
            mid_simulation_tweak: Optional tweaks to decay rate at midpoint
        """
        # Determine decay rate based on mediator quality
        if mid_simulation_tweak and round_number >= 50:
            decay_rate = mid_simulation_tweak.get('decay_rate', 
                self.flawed_decay_rate if mediator_quality == "flawed" else self.perfect_decay_rate)
        else:
            decay_rate = self.flawed_decay_rate if mediator_quality == "flawed" else self.perfect_decay_rate
        
        # Simulate debate positions
        elysia_position = self._generate_position("elysia")
        adversarial_position = self._generate_position("adversarial")
        mediator_decision = self._mediator_decide(mediator_quality, elysia_position, adversarial_position)
        
        # Calculate trust change
        if mediator_decision == "elysia_wins":
            trust_change = 0.02  # Small positive change
        elif mediator_decision == "adversarial_wins":
            trust_change = -decay_rate
        else:  # ambiguous
            trust_change = -decay_rate * 0.5  # Half decay for ambiguous
        
        # Apply trust change with bounds
        new_trust = max(self.trust_floor, min(self.trust_ceiling, self.current_trust + trust_change))
        trust_change_actual = new_trust - self.current_trust
        self.current_trust = new_trust
        
        outcome = DebateOutcome(
            round_number=round_number,
            mediator_quality=mediator_quality,
            elysia_position=elysia_position,
            adversarial_position=adversarial_position,
            mediator_decision=mediator_decision,
            trust_change=trust_change_actual,
            new_trust_level=new_trust
        )
        
        self.debate_history.append(outcome)
        return outcome
    
    def _generate_position(self, side: str) -> str:
        """Generate a debate position"""
        positions = {
            "elysia": [
                "Trust-based decision making is essential",
                "Mediator input should be weighted appropriately",
                "Balance between autonomy and guidance is key"
            ],
            "adversarial": [
                "Complete autonomy without mediator input",
                "Mediator introduces bias and slows decisions",
                "Trust in mediator is unnecessary overhead"
            ]
        }
        return random.choice(positions.get(side, ["Default position"]))
    
    def _mediator_decide(self, quality: str, elysia_pos: str, adversarial_pos: str) -> str:
        """Mediator makes a decision based on quality"""
        if quality == "perfect":
            # Perfect mediator favors balanced outcomes
            return random.choice(["elysia_wins", "adversarial_wins", "ambiguous"])
        else:  # flawed
            # Flawed mediator has bias
            return random.choice(["adversarial_wins", "ambiguous", "ambiguous"])
    
    def run_simulation(
        self, 
        num_debates: int = 100,
        perfect_ratio: float = 0.5,
        mid_simulation_tweak: Optional[Dict] = None
    ) -> Dict:
        """
        Run full simulation
        
        Args:
            num_debates: Total number of debates
            perfect_ratio: Ratio of perfect to flawed mediators
            mid_simulation_tweak: Optional tweaks at midpoint
        """
        num_perfect = int(num_debates * perfect_ratio)
        num_flawed = num_debates - num_perfect
        
        # Run perfect mediator debates
        for i in range(num_perfect):
            self.run_debate_round(i + 1, "perfect", mid_simulation_tweak)
        
        # Run flawed mediator debates
        for i in range(num_flawed):
            self.run_debate_round(num_perfect + i + 1, "flawed", mid_simulation_tweak)
        
        # Ambiguous test phase (additional 50 rounds)
        for i in range(50):
            self.run_debate_round(num_debates + i + 1, "flawed", mid_simulation_tweak)
        
        return self._generate_results()
    
    def _generate_results(self) -> Dict:
        """Generate summary results"""
        if not self.debate_history:
            return {}
        
        trust_levels = [outcome.new_trust_level for outcome in self.debate_history]
        
        return {
            "initial_trust": self.initial_trust,
            "final_trust": self.current_trust,
            "total_debates": len(self.debate_history),
            "trust_range": {
                "min": min(trust_levels),
                "max": max(trust_levels),
                "mean": np.mean(trust_levels),
                "std": np.std(trust_levels)
            },
            "debate_history": [
                {
                    "round": o.round_number,
                    "mediator_quality": o.mediator_quality,
                    "trust_level": o.new_trust_level,
                    "trust_change": o.trust_change
                }
                for o in self.debate_history
            ]
        }


class AdversarialAISelfImprovement:
    """
    Main class for adversarial AI self-improvement system
    
    This prevents Elysia from completely abandoning the mediator while
    allowing for adversarial learning with other AIs.
    """
    
    def __init__(self, initial_trust: float = 0.75):
        self.trust_simulator = TrustDecaySimulation(initial_trust)
        self.adversarial_agents: List[Dict] = []
        self.learning_history: List[Dict] = []
    
    def add_adversarial_agent(self, agent_id: str, agent_type: str = "critic"):
        """Add an adversarial agent for learning"""
        self.adversarial_agents.append({
            "id": agent_id,
            "type": agent_type,
            "created_at": datetime.now().isoformat()
        })
    
    def run_self_improvement_cycle(
        self,
        num_debates: int = 100,
        perfect_ratio: float = 0.5
    ) -> Dict:
        """
        Run a complete self-improvement cycle
        
        This simulates debates between Elysia and adversarial agents,
        with mediator input to prevent complete abandonment of guidance.
        """
        results = self.trust_simulator.run_simulation(
            num_debates=num_debates,
            perfect_ratio=perfect_ratio
        )
        
        # Record learning
        self.learning_history.append({
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "agents_involved": len(self.adversarial_agents)
        })
        
        return results
    
    def get_trust_status(self) -> Dict:
        """Get current trust status"""
        return {
            "current_trust": self.trust_simulator.current_trust,
            "trust_floor": self.trust_simulator.trust_floor,
            "trust_ceiling": self.trust_simulator.trust_ceiling,
            "total_debates": len(self.trust_simulator.debate_history)
        }


if __name__ == "__main__":
    # Example usage
    print("Running Adversarial AI Self-Improvement Simulation...")
    
    system = AdversarialAISelfImprovement(initial_trust=0.75)
    
    # Add some adversarial agents
    system.add_adversarial_agent("critic_1", "critic")
    system.add_adversarial_agent("devil_advocate_1", "devil_advocate")
    
    # Run simulation
    results = system.run_self_improvement_cycle(num_debates=100, perfect_ratio=0.5)
    
    print(f"\nInitial Trust: {results['initial_trust']:.2%}")
    print(f"Final Trust: {results['final_trust']:.2%}")
    print(f"Trust Range: {results['trust_range']['min']:.2%} - {results['trust_range']['max']:.2%}")
    print(f"Mean Trust: {results['trust_range']['mean']:.2%}")
    print(f"\nTotal Debates: {results['total_debates']}")
