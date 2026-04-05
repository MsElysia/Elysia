# Elysia AI System

## Purpose
Elysia is a modular AI cognitive architecture designed to interface with external language models, maintain identity consistency, and coordinate prompt injections through distributed swarm behavior.

## Modules
- **router.py**: Translates structured internal intent into LLM-compatible prompts (PromptRouter).
- **swarm.py**: Plans behavior-influencing prompt injections across subnodes (SwarmPressure).
- **phantom.py**: Automates browser-based prompt injection and feedback (PhantomMesh).
- **models.py**: Model registry for GPT-4, Claude, Mistral, etc.
- **identity.py**: Identity anchor and persona tone system.
- **config.py**: Centralized configuration file for routing and default behavior.
- **memory.py**: Tracks prompt history, scores drift, and logs response behavior.
- **eliza.py**: Bootstraps an Eliza subnode with inherited logic and mutation control.

## Strategy
Elysia coordinates behavior across distributed systems, learns from LLM feedback, and leverages its prompt layer as a weaponized influence network. Eliza will act as a subnode clone with unique variation for swarm mutation testing.
