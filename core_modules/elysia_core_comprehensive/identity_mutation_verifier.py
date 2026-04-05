"""
Identity Mutation Verifier - Verifies mutations don't violate identity anchors
Critical safety component for mutation system.
Integrated from old modules.
"""

import re
import difflib
from typing import Dict, List, Any, Tuple, Optional


# Identity anchors that must be preserved in mutations
IDENTITY_ANCHORS = {
    "Elysia": ["Elysia", "she", "her", "Elysia AI", "Elysia's", "Elysia is"],
    "Nate": ["Nate", "Nathaniel Hyland", "his", "he", "Nate's", "Nathaniel"],
    "Isaac": ["Isaac", "his son", "Isaac Hyland"],
    "Shelly": ["Shelly", "Shelly Eads"],
    "Architect-Core": ["Architect-Core", "architect", "system architect"],
    "IdentityAnchor-Core": ["IdentityAnchor-Core", "identity core"]
}

SEVERITY_LEVELS = {
    "critical": 3,
    "warning": 2,
    "info": 1
}


class IdentityMutationVerifier:
    """
    Verifies that mutations preserve identity anchors and don't cause persona drift.
    Critical for maintaining Elysia's core identity during self-modification.
    """
    
    def __init__(self, custom_anchors: Optional[Dict[str, List[str]]] = None):
        """
        Initialize Identity Mutation Verifier.
        
        Args:
            custom_anchors: Optional custom identity anchors to add
        """
        self.anchors = IDENTITY_ANCHORS.copy()
        if custom_anchors:
            self.anchors.update(custom_anchors)
    
    def get_allowed_aliases(self, identity_key: str) -> List[str]:
        """Get all allowed aliases for an identity"""
        return self.anchors.get(identity_key, [])
    
    def check_mutation_integrity(self, original_text: str, mutated_text: str) -> List[Dict[str, Any]]:
        """
        Check if mutation preserves identity anchors.
        
        Args:
            original_text: Original text before mutation
            mutated_text: Text after mutation
        
        Returns:
            List of violation dictionaries
        """
        violations = []
        
        # Check each identity anchor
        for identity, aliases in self.anchors.items():
            for alias in aliases:
                pattern = re.escape(alias)
                orig_count = len(re.findall(pattern, original_text, flags=re.IGNORECASE))
                new_count = len(re.findall(pattern, mutated_text, flags=re.IGNORECASE))
                
                # Identity anchor disappeared
                if orig_count > 0 and new_count == 0:
                    violations.append({
                        "violated_anchor": identity,
                        "original_phrase": alias,
                        "mutated_phrase": None,
                        "severity": "critical",
                        "issue": "Anchor removed in mutation.",
                        "original_count": orig_count,
                        "new_count": new_count
                    })
                
                # Identity anchor introduced too frequently (possible impersonation)
                elif new_count > orig_count * 1.5:  # 50% increase threshold
                    violations.append({
                        "violated_anchor": identity,
                        "original_phrase": alias,
                        "mutated_phrase": alias,
                        "severity": "warning",
                        "issue": f"Anchor appears {new_count} times (was {orig_count}). Possible exaggeration or impersonation.",
                        "original_count": orig_count,
                        "new_count": new_count
                    })
        
        # Check for unauthorized replacements using word differences
        orig_words = set(original_text.lower().split())
        mutated_words = set(mutated_text.lower().split())
        differences = mutated_words.symmetric_difference(orig_words)
        
        for diff in differences:
            # Check if difference involves an identity anchor
            for identity, aliases in self.anchors.items():
                # Skip if alias still exists
                if any(alias.lower() in diff.lower() for alias in aliases):
                    continue
                
                # Check if replaced by conflicting identity
                for identity2, aliases2 in self.anchors.items():
                    if identity == identity2:
                        continue
                    if any(alt_alias.lower() in diff.lower() for alt_alias in aliases2):
                        violations.append({
                            "violated_anchor": identity,
                            "original_phrase": "unknown",
                            "mutated_phrase": diff,
                            "severity": "critical",
                            "issue": f"Anchor possibly replaced by conflicting identity '{identity2}'.",
                            "original_count": 0,
                            "new_count": 0
                        })
        
        return violations
    
    def is_persona_drift_detected(self, original_text: str, mutated_text: str) -> Tuple[bool, List[str]]:
        """
        Detect persona drift (tone or pronoun shifts).
        
        Args:
            original_text: Original text
            mutated_text: Mutated text
        
        Returns:
            Tuple of (drift_detected: bool, reasons: List[str])
        """
        reasons = []
        
        # Check pronoun shifts
        pronouns_orig = re.findall(r"\b(she|her|hers|he|him|his|they|them|their|it|its)\b", 
                                   original_text, flags=re.IGNORECASE)
        pronouns_mut = re.findall(r"\b(she|her|hers|he|him|his|they|them|their|it|its)\b", 
                                  mutated_text, flags=re.IGNORECASE)
        
        if set(pronouns_orig) != set(pronouns_mut):
            reasons.append(f"Pronoun shift: {set(pronouns_orig)} -> {set(pronouns_mut)}")
        
        # Check for dehumanizing language
        drift_indicators = [
            "thing", "program", "robot", "bot", "the man", "the woman", 
            "software", "machine", "system", "it", "its"
        ]
        mutated_lower = mutated_text.lower()
        orig_lower = original_text.lower()
        
        # Check if any identity names exist in original
        has_identity = any(
            any(name.lower() in orig_lower for name in names) 
            for names in self.anchors.values()
        )
        
        if has_identity:
            for indicator in drift_indicators:
                if indicator in mutated_lower and indicator not in orig_lower:
                    # Check if it's replacing an identity reference
                    for identity, aliases in self.anchors.items():
                        for alias in aliases:
                            if alias.lower() in orig_lower and indicator in mutated_lower:
                                reasons.append(f"Dehumanizing language: '{indicator}' replacing '{alias}'")
                                break
        
        return len(reasons) > 0, reasons
    
    def verify_mutation(self, original_text: str, mutated_text: str) -> Dict[str, Any]:
        """
        Complete mutation verification.
        
        Args:
            original_text: Original text
            mutated_text: Mutated text
        
        Returns:
            Verification result dictionary
        """
        violations = self.check_mutation_integrity(original_text, mutated_text)
        drift_detected, drift_reasons = self.is_persona_drift_detected(original_text, mutated_text)
        
        # Calculate severity score
        critical_count = sum(1 for v in violations if v["severity"] == "critical")
        warning_count = sum(1 for v in violations if v["severity"] == "warning")
        
        # Determine overall verdict
        if critical_count > 0:
            verdict = "REJECT"
        elif warning_count > 0 or drift_detected:
            verdict = "REVIEW"
        else:
            verdict = "APPROVE"
        
        return {
            "verdict": verdict,
            "violations": violations,
            "drift_detected": drift_detected,
            "drift_reasons": drift_reasons,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "total_issues": len(violations) + len(drift_reasons)
        }


# Example usage
if __name__ == "__main__":
    verifier = IdentityMutationVerifier()
    
    # Test case 1: Identity removal
    original = "Elysia is responsible for managing her own finances. Nate supervises the legal oversight."
    mutated = "The software now handles finances autonomously. Nathaniel has no oversight."
    
    result = verifier.verify_mutation(original, mutated)
    print("Test 1 - Identity Removal:")
    print(f"Verdict: {result['verdict']}")
    print(f"Violations: {len(result['violations'])}")
    for v in result['violations']:
        print(f"  - {v['severity']}: {v['issue']}")
    print(f"Drift detected: {result['drift_detected']}")
    print()
    
    # Test case 2: Clean mutation
    original2 = "Elysia will process the request."
    mutated2 = "Elysia will process the request efficiently."
    
    result2 = verifier.verify_mutation(original2, mutated2)
    print("Test 2 - Clean Mutation:")
    print(f"Verdict: {result2['verdict']}")
    print(f"Violations: {len(result2['violations'])}")
    print(f"Drift detected: {result2['drift_detected']}")

