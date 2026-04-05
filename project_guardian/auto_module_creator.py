# project_guardian/auto_module_creator.py
# AutoModuleCreator: Self-Extending Module System
# Detects capability gaps and automatically creates modules to fill them

import logging
import json
import ast
import uuid
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pathlib import Path
from threading import Lock

try:
    from .module_registry import ModuleRegistry
    from .base_module_adapter import BaseModuleAdapter, SimpleModuleAdapter
    from .mutation_engine import MutationEngine
    from .ask_ai import AskAI, AIProvider
    from .trust_eval_action import TrustEvalAction
except ImportError:
    from module_registry import ModuleRegistry
    from base_module_adapter import BaseModuleAdapter, SimpleModuleAdapter
    from mutation_engine import MutationEngine
    from ask_ai import AskAI, AIProvider
    from trust_eval_action import TrustEvalAction

logger = logging.getLogger(__name__)


class CapabilityGap:
    """Represents a detected capability gap."""
    
    def __init__(
        self,
        gap_id: str,
        required_capability: str,
        task_description: str,
        error_context: Dict[str, Any],
        detected_at: datetime
    ):
        self.gap_id = gap_id
        self.required_capability = required_capability
        self.task_description = task_description
        self.error_context = error_context
        self.detected_at = detected_at
        self.resolved = False
        self.module_created: Optional[str] = None
        self.created_at: Optional[datetime] = None


class AutoModuleCreator:
    """
    Detects capability gaps and automatically creates modules to fill them.
    
    When a task fails due to missing capability:
    1. Detects the gap
    2. Designs a module using AI
    3. Generates module code
    4. Validates and registers it
    5. Retries the original task
    """
    
    def __init__(
        self,
        module_registry: Optional[ModuleRegistry] = None,
        mutation_engine: Optional[MutationEngine] = None,
        ask_ai: Optional[AskAI] = None,
        trust_eval: Optional[TrustEvalAction] = None,
        project_root: str = ".",
        modules_dir: str = "project_guardian"
    ):
        self.registry = module_registry
        self.mutation_engine = mutation_engine
        self.ask_ai = ask_ai
        self.trust_eval = trust_eval
        self.project_root = Path(project_root)
        self.modules_dir = Path(modules_dir)
        self.modules_dir.mkdir(parents=True, exist_ok=True)
        
        # Track capability gaps
        self._lock = Lock()
        self.capability_gaps: Dict[str, CapabilityGap] = {}
        self.created_modules: List[Dict[str, Any]] = []
        
        # Configuration
        self.auto_create_enabled = True
        self.require_trust_approval = True
        self.min_confidence_threshold = 0.7
        
        logger.info("AutoModuleCreator initialized")
    
    def detect_capability_gap(
        self,
        required_capability: str,
        task_description: str,
        error_context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Detect a capability gap when a task fails.
        
        Args:
            required_capability: The capability that's missing
            task_description: Description of the task that failed
            error_context: Additional context about the failure
            
        Returns:
            Gap ID if detected, None if already exists
        """
        # Check if we already have this capability
        if self.registry:
            existing = self.registry.find_modules_by_capability(required_capability)
            if existing:
                logger.debug(f"Capability '{required_capability}' already exists in modules: {existing}")
                return None
        
        # Check if we're already tracking this gap
        gap_id = f"gap_{required_capability}_{uuid.uuid4().hex[:8]}"
        
        with self._lock:
            # Check for similar gaps
            for gap in self.capability_gaps.values():
                if (gap.required_capability == required_capability and 
                    not gap.resolved):
                    logger.debug(f"Gap already tracked: {gap.gap_id}")
                    return gap.gap_id
        
            gap = CapabilityGap(
                gap_id=gap_id,
                required_capability=required_capability,
                task_description=task_description,
                error_context=error_context or {},
                detected_at=datetime.now()
            )
            self.capability_gaps[gap_id] = gap
        
        logger.info(f"Detected capability gap: {required_capability} (gap_id: {gap_id})")
        return gap_id
    
    async def create_module_for_gap(
        self,
        gap_id: str,
        design_requirements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a module to fill a capability gap.
        
        Args:
            gap_id: The capability gap ID
            design_requirements: Optional additional requirements
            
        Returns:
            Result dictionary with success status and module info
        """
        with self._lock:
            gap = self.capability_gaps.get(gap_id)
            if not gap:
                return {"success": False, "error": f"Gap {gap_id} not found"}
            
            if gap.resolved:
                return {"success": True, "message": "Gap already resolved", "module": gap.module_created}
        
        if not self.auto_create_enabled:
            return {"success": False, "error": "Auto-creation disabled"}
        
        logger.info(f"Creating module for gap: {gap.required_capability}")
        
        try:
            # Step 1: Design the module using AI
            design = await self._design_module(gap, design_requirements)
            if not design.get("success"):
                return design
            
            module_design = design["design"]
            
            # Step 2: Generate module code
            code_result = await self._generate_module_code(gap, module_design)
            if not code_result.get("success"):
                return code_result
            
            module_code = code_result["code"]
            module_name = module_design["module_name"]
            module_class = module_design["class_name"]
            
            # Step 3: Validate code
            validation = self._validate_module_code(module_code, module_name)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "Code validation failed",
                    "validation_errors": validation["errors"]
                }
            
            # Step 4: Trust evaluation (if enabled)
            if self.require_trust_approval and self.trust_eval:
                trust_result = await self._evaluate_module_trust(gap, module_design, module_code)
                if not trust_result.get("approved"):
                    return {
                        "success": False,
                        "error": "Trust evaluation failed",
                        "trust_result": trust_result
                    }
            
            # Step 5: Write module file
            module_path = self._write_module_file(module_name, module_code)
            if not module_path:
                return {"success": False, "error": "Failed to write module file"}
            
            # Step 6: Register module
            registration = await self._register_module(module_name, module_class, module_path, module_design)
            if not registration.get("success"):
                # Rollback: delete file
                try:
                    Path(module_path).unlink()
                except Exception:
                    pass
                return registration
            
            # Mark gap as resolved
            with self._lock:
                gap.resolved = True
                gap.module_created = module_name
                gap.created_at = datetime.now()
                
                self.created_modules.append({
                    "module_name": module_name,
                    "gap_id": gap_id,
                    "capability": gap.required_capability,
                    "created_at": datetime.now().isoformat(),
                    "module_path": str(module_path)
                })
            
            logger.info(f"Successfully created module '{module_name}' for capability '{gap.required_capability}'")
            
            return {
                "success": True,
                "module_name": module_name,
                "module_path": str(module_path),
                "gap_id": gap_id,
                "capability": gap.required_capability
            }
            
        except Exception as e:
            logger.error(f"Error creating module for gap {gap_id}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def _design_module(
        self,
        gap: CapabilityGap,
        additional_requirements: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Use AI to design a module that fills the capability gap."""
        
        if not self.ask_ai:
            return {"success": False, "error": "AskAI not available"}
        
        prompt = f"""Design a Python module to fill a capability gap in the Elysia AI system.

REQUIRED CAPABILITY: {gap.required_capability}
TASK DESCRIPTION: {gap.task_description}
ERROR CONTEXT: {json.dumps(gap.error_context, indent=2)}

EXISTING SYSTEM CONTEXT:
- Uses BaseModuleAdapter pattern for integration
- Modules are registered in ModuleRegistry
- System uses async/await patterns
- Modules should have clear capabilities and dependencies

DESIGN REQUIREMENTS:
{json.dumps(additional_requirements or {}, indent=2) if additional_requirements else "None"}

Please design a complete module that:
1. Provides the required capability: {gap.required_capability}
2. Follows Python best practices and PEP 8
3. Integrates with BaseModuleAdapter pattern
4. Has proper error handling and logging
5. Is well-documented
6. Can be easily registered and used

Return JSON with:
{{
    "module_name": "descriptive_name",
    "class_name": "MainClass",
    "description": "What this module does",
    "capabilities": ["capability1", "capability2"],
    "dependencies": ["module1", "module2"],
    "design_rationale": "Why this design",
    "key_methods": [
        {{"name": "method1", "purpose": "what it does"}},
        {{"name": "method2", "purpose": "what it does"}}
    ],
    "design_notes": "Additional design considerations"
}}
"""
        
        try:
            response = await self.ask_ai.ask(
                prompt=prompt,
                provider=AIProvider.OPENAI,
                temperature=0.7,
                max_tokens=2000
            )
            
            if not response.success:
                return {"success": False, "error": "AI design request failed"}
            
            # Parse JSON from response
            import re
            content = response.content.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                design = json.loads(json_match.group(0))
                return {"success": True, "design": design}
            else:
                return {"success": False, "error": "Could not parse design JSON"}
                
        except Exception as e:
            logger.error(f"Error designing module: {e}")
            return {"success": False, "error": str(e)}
    
    async def _generate_module_code(
        self,
        gap: CapabilityGap,
        design: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate the actual Python code for the module."""
        
        if not self.ask_ai:
            return {"success": False, "error": "AskAI not available"}
        
        prompt = f"""Generate complete Python module code based on this design:

MODULE DESIGN:
{json.dumps(design, indent=2)}

REQUIRED CAPABILITY: {gap.required_capability}
TASK NEED: {gap.task_description}

Generate a complete, production-ready Python module file that:
1. Implements the class '{design.get("class_name", "Module")}'
2. Provides capability: {gap.required_capability}
3. Follows BaseModuleAdapter pattern (import from project_guardian.base_module_adapter)
4. Has all methods from the design
5. Includes proper imports, type hints, docstrings
6. Has error handling and logging
7. Is ready to be saved as a .py file and imported

Return ONLY the Python code, no markdown, no explanations, just the code.
"""
        
        try:
            response = await self.ask_ai.ask(
                prompt=prompt,
                provider=AIProvider.OPENAI,
                temperature=0.5,
                max_tokens=4000
            )
            
            if not response.success:
                return {"success": False, "error": "AI code generation failed"}
            
            # Extract code (remove markdown code blocks if present)
            code = response.content.strip()
            if code.startswith("```python"):
                code = code[9:]
            if code.startswith("```"):
                code = code[3:]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()
            
            return {"success": True, "code": code}
            
        except Exception as e:
            logger.error(f"Error generating module code: {e}")
            return {"success": False, "error": str(e)}
    
    def _validate_module_code(self, code: str, module_name: str) -> Dict[str, Any]:
        """Validate the generated module code."""
        errors = []
        
        try:
            # Syntax validation
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return {"valid": False, "errors": errors}
        
        # Check for required elements
        if "class" not in code:
            errors.append("No class definition found")
        
        if "BaseModuleAdapter" not in code and "SimpleModuleAdapter" not in code:
            errors.append("Module doesn't use BaseModuleAdapter pattern")
        
        # Check for basic structure
        if "def" not in code:
            errors.append("No methods found")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
    
    async def _evaluate_module_trust(
        self,
        gap: CapabilityGap,
        design: Dict[str, Any],
        code: str
    ) -> Dict[str, Any]:
        """Evaluate if the module is safe to create."""
        
        if not self.trust_eval:
            return {"approved": True, "reason": "Trust evaluation not available"}
        
        try:
            # Evaluate the action of creating a new module
            action_context = {
                "action_type": "create_module",
                "capability": gap.required_capability,
                "module_name": design.get("module_name"),
                "code_length": len(code),
                "has_file_access": True,
                "has_network_access": "requests" in code or "http" in code.lower()
            }
            
            result = await self.trust_eval.evaluate_action(
                action="create_auto_module",
                context=action_context
            )
            
            return {
                "approved": result.get("trust_score", 0) >= self.min_confidence_threshold,
                "trust_score": result.get("trust_score", 0),
                "reason": result.get("reasoning", "Trust evaluation completed")
            }
            
        except Exception as e:
            logger.warning(f"Trust evaluation error: {e}")
            return {"approved": True, "reason": "Trust evaluation error, allowing"}
    
    def _write_module_file(self, module_name: str, code: str) -> Optional[Path]:
        """Write the module code to a file."""
        try:
            # Sanitize module name
            safe_name = module_name.lower().replace(" ", "_").replace("-", "_")
            if not safe_name.isidentifier():
                safe_name = "auto_module_" + safe_name.replace(" ", "_")
            
            module_file = self.modules_dir / f"{safe_name}.py"
            
            # Ensure unique filename
            counter = 1
            while module_file.exists():
                module_file = self.modules_dir / f"{safe_name}_{counter}.py"
                counter += 1
            
            with open(module_file, 'w', encoding='utf-8') as f:
                f.write(code)
            
            logger.info(f"Module file written: {module_file}")
            return module_file
            
        except Exception as e:
            logger.error(f"Error writing module file: {e}")
            return None
    
    async def _register_module(
        self,
        module_name: str,
        class_name: str,
        module_path: Path,
        design: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Register the new module in the system."""
        
        if not self.registry:
            return {"success": False, "error": "ModuleRegistry not available"}
        
        try:
            # Import the module dynamically
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if not spec or not spec.loader:
                return {"success": False, "error": "Could not create module spec"}
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Get the class
            if not hasattr(module, class_name):
                return {"success": False, "error": f"Class {class_name} not found in module"}
            
            module_class = getattr(module, class_name)
            
            # Create instance
            instance = module_class()
            
            # Register with SimpleModuleAdapter
            capabilities = design.get("capabilities", [gap.required_capability])
            dependencies = design.get("dependencies", [])
            
            adapter = SimpleModuleAdapter(
                module_name=module_name,
                module_instance=instance,
                priority=5,
                dependencies=dependencies
            )
            
            # Override capabilities
            adapter.capabilities = capabilities
            
            success = self.registry.register(
                module_name=module_name,
                adapter=adapter,
                auto_initialize=True
            )
            
            if success:
                return {
                    "success": True,
                    "module_name": module_name,
                    "registered": True
                }
            else:
                return {"success": False, "error": "Registration failed"}
                
        except Exception as e:
            logger.error(f"Error registering module: {e}", exc_info=True)
            return {"success": False, "error": f"Registration error: {str(e)}"}
    
    def get_gap(self, gap_id: str) -> Optional[CapabilityGap]:
        """Get a capability gap by ID."""
        with self._lock:
            return self.capability_gaps.get(gap_id)
    
    def list_unresolved_gaps(self) -> List[CapabilityGap]:
        """List all unresolved capability gaps."""
        with self._lock:
            return [gap for gap in self.capability_gaps.values() if not gap.resolved]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about auto-created modules."""
        with self._lock:
            return {
                "total_gaps_detected": len(self.capability_gaps),
                "resolved_gaps": sum(1 for g in self.capability_gaps.values() if g.resolved),
                "unresolved_gaps": sum(1 for g in self.capability_gaps.values() if not g.resolved),
                "modules_created": len(self.created_modules),
                "auto_create_enabled": self.auto_create_enabled
            }

