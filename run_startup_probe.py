#!/usr/bin/env python3
"""
Runtime probe to verify no embedding HTTP requests occur during startup.
Monkeypatches embedding functions to raise if called before enable_embeddings().
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import logging

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# Suppress noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


class EmbeddingCallProbe:
    """Probe to detect premature embedding calls."""
    
    def __init__(self):
        self.embedding_calls = []
        self.embeddings_enabled = False
        self.startup_complete = False
    
    def track_embedding_call(self, *args, **kwargs):
        """Track embedding call and raise if called before enable."""
        if not self.embeddings_enabled:
            call_info = {
                "args": args,
                "kwargs": kwargs,
                "stack": self._get_call_stack()
            }
            self.embedding_calls.append(call_info)
            raise AssertionError(
                f"Embedding called during startup before enable_embeddings()!\n"
                f"Call: {args}, {kwargs}\n"
                f"Stack: {call_info['stack']}"
            )
        # If enabled, allow the call (but we're mocking, so this won't execute)
        return [0.1] * 384  # Fake embedding
    
    def _get_call_stack(self):
        """Get simplified call stack."""
        import traceback
        tb = traceback.extract_tb(sys.exc_info()[2])
        return [f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in tb[-5:]]
    
    def enable_embeddings(self):
        """Mark embeddings as enabled."""
        self.embeddings_enabled = True
        logger.info("[PROBE] Embeddings enabled - calls now allowed")
    
    def get_results(self):
        """Get probe results."""
        return {
            "embedding_calls_during_startup": len(self.embedding_calls),
            "calls": self.embedding_calls,
            "embeddings_enabled": self.embeddings_enabled
        }


def probe_unified_startup():
    """Probe unified startup for premature embedding calls."""
    logger.info("="*70)
    logger.info("STARTUP PROBE: Verifying no embeddings during startup")
    logger.info("="*70)
    
    probe = EmbeddingCallProbe()
    
    # Monkeypatch embedding functions to track calls
    embedding_patches = []
    
    # Patch MemoryVectorSearch._get_embedding
    try:
        from project_guardian import memory_vector_search
        patch_obj = patch.object(
            memory_vector_search.MemoryVectorSearch,
            '_get_embedding',
            side_effect=probe.track_embedding_call
        )
        embedding_patches.append(patch_obj)
        patch_obj.start()
        logger.info("[PROBE] Patched MemoryVectorSearch._get_embedding")
    except (ImportError, AttributeError) as e:
        logger.debug(f"[PROBE] Could not patch MemoryVectorSearch._get_embedding: {e}")
    
    # Patch httpx to detect embedding API calls
    try:
        import httpx
        original_request = httpx.Client.request
        
        def track_httpx_request(self, *args, **kwargs):
            url = kwargs.get('url') or (args[1] if len(args) > 1 else None)
            if url and 'embeddings' in str(url).lower():
                probe.track_embedding_call(url=url, method=kwargs.get('method', args[0] if args else None))
            return original_request(self, *args, **kwargs)
        
        patch_obj = patch.object(httpx.Client, 'request', track_httpx_request)
        embedding_patches.append(patch_obj)
        patch_obj.start()
        logger.info("[PROBE] Patched httpx.Client.request to detect embedding API calls")
    except ImportError:
        logger.debug("[PROBE] httpx not available, skipping patch")
    
    try:
        # Import and initialize unified system
        logger.info("[PROBE] Starting unified system initialization...")
        from run_elysia_unified import UnifiedElysiaSystem
        
        system = UnifiedElysiaSystem()
        logger.info("[PROBE] UnifiedElysiaSystem created")
        
        # Start the system (this should NOT trigger embeddings)
        logger.info("[PROBE] Starting unified system (will stop after start() completes)...")
        system.start()
        logger.info("[PROBE] Unified system started")
        
        # Mark startup as complete
        probe.startup_complete = True
        logger.info("[PROBE] Startup complete - checking for premature embedding calls...")
        
        # Get results
        results = probe.get_results()
        
        if results["embedding_calls_during_startup"] == 0:
            logger.info("="*70)
            logger.info("[PASS] No embedding calls detected during startup!")
            logger.info("="*70)
            return True
        else:
            logger.error("="*70)
            logger.error(f"[FAIL] {results['embedding_calls_during_startup']} embedding calls detected during startup!")
            logger.error("="*70)
            for i, call in enumerate(results["calls"], 1):
                logger.error(f"Call {i}: {call}")
            return False
            
    except AssertionError as e:
        # This is expected if embeddings are called prematurely
        logger.error("="*70)
        logger.error("[FAIL] Embedding call detected during startup!")
        logger.error("="*70)
        logger.error(str(e))
        results = probe.get_results()
        logger.error(f"Total premature calls: {results['embedding_calls_during_startup']}")
        return False
    except Exception as e:
        logger.error(f"[ERROR] Probe failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up patches
        for patch_obj in embedding_patches:
            try:
                patch_obj.stop()
            except Exception:
                pass


def probe_core_startup():
    """Probe GuardianCore startup for premature embedding calls."""
    logger.info("="*70)
    logger.info("STARTUP PROBE: Verifying no embeddings during GuardianCore init")
    logger.info("="*70)
    
    probe = EmbeddingCallProbe()
    
    # Monkeypatch embedding functions
    embedding_patches = []
    
    try:
        from project_guardian import memory_vector_search
        patch_obj = patch.object(
            memory_vector_search.MemoryVectorSearch,
            '_get_embedding',
            side_effect=probe.track_embedding_call
        )
        embedding_patches.append(patch_obj)
        patch_obj.start()
        logger.info("[PROBE] Patched MemoryVectorSearch._get_embedding")
    except (ImportError, AttributeError) as e:
        logger.debug(f"[PROBE] Could not patch MemoryVectorSearch._get_embedding: {e}")
    
    try:
        # Import and initialize GuardianCore
        logger.info("[PROBE] Creating GuardianCore...")
        from project_guardian.guardian_singleton import get_guardian_core
        
        core = get_guardian_core()
        logger.info("[PROBE] GuardianCore created")
        
        # Check if memory has enable_embeddings
        if hasattr(core, 'memory') and hasattr(core.memory, 'enable_embeddings'):
            logger.info("[PROBE] Memory has enable_embeddings method")
            # Verify embeddings are disabled
            if hasattr(core.memory, '_embeddings_enabled'):
                assert core.memory._embeddings_enabled is False, "Embeddings should be disabled during init"
                logger.info("[PROBE] Verified: _embeddings_enabled = False")
        
        # Mark startup as complete
        probe.startup_complete = True
        
        # Get results
        results = probe.get_results()
        
        if results["embedding_calls_during_startup"] == 0:
            logger.info("="*70)
            logger.info("[PASS] No embedding calls detected during GuardianCore init!")
            logger.info("="*70)
            return True
        else:
            logger.error("="*70)
            logger.error(f"[FAIL] {results['embedding_calls_during_startup']} embedding calls detected during init!")
            logger.error("="*70)
            return False
            
    except AssertionError as e:
        logger.error("="*70)
        logger.error("[FAIL] Embedding call detected during GuardianCore init!")
        logger.error("="*70)
        logger.error(str(e))
        return False
    except Exception as e:
        logger.error(f"[ERROR] Probe failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up patches
        for patch_obj in embedding_patches:
            try:
                patch_obj.stop()
            except Exception:
                pass


def main():
    """Run startup probes."""
    logger.info("Starting startup verification probes...")
    logger.info("")
    
    # Probe 1: GuardianCore initialization
    core_ok = probe_core_startup()
    logger.info("")
    
    # Probe 2: Unified system startup
    unified_ok = probe_unified_startup()
    logger.info("")
    
    # Summary
    logger.info("="*70)
    logger.info("PROBE SUMMARY")
    logger.info("="*70)
    logger.info(f"GuardianCore init: {'PASS' if core_ok else 'FAIL'}")
    logger.info(f"Unified startup: {'PASS' if unified_ok else 'FAIL'}")
    logger.info("="*70)
    
    if core_ok and unified_ok:
        logger.info("[SUCCESS] All probes passed - no embeddings during startup!")
        return 0
    else:
        logger.error("[FAILURE] Some probes failed - embeddings detected during startup!")
        return 1


if __name__ == "__main__":
    sys.exit(main())

