"""
CodeGenClient - LLM wrapper for code generation
"""

import json
import logging
import time
from pathlib import Path
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class CodeGenClient:
    """
    Thin wrapper around LLM for code generation.
    Generates patches based on step descriptions and acceptance criteria.
    """
    
    def __init__(self, api_manager=None):
        """
        Initialize code generation client.
        
        Args:
            api_manager: API key manager for LLM access
        """
        self.api_manager = api_manager
        self.has_llm = api_manager and api_manager.has_llm_access() if api_manager else False

        if not self.has_llm:
            if api_manager is None:
                logger.debug("CodeGenClient: no api_manager; using fallback mode")
            else:
                logger.warning("No LLM access available. CodeGenClient will use fallback mode.")
    
    def generate_patch(self, 
                      step_description: str,
                      current_files: Dict[str, str],
                      target_files: List[str],
                      acceptance_criteria: List[str],
                      context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Generate code patches for target files.
        
        Args:
            step_description: What needs to be done
            current_files: Dict of file_path -> current content
            target_files: List of files to modify/create
            acceptance_criteria: List of criteria that must be met
            context: Optional additional context (proposal metadata, etc.)
        
        Returns:
            Dict mapping file_path -> new content
        """
        if not self.has_llm or not self.api_manager:
            logger.debug("CodeGenClient.generate_patch: LLM unavailable, using fallback")
            return self._fallback_generation(
                step_description,
                target_files,
                current_files=current_files,
                acceptance_criteria=acceptance_criteria,
                context=context,
            )
        
        try:
            return self._llm_generate(
                step_description,
                current_files,
                target_files,
                acceptance_criteria,
                context,
            )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}, falling back")
            return self._fallback_generation(
                step_description,
                target_files,
                current_files=current_files,
                acceptance_criteria=acceptance_criteria,
                context=context,
            )
    
    def _llm_generate(self, 
                      step_description: str,
                      current_files: Dict[str, str],
                      target_files: List[str],
                      acceptance_criteria: List[str],
                      context: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """
        Use LLM to generate code patches.
        """
        client = self.api_manager.get_llm_client()
        if not client:
            raise RuntimeError("No LLM client available")
        
        # Structured registry messages + centralized OpenAI wrapper
        from ..llm.cloud_openai_chat import openai_chat_completion
        from ..module_prompt_registry import structured_messages_for_llm_call, validate_module_llm_output

        pe = {
            "task_id": f"codegen_{int(time.time())}",
            "task": {
                "step_description": step_description,
                "target_files": target_files,
                "acceptance_criteria": acceptance_criteria,
                "system_tone": self._get_system_prompt(),
                "user_prompt_flat": self._build_prompt(
                    step_description,
                    current_files,
                    target_files,
                    acceptance_criteria,
                    context,
                ),
            },
        }
        base_msgs = [{"role": "user", "content": "implementer codegen: structured task packet in JSON."}]
        msgs, triple = structured_messages_for_llm_call(base_msgs, pe, "implementer:codegen_patch")
        if not triple[0]:
            raise RuntimeError("structured role codegen_patch unavailable")

        try:
            if hasattr(client, "chat"):
                llm_output, oerr = openai_chat_completion(
                    client,
                    model="gpt-4o-mini",
                    messages=msgs,
                    max_tokens=4000,
                    temperature=0.3,
                )
                if oerr:
                    raise RuntimeError(oerr)
            else:
                raise RuntimeError("LLM client does not support chat interface")

            vd = validate_module_llm_output(triple[0], triple[1], triple[2], llm_output)
            if vd.get("valid"):
                body = str((vd.get("data") or {}).get("patch_document") or "").strip()
                llm_use = body if body else llm_output
            else:
                logger.debug("Codegen structured validation failed: %s", (vd.get("errors") or [])[:3])
                llm_use = llm_output

            return self._parse_llm_output(
                llm_use,
                target_files,
                step_description=step_description,
                acceptance_criteria=acceptance_criteria,
                current_files=current_files,
                context=context,
            )
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _build_prompt(self, 
                     step_description: str,
                     current_files: Dict[str, str],
                     target_files: List[str],
                     acceptance_criteria: List[str],
                     context: Optional[Dict[str, Any]]) -> str:
        """Build prompt for LLM"""
        prompt = f"""You are implementing a code change for an Elysia proposal.

Step Description:
{step_description}

Target Files:
{', '.join(target_files)}

Acceptance Criteria:
{chr(10).join(f'- {criterion}' for criterion in acceptance_criteria)}

Current File Contents:
"""
        for file_path, content in current_files.items():
            prompt += f"\n--- {file_path} ---\n{content}\n"
        
        if context:
            prompt += f"\nAdditional Context:\n{context}\n"
        
        prompt += """
Please generate the complete updated file contents for each target file.
Format your response as:

FILE: <file_path>
<complete file content>

FILE: <next_file_path>
<complete file content>
"""
        return prompt
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for code generation"""
        return """You are a code generation assistant for the Elysia system.
Your job is to generate clean, well-structured Python code that:
- Follows existing code style and patterns
- Includes proper error handling
- Has clear docstrings
- Is testable
- Only modifies the specified target files
- Meets all acceptance criteria

Generate complete file contents, not diffs."""
    
    def _parse_llm_output(
        self,
        llm_output: str,
        target_files: List[str],
        *,
        step_description: str,
        acceptance_criteria: List[str],
        current_files: Optional[Dict[str, str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Parse LLM output into file contents.
        Simple parser - expects FILE: <path> followed by content.
        """
        files: Dict[str, str] = {}
        current_file = None
        current_content: List[str] = []
        normalized_targets = {str(path).strip(): str(path).strip() for path in target_files}
        
        lines = llm_output.split('\n')
        
        for line in lines:
            if line.startswith('FILE:'):
                # Save previous file
                if current_file and current_file in normalized_targets:
                    files[current_file] = self._clean_generated_content('\n'.join(current_content))
                
                # Start new file
                current_file = line.replace('FILE:', '').strip()
                current_content = []
            elif current_file:
                current_content.append(line)
        
        # Save last file
        if current_file and current_file in normalized_targets:
            files[current_file] = self._clean_generated_content('\n'.join(current_content))
        
        # If parsing failed or some files were omitted, create deterministic scaffolds.
        for target_file in target_files:
            if target_file not in files:
                files[target_file] = self._generate_file_scaffold(
                    target_file,
                    step_description=step_description,
                    acceptance_criteria=acceptance_criteria,
                    current_content=(current_files or {}).get(target_file, ""),
                    context=context,
                )
        
        return files
    
    def _fallback_generation(
        self,
        step_description: str,
        target_files: List[str],
        *,
        current_files: Optional[Dict[str, str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Fallback generation when LLM is not available"""
        files: Dict[str, str] = {}
        for target_file in target_files:
            files[target_file] = self._generate_file_scaffold(
                target_file,
                step_description=step_description,
                acceptance_criteria=acceptance_criteria or [],
                current_content=(current_files or {}).get(target_file, ""),
                context=context,
            )
        return files

    def _clean_generated_content(self, content: str) -> str:
        """Strip common fenced-code wrappers from generated file content."""
        cleaned = content.strip()
        fenced = re.fullmatch(r"```(?:[A-Za-z0-9_+-]+)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()
        return cleaned

    def _generate_file_scaffold(
        self,
        target_file: str,
        *,
        step_description: str,
        acceptance_criteria: List[str],
        current_content: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        path = Path(target_file)
        suffix = path.suffix.lower()

        if suffix == ".py":
            return self._generate_python_scaffold(
                target_file,
                step_description=step_description,
                acceptance_criteria=acceptance_criteria,
                current_content=current_content,
                context=context,
            )
        if suffix == ".json":
            return json.dumps(
                {
                    "generated_by": "Implementer Agent",
                    "target_file": target_file,
                    "step_description": step_description,
                    "acceptance_criteria": acceptance_criteria,
                    "context": self._summarize_context(context),
                },
                indent=2,
            ) + "\n"
        if suffix in {".yml", ".yaml"}:
            criteria_block = acceptance_criteria or ["Documented fallback scaffold"]
            lines = [
                "generated_by: Implementer Agent",
                f"target_file: {target_file}",
                f"step_description: {json.dumps(step_description)}",
                "acceptance_criteria:",
            ]
            lines.extend(f"  - {json.dumps(item)}" for item in criteria_block)
            return "\n".join(lines) + "\n"
        if suffix in {".md", ".txt"}:
            criteria_block = acceptance_criteria or ["Documented fallback scaffold"]
            lines = [
                f"# Generated Scaffold for `{target_file}`",
                "",
                "## Step",
                step_description,
                "",
                "## Acceptance Criteria",
            ]
            lines.extend(f"- {item}" for item in criteria_block)
            return "\n".join(lines) + "\n"

        return (
            f"Generated scaffold for {target_file}\n"
            f"Step: {step_description}\n"
            f"Acceptance criteria: {', '.join(acceptance_criteria or ['Documented fallback scaffold'])}\n"
        )

    def _generate_python_scaffold(
        self,
        target_file: str,
        *,
        step_description: str,
        acceptance_criteria: List[str],
        current_content: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        path = Path(target_file)
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", path.stem or "generated_module").strip("_") or "generated_module"
        summary = self._summarize_context(context)
        criteria_json = json.dumps(acceptance_criteria or ["Documented fallback scaffold"], indent=4)
        summary_json = json.dumps(summary, indent=4, sort_keys=True)

        if "test" in path.parts or path.stem.startswith("test_"):
            return f'''"""Generated test scaffold for {target_file}."""\n\nfrom __future__ import annotations\n\n\ndef test_{safe_name}_scaffold_metadata() -> None:\n    criteria = {criteria_json}\n    assert isinstance(criteria, list)\n    assert all(isinstance(item, str) and item for item in criteria)\n'''

        generated_block = f'''
def generated_{safe_name}_scaffold() -> dict[str, object]:
    """Deterministic fallback scaffold when LLM codegen is unavailable."""
    return {{
        "target_file": {json.dumps(target_file)},
        "step_description": {json.dumps(step_description)},
        "acceptance_criteria": {criteria_json},
        "context_summary": {summary_json},
    }}
'''.strip()

        if current_content.strip():
            base = current_content.rstrip() + "\n\n"
            if f"generated_{safe_name}_scaffold" in current_content:
                return current_content if current_content.endswith("\n") else current_content + "\n"
            return base + generated_block + "\n"

        return f'''"""Generated scaffold for {target_file}."""\n\nfrom __future__ import annotations\n\n\ndef generated_{safe_name}_scaffold() -> dict[str, object]:\n    """Deterministic fallback scaffold when LLM codegen is unavailable."""\n    return {{\n        "target_file": {json.dumps(target_file)},\n        "step_description": {json.dumps(step_description)},\n        "acceptance_criteria": {criteria_json},\n        "context_summary": {summary_json},\n    }}\n'''

    def _summarize_context(self, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(context, dict):
            return {}
        summarized: Dict[str, Any] = {}
        for key, value in context.items():
            if key == "proposal" and isinstance(value, dict):
                summarized[key] = {
                    "proposal_id": value.get("proposal_id"),
                    "status": value.get("status"),
                    "domain": value.get("domain"),
                }
            elif isinstance(value, (str, int, float, bool)) or value is None:
                summarized[key] = value
        return summarized
    
    def validate_patch(self, patch: Dict[str, str], target_files: List[str]) -> tuple[bool, Optional[str]]:
        """
        Validate that patch only affects target files.
        
        Returns:
            (is_valid, error_message)
        """
        patch_files = set(patch.keys())
        target_set = set(target_files)
        
        if patch_files != target_set:
            extra = patch_files - target_set
            missing = target_set - patch_files
            error = f"Patch affects wrong files. Extra: {extra}, Missing: {missing}"
            return False, error
        
        return True, None

