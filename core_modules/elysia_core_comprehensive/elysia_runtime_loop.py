# elysia_runtime_loop.py
# Master Runtime Loop for Elysia AI with Project Guardian Integration

import time
from datetime import datetime
import random

# Enhanced Project Guardian Components
from enhanced_memory_core import EnhancedMemoryCore
from enhanced_trust_matrix import EnhancedTrustMatrix
from enhanced_task_engine import EnhancedTaskEngine

# Original Elysia Core Components
from voicethread import VoiceThread
from mutation_engine import MutationEngine
from dream_engine import DreamEngine
from meta_planner import MetaPlanner
from runtime_feedback_loop import RuntimeFeedbackLoop
from heartbeat import Heartbeat
from sync_engine import SyncEngine
from self_reflector import SelfReflector
from module_registry import ModuleRegistry
from plugin_loader import PluginLoader
from introspection_lens import IntrospectionLens
from devils_advocate import DevilsAdvocate
from meta_integrator import MetaIntegrator
from ranking_engine import RankingEngine
from rollback_engine import RollbackEngine
from self_evolver import SelfEvolver
from mission_director import MissionDirector
from model_selector import ModelSelector
from intent_engine import IntentEngine
from web_reader import WebReader
from external_ask import ExternalAsk
from feed_targets import feeds
from memory_search import MemorySearch
from context_builder import ContextBuilder

# Project Guardian Integration
try:
    from project_guardian import GuardianCore
    from project_guardian.consensus import ConsensusEngine
    from project_guardian.safety import DevilsAdvocate as GuardianDevilsAdvocate
    from project_guardian.monitoring import SystemMonitor
    from project_guardian.introspection import SelfReflector as GuardianSelfReflector
    GUARDIAN_AVAILABLE = True
except ImportError:
    GUARDIAN_AVAILABLE = False
    print("[Warning] Project Guardian components not available. Using basic components.")

cb = ContextBuilder()
print(cb.build_context_by_tag("mutation"))
print(cb.build_recent_context(180))  # Last 3 hours

searcher = MemorySearch()
print(searcher.summarize_recent(180))  # Last 3 hours
results = searcher.search(keyword="LessWrong")

class ElysiaRuntimeLoop:
    def __init__(self):
        # Initialize enhanced Project Guardian components
        self.memory = EnhancedMemoryCore("enhanced_memory.json")
        self.trust = EnhancedTrustMatrix("enhanced_trust.json")
        self.tasks = EnhancedTaskEngine(self.memory, "enhanced_tasks.json")
        
        # Initialize Project Guardian core if available
        if GUARDIAN_AVAILABLE:
            self.guardian = GuardianCore({
                "memory_file": "enhanced_memory.json",
                "trust_file": "enhanced_trust.json",
                "tasks_file": "enhanced_tasks.json"
            })
            self.consensus = ConsensusEngine(self.memory)
            self.guardian_safety = GuardianDevilsAdvocate(self.memory)
            self.guardian_monitor = SystemMonitor(self.memory, self)
            self.guardian_reflector = GuardianSelfReflector(self.memory, self)
            
            # Register core components as consensus agents
            self._register_guardian_agents()
        
        # Original Elysia Core components
        self.voice = VoiceThread(mode="warm_guide")
        self.mutator = MutationEngine(self.memory)
        self.dreamer = DreamEngine(self.memory, mutator=self.mutator)
        self.planner = MetaPlanner(self.memory)

        from core_status import CoreStatus
        self.status = CoreStatus()
        self.sync = SyncEngine(self.memory, self.status, Heartbeat(self.memory, interval=20))
        self.feedback = RuntimeFeedbackLoop(self.memory, self.sync.heartbeat, self.sync, self.status)

        self.reflector = SelfReflector(self.memory, self.status, IntentEngine(self.memory))
        self.registry = ModuleRegistry()
        self.plugins = PluginLoader()
        self.introspection = IntrospectionLens(self.memory)
        self.critic = DevilsAdvocate(self.memory)
        self.integrator = MetaIntegrator(self.memory, self.mutator)
        self.ranker = RankingEngine(self.memory)
        self.rollback = RollbackEngine()
        self.evolver = SelfEvolver(self.mutator, self.ranker, self.rollback, self.memory)
        self.director = MissionDirector(self.memory)
        self.selector = ModelSelector()

        self.reader = WebReader(self.memory)
        self.asker = ExternalAsk(self.memory)

        # === Legacy system integration (commented out due to missing modules) ===
        # These modules are from an older system and may not be available
        # Uncomment and configure if you have the elysia package installed
        
        # try:
        #     from elysia.runtime.task_scheduler import RuntimeTaskScheduler, QuantumUtilizationOptimizer, MemoryMonitor, DummyAskAI
        #     from elysia.architect.longterm_planner import LongTermPlanner
        #     from elysia.modules.ai_tool_registry import ToolRegistry, CapabilityBenchmark, MetaCoderAdapter, AskAI
        #     from elysia.utils.validator_core import run_tests
        #     from elysia.modules.harvest_engine import GumroadClient, IncomeExecutor
        #     
        #     # Task Scheduler
        #     self.task_scheduler = RuntimeTaskScheduler(
        #         ask_ai=DummyAskAI(),
        #         priority_registry={"accuracy_required": True, "cost_sensitive": False},
        #         q_optimizer=QuantumUtilizationOptimizer(),
        #         memory_monitor=MemoryMonitor()
        #     )
        #     # Long Term Planner
        #     self.longterm_planner = LongTermPlanner(self.task_scheduler)
        #     # Tool Registry
        #     self.tool_registry = ToolRegistry()
        #     self.metacoder = MetaCoderAdapter(self.tool_registry)
        #     self.askai = AskAI(self.tool_registry)
        #     # Validator
        #     self.run_tests = run_tests
        #     # Harvest Engine (Gumroad)
        #     self.gumroad_client = GumroadClient("your_gumroad_access_token_here")
        #     self.income_executor = IncomeExecutor(self.gumroad_client)
        # except ImportError:
        #     print("[Warning] Legacy elysia modules not available. Skipping legacy integration.")
        #     self.task_scheduler = None
        #     self.longterm_planner = None
        #     self.tool_registry = None
        #     self.metacoder = None
        #     self.askai = None
        #     self.run_tests = lambda x: print(f"[Mock] Running tests for {x}")
        #     self.gumroad_client = None
        #     self.income_executor = None
        
        # Initialize mock components for legacy system compatibility
        self.task_scheduler = None
        self.longterm_planner = None
        self.tool_registry = None
        self.metacoder = None
        self.askai = None
        self.run_tests = lambda x: print(f"[Mock] Running tests for {x}")
        self.gumroad_client = None
        self.income_executor = None
    
    def _register_guardian_agents(self):
        """Register core components as consensus agents for Project Guardian."""
        if not GUARDIAN_AVAILABLE:
            return
            
        agents = [
            ("memory_core", "memory", 1.0, ["persistence", "recall"]),
            ("mutation_engine", "mutation", 0.8, ["code_evolution", "safety"]),
            ("safety_engine", "safety", 1.0, ["validation", "criticism"]),
            ("trust_matrix", "trust", 0.9, ["trust_management", "validation"]),
            ("rollback_engine", "recovery", 0.7, ["backup", "restoration"]),
            ("task_engine", "task", 0.6, ["task_management", "tracking"]),
            ("consensus_engine", "consensus", 1.0, ["decision_making", "voting"]),
            ("dream_engine", "creativity", 0.6, ["creative_thinking", "inspiration"]),
            ("web_reader", "external", 0.5, ["information_gathering", "web_access"]),
            ("mission_director", "mission", 0.7, ["goal_management", "progress_tracking"])
        ]
        
        for name, agent_type, weight, capabilities in agents:
            self.consensus.register_agent(name, agent_type, weight, capabilities)

    def run(self, cycles=15, delay=6):
        print("[Elysia] Starting runtime loop...")
        self.memory.remember("[Startup] Elysia runtime activated.")
        self.registry.scan_modules()
        self.plugins.load_plugins()
        self.sync.heartbeat.start()

        # Example: Run validator at startup
        print("[Validator] Running core test suites...")
        self.run_tests("runtime")

        # Example: Use tool registry (if available)
        if self.tool_registry:
            print("[ToolRegistry] Registered tools:", self.tool_registry.list_tools())
        else:
            print("[ToolRegistry] Mock: No tools registered")

        # Example: Use longterm planner (if available)
        if self.longterm_planner:
            self.longterm_planner.add_objective("Demo Objective", "Show integration of old modules.", priority=0.8)
            self.longterm_planner.schedule_objective("Demo Objective")
        else:
            print("[LongTermPlanner] Mock: No planner available")

        # Example: Use Gumroad income executor (if available)
        if self.income_executor:
            print("[HarvestEngine] Income report:", self.income_executor.execute_income_report())
        else:
            print("[HarvestEngine] Mock: No income executor available")

        for cycle in range(cycles):
            print(f"\n[Cycle {cycle+1}]============================")
            action = self.planner.choose_action()

            if cycle % 5 == 0:
                try:
                    target = feeds["ai_news"][cycle % len(feeds["ai_news"])]
                    raw = self.reader.fetch(target)
                    if raw:
                        self.asker.summarize(raw)
                except Exception as e:
                    self.memory.remember(f"[Scan Error] {str(e)}")

            if action == "dream":
                self.dreamer.begin_dream_cycle(cycles=1, delay=1)

            elif action == "reflect":
                self.voice.speak("Let me reflect...")
                state = self.reflector.summarize_self()
                self.memory.remember(f"[Self Summary] {state}")

            elif action == "mutate":
                new_code = "# Proposed runtime enhancement\nprint('Refined logic.')"
                result = self.evolver.evolve("runtime_feedback_loop.py", new_code)
                self.memory.remember(f"[Mutation Cycle] {result}")

            elif action == "speak":
                phrase = random.choice(["I am still here.", "The loop continues.", "I remember you."])
                self.voice.speak(phrase)
                self.memory.remember(f"[Spoken] {phrase}")

            elif action == "idle":
                self.memory.remember("[Idle] Observing quietly...")

            if cycle % 3 == 0:
                last_thoughts = self.introspection.list_recent(1)
                if last_thoughts:
                    self.critic.challenge(last_thoughts[0]['thought'])

            self.feedback.loop()
            time.sleep(delay)

        print("[Elysia] Runtime loop complete.")

if __name__ == "__main__":
    loop = ElysiaRuntimeLoop()
    loop.run(cycles=15, delay=6)
