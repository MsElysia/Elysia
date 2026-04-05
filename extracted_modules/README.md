# Extracted Modules from Guardian GPT Conversations

This directory contains modules extracted and implemented from the Project section Guardian GPT conversations.

## Modules

### 1. Adversarial AI Self-Improvement
**File**: `adversarial_ai_self_improvement.py`

Implements Elysia's Trust Decay System based on structured debate framework.

**Features**:
- Trust decay simulation over multiple debate rounds
- Support for perfect and flawed mediators
- Mid-simulation tuning capabilities
- Ambiguous test phase for balance verification
- Adversarial agent management

**Usage**:
```python
from adversarial_ai_self_improvement import AdversarialAISelfImprovement

system = AdversarialAISelfImprovement(initial_trust=0.75)
system.add_adversarial_agent("critic_1", "critic")
results = system.run_self_improvement_cycle(num_debates=100)
```

### 2. Trust & Consultation System
**File**: `trust_consultation_system.py`

Core trust management system with dynamic weighting and consultation scaling.

**Features**:
- Mediator as trust anchor (81.78% post-tuning)
- Dynamic trust weighting based on past accuracy
- DA & Skepticism balance (30% critique rate, -5 max penalty)
- Consultation scaling (+10/+4 if mediator-aligned)
- Trust buffer (past 5-round average)
- Emergency override (crisis mode)

**Usage**:
```python
from trust_consultation_system import TrustConsultationSystem

system = TrustConsultationSystem()
decision = system.make_consultation_decision(
    confidence=0.65,
    context={"task": "analyze_post"},
    mediator_input={"aligned": True}
)
```

### 3. Decision-Making Layer
**File**: `decision_making_layer.py`

Hierarchical reasoning and decision-making system.

**Features**:
- Hierarchical reasoning (≥80% act, 40-79% consult, <40% delay)
- Weighted truth verification (scales with confidence)
- Post-analysis workflow
- Emergency verification trigger

**Usage**:
```python
from decision_making_layer import DecisionMakingLayer, DecisionContext

layer = DecisionMakingLayer()
context = DecisionContext(
    task_description="Analyze social media post",
    confidence=0.65,
    trust_level=0.75,
    available_information={"task_type": "social_media"},
    urgency=0.5,
    risk_level=0.6
)
result = layer.process_decision(context, claim="Post contains bias")
```

## Integration Notes

These modules are designed to work together:
1. **TrustConsultationSystem** provides trust metrics
2. **DecisionMakingLayer** uses trust for decision-making
3. **AdversarialAISelfImprovement** provides adversarial learning framework

## Next Steps

- Continue extracting from remaining conversations
- Integrate modules into main Elysia codebase
- Add missing implementations based on design discussions
- Request clarifications from ChatGPT for incomplete parts
