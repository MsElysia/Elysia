"""
CodeGenClient - LLM wrapper for code generation
"""

import logging
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
            return self._fallback_generation(step_description, target_files)
        
        try:
            return self._llm_generate(step_description, current_files, target_files, 
                                    acceptance_criteria, context)
        except Exception as e:
            logger.error(f"LLM generation failed: {e}, falling back")
            return self._fallback_generation(step_description, target_files)
    
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
        
        # Build prompt
        prompt = self._build_prompt(step_description, current_files, target_files, 
                                   acceptance_criteria, context)
        
        # Call LLM
        try:
            from ..prompts.prompt_builder import log_legacy_llm_call

            log_legacy_llm_call(
                "",
                caller="CodegenClient.generate_code",
                reason="inline_prompt_implementer_codegen",
            )
            if hasattr(client, 'chat'):
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  # Use cheaper model for code generation
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more deterministic code
                    max_tokens=4000
                )
                llm_output = response.choices[0].message.content
            else:
                raise RuntimeError("LLM client does not support chat interface")
            
            # Parse LLM output into file contents
            # For now, simple parsing - in production, use structured output
            return self._parse_llm_output(llm_output, target_files)
            
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
    
    def _parse_llm_output(self, llm_output: str, target_files: List[str]) -> Dict[str, str]:
        """
        Parse LLM output into file contents.
        Simple parser - expects FILE: <path> followed by content.
        """
        files = {}
        current_file = None
        current_content = []
        
        lines = llm_output.split('\n')
        
        for line in lines:
            if line.startswith('FILE:'):
                # Save previous file
                if current_file and current_file in target_files:
                    files[current_file] = '\n'.join(current_content)
                
                # Start new file
                current_file = line.replace('FILE:', '').strip()
                current_content = []
            elif current_file:
                current_content.append(line)
        
        # Save last file
        if current_file and current_file in target_files:
            files[current_file] = '\n'.join(current_content)
        
        # If parsing failed, create placeholder files
        for target_file in target_files:
            if target_file not in files:
                files[target_file] = f"# TODO: Implement {target_file}\n# Generated by Implementer Agent\n"
        
        return files
    
    def _fallback_generation(self, step_description: str, target_files: List[str]) -> Dict[str, str]:
        """Fallback generation when LLM is not available"""
        files = {}
        for target_file in target_files:
            files[target_file] = f"""# Generated by Implementer Agent (fallback mode)
# Step: {step_description}
# File: {target_file}

# TODO: Implement this file
# LLM not available - manual implementation required

"""
        return files
    
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

