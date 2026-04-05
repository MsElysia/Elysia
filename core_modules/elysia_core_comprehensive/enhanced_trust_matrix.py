# enhanced_trust_matrix.py
# Enhanced Trust Matrix with Project Guardian features

import datetime
import json
import os
from typing import Dict, List, Optional, Any

class EnhancedTrustMatrix:
    def __init__(self, trust_file="trust_matrix.json"):
        self.trust = {}
        self.trust_file = trust_file
        self.trust_history = {}
        self.decay_rate = 0.01
        self.load()

    def update_trust(self, name, delta, reason="", action_type="general"):
        """
        Enhanced trust update with reason tracking and action types
        Maintains backward compatibility with original update_trust()
        """
        if name not in self.trust:
            self.trust[name] = 0.5
        
        old_trust = self.trust[name]
        self.trust[name] = max(0.0, min(1.0, self.trust[name] + delta))
        
        # Track trust history
        if name not in self.trust_history:
            self.trust_history[name] = []
        
        history_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "old_trust": old_trust,
            "new_trust": self.trust[name],
            "delta": delta,
            "reason": reason,
            "action_type": action_type
        }
        self.trust_history[name].append(history_entry)
        
        self._save()
        print(f"[Trust] {name}: {old_trust:.2f} → {self.trust[name]:.2f} ({delta:+.2f}) - {reason}")
        return self.trust[name]

    def get_trust(self, name):
        return self.trust.get(name, 0.5)

    def get_trust_stats(self) -> Dict[str, Any]:
        """Get comprehensive trust statistics"""
        if not self.trust:
            return {
                "total_components": 0,
                "average_trust": 0.5,
                "high_trust_components": 0,
                "low_trust_components": 0,
                "trust_range": {"min": 0.0, "max": 1.0}
            }
        
        trusts = list(self.trust.values())
        stats = {
            "total_components": len(self.trust),
            "average_trust": sum(trusts) / len(trusts),
            "high_trust_components": len([t for t in trusts if t >= 0.7]),
            "low_trust_components": len([t for t in trusts if t <= 0.3]),
            "trust_range": {"min": min(trusts), "max": max(trusts)}
        }
        return stats

    def validate_trust_for_action(self, component: str, action: str, required_trust: float = 0.5) -> bool:
        """Validate if component has sufficient trust for specific action"""
        current_trust = self.get_trust(component)
        is_valid = current_trust >= required_trust
        
        if not is_valid:
            print(f"[Trust] {component} trust ({current_trust:.2f}) insufficient for {action} (requires {required_trust:.2f})")
        
        return is_valid

    def get_trust_history(self, component: str, hours: int = 24) -> List[Dict]:
        """Get trust history for a component within specified hours"""
        if component not in self.trust_history:
            return []
        
        cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
        recent_history = []
        
        for entry in self.trust_history[component]:
            entry_time = datetime.datetime.fromisoformat(entry["timestamp"])
            if entry_time > cutoff:
                recent_history.append(entry)
        
        return recent_history

    def get_components_by_trust_level(self, min_trust: float = 0.0, max_trust: float = 1.0) -> List[str]:
        """Get components within specified trust range"""
        return [
            component for component, trust in self.trust.items()
            if min_trust <= trust <= max_trust
        ]

    def decay_all(self, amount=None):
        """Enhanced decay with configurable amount"""
        decay_amount = amount if amount is not None else self.decay_rate
        
        for component in self.trust:
            old_trust = self.trust[component]
            self.trust[component] = max(0.0, self.trust[component] - decay_amount)
            
            # Track decay in history
            if component not in self.trust_history:
                self.trust_history[component] = []
            
            history_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "old_trust": old_trust,
                "new_trust": self.trust[component],
                "delta": -decay_amount,
                "reason": "Automatic trust decay",
                "action_type": "decay"
            }
            self.trust_history[component].append(history_entry)
        
        self._save()
        print(f"[Trust] Applied decay of {decay_amount:.3f} to all components")

    def set_decay_rate(self, rate: float):
        """Set the automatic decay rate"""
        self.decay_rate = max(0.0, min(1.0, rate))
        print(f"[Trust] Decay rate set to {self.decay_rate:.3f}")

    def get_low_trust_warnings(self, threshold: float = 0.3) -> List[str]:
        """Get warnings for components with low trust"""
        warnings = []
        for component, trust in self.trust.items():
            if trust <= threshold:
                warnings.append(f"{component}: {trust:.2f}")
        return warnings

    def _save(self):
        """Save trust data to file"""
        data = {
            "trust": self.trust,
            "trust_history": self.trust_history,
            "decay_rate": self.decay_rate,
            "last_updated": datetime.datetime.now().isoformat()
        }
        
        try:
            with open(self.trust_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Trust] Save failed: {e}")

    def load(self):
        """Load trust data from file"""
        if os.path.exists(self.trust_file):
            try:
                with open(self.trust_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                self.trust = data.get("trust", {})
                self.trust_history = data.get("trust_history", {})
                self.decay_rate = data.get("decay_rate", 0.01)
                
                print(f"[Trust] Loaded trust data for {len(self.trust)} components")
            except Exception as e:
                print(f"[Trust] Load failed: {e}")

# Backward compatibility alias
TrustMatrix = EnhancedTrustMatrix 