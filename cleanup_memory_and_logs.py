#!/usr/bin/env python3
"""
Comprehensive Memory and Log Cleanup
=====================================
Cleans up redundant logs and optimizes memory storage
"""

import sys
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import gzip
import shutil

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))

def cleanup_log_file(log_path: Path, archive_old: bool = True, days_to_keep: int = 7) -> dict:
    """
    Clean up redundant log entries from a log file.
    
    Args:
        log_path: Path to log file
        archive_old: Whether to archive old logs
        days_to_keep: Keep logs from last N days
        
    Returns:
        Dictionary with cleanup results
    """
    if not log_path.exists():
        return {"error": f"Log file not found: {log_path}"}
    
    print(f"\nProcessing: {log_path.name}")
    print(f"  Original size: {log_path.stat().st_size / (1024*1024):.2f} MB")
    
    try:
        # Read log file
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        original_line_count = len(lines)
        original_size = log_path.stat().st_size
        
        # Patterns to identify redundant entries
        redundant_patterns = [
            (r'httpx - INFO - HTTP Request:.*', 'HTTP request logs'),
            (r'ElysiaLoop heartbeat:.*', 'Heartbeat messages'),
            (r'Runtime health.*', 'Health check messages'),
        ]
        
        # Track seen entries to remove duplicates
        seen_entries = defaultdict(int)
        cleaned_lines = []
        removed_by_type = defaultdict(int)
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        for line in lines:
            # Extract timestamp if present
            timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            line_date = None
            if timestamp_match:
                try:
                    line_date = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                except:
                    pass
            
            # Skip old entries (older than days_to_keep)
            if line_date and line_date < cutoff_date:
                removed_by_type['old_entries'] += 1
                continue
            
            # Check for redundant patterns
            is_redundant = False
            for pattern, pattern_name in redundant_patterns:
                if re.search(pattern, line):
                    # Create a simplified key for duplicate detection
                    # For HTTP requests, use just the endpoint
                    if 'HTTP Request' in line:
                        endpoint_match = re.search(r'(GET|POST|PUT|DELETE) ([^\s"]+)', line)
                        if endpoint_match:
                            key = f"HTTP_{endpoint_match.group(1)}_{endpoint_match.group(2)[:50]}"
                        else:
                            key = line.strip()[:100]
                    # For heartbeats, use a time-based key (one per minute)
                    elif 'heartbeat' in line.lower():
                        if timestamp_match:
                            # Round to minute
                            minute_key = timestamp_match.group(1)[:16]  # YYYY-MM-DD HH:MM
                            key = f"heartbeat_{minute_key}"
                        else:
                            key = line.strip()[:50]
                    else:
                        key = line.strip()[:100]
                    
                    seen_entries[key] += 1
                    # Keep first occurrence, skip subsequent duplicates in same minute
                    if seen_entries[key] > 1:
                        is_redundant = True
                        removed_by_type[pattern_name] += 1
                    break
            
            if not is_redundant:
                cleaned_lines.append(line)
        
        # Write cleaned log
        if len(cleaned_lines) < original_line_count:
            # Backup original
            backup_path = log_path.with_suffix('.log.backup')
            if not backup_path.exists():
                shutil.copy2(log_path, backup_path)
                print(f"  Created backup: {backup_path.name}")
            
            # Write cleaned version
            with open(log_path, 'w', encoding='utf-8') as f:
                f.writelines(cleaned_lines)
            
            new_size = log_path.stat().st_size
            reduction = original_size - new_size
            reduction_pct = (reduction / original_size * 100) if original_size > 0 else 0
            
            print(f"  Cleaned: {original_line_count:,} -> {len(cleaned_lines):,} lines")
            print(f"  Size: {original_size / (1024*1024):.2f} MB -> {new_size / (1024*1024):.2f} MB")
            print(f"  Reduction: {reduction / (1024*1024):.2f} MB ({reduction_pct:.1f}%)")
            
            if removed_by_type:
                print(f"  Removed by type:")
                for rtype, count in removed_by_type.items():
                    print(f"    - {rtype}: {count:,} lines")
            
            # Archive old backup if it exists and is old
            if archive_old and backup_path.exists():
                backup_age = datetime.now() - datetime.fromtimestamp(backup_path.stat().st_mtime)
                if backup_age.days > 30:
                    archive_path = backup_path.with_suffix('.log.backup.gz')
                    with open(backup_path, 'rb') as f_in:
                        with gzip.open(archive_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    backup_path.unlink()
                    print(f"  Archived old backup: {archive_path.name}")
            
            return {
                "success": True,
                "original_lines": original_line_count,
                "cleaned_lines": len(cleaned_lines),
                "removed": original_line_count - len(cleaned_lines),
                "original_size_mb": round(original_size / (1024*1024), 2),
                "new_size_mb": round(new_size / (1024*1024), 2),
                "reduction_mb": round(reduction / (1024*1024), 2),
                "reduction_pct": round(reduction_pct, 1),
                "removed_by_type": dict(removed_by_type)
            }
        else:
            print(f"  No cleanup needed")
            return {
                "success": True,
                "action": "no_cleanup_needed",
                "lines": original_line_count
            }
            
    except Exception as e:
        return {"error": str(e)}


def cleanup_memory_system() -> dict:
    """
    Clean up memory system using existing cleanup utilities.
    
    Returns:
        Dictionary with cleanup results
    """
    print("\n" + "="*60)
    print("Memory System Cleanup")
    print("="*60)
    
    try:
        from project_guardian.core import GuardianCore
        from project_guardian.memory_cleanup import MemoryCleanup
        import json
        
        print("\nLoading Guardian Core...")
        
        # Load external storage config if available
        config = {}
        config_dir = project_root / "config"
        external_config_file = config_dir / "external_storage.json"
        
        if external_config_file.exists():
            try:
                with open(external_config_file, 'r', encoding='utf-8') as f:
                    external_config = json.load(f)
                    config.update(external_config)
                    print(f"  Loaded external storage config: {external_config.get('external_drive', 'N/A')}")
            except Exception as e:
                print(f"  [WARNING] Could not load external storage config: {e}")
        
        # Initialize with config
        core = GuardianCore(config=config, allow_multiple=True)
        
        if not hasattr(core, 'memory') or not hasattr(core.memory, 'memory_log'):
            return {"error": "Memory system not available"}
        
        current_count = len(core.memory.memory_log)
        print(f"Current memory count: {current_count:,}")
        
        # Get size estimate
        cleanup = MemoryCleanup(core.memory)
        stats = cleanup.get_memory_size_estimate()
        
        if "error" not in stats:
            print(f"Estimated memory size: {stats.get('estimated_size_mb', 0):.2f} MB")
        
        # Perform cleanup if needed
        if current_count > 4000:
            print(f"\n[WARNING] Memory count ({current_count:,}) exceeds threshold (4000)")
            print("Performing consolidation...")
            
            result = cleanup.consolidate_memories(max_memories=4000, keep_recent_days=30)
            
            if "error" not in result:
                print(f"\n[OK] Memory cleanup completed!")
                print(f"   Original: {result.get('original_count', 0):,} memories")
                print(f"   Final: {result.get('final_count', 0):,} memories")
                print(f"   Removed: {result.get('removed', 0):,} memories")
                print(f"   Recent kept: {result.get('recent_kept', 0):,}")
                print(f"   High priority kept: {result.get('high_priority_kept', 0):,}")
                return result
            else:
                print(f"\n[ERROR] {result.get('error')}")
                return result
        else:
            print(f"\n[OK] Memory count ({current_count:,}) is within normal range.")
            print("No cleanup needed.")
            return {
                "action": "no_action_needed",
                "current_count": current_count
            }
            
    except Exception as e:
        import traceback
        print(f"\n[ERROR] {e}")
        # Only print traceback if it's not a configuration issue
        if "config" not in str(e).lower() and "external_storage" not in str(e).lower():
            traceback.print_exc()
        return {"error": str(e), "action": "skipped"}


def cleanup_vector_memory() -> dict:
    """
    Clean up vector memory files if they're too large.
    
    Returns:
        Dictionary with cleanup results
    """
    print("\n" + "="*60)
    print("Vector Memory Cleanup")
    print("="*60)
    
    # Check multiple possible paths
    possible_paths = [
        Path("F:/Project Guardian/memory"),
        Path("F:/ProjectGuardian/memory"),
        Path("c:/Users/mrnat/Project guardian/memory")
    ]
    
    vector_memory_path = None
    for path in possible_paths:
        if path.exists():
            vector_memory_path = path
            break
    
    if not vector_memory_path:
        return {"error": "Vector memory directory not found"}
    
    print(f"  Using path: {vector_memory_path}")
    
    results = {}
    
    # Check FAISS index
    faiss_index = vector_memory_path / "vectors" / "index.faiss"
    if faiss_index.exists():
        size_mb = faiss_index.stat().st_size / (1024*1024)
        print(f"\nFAISS Index: {size_mb:.2f} MB")
        
        if size_mb > 50:  # If larger than 50MB, suggest rebuilding
            print(f"[WARNING] FAISS index is large ({size_mb:.2f} MB)")
            print("   Consider rebuilding after memory cleanup")
            results['faiss_size_mb'] = round(size_mb, 2)
            results['faiss_action'] = 'consider_rebuild'
        else:
            print(f"[OK] FAISS index size is acceptable")
            results['faiss_size_mb'] = round(size_mb, 2)
            results['faiss_action'] = 'ok'
    
    # Check metadata
    metadata_file = vector_memory_path / "vectors" / "metadata.json"
    if metadata_file.exists():
        size_mb = metadata_file.stat().st_size / (1024*1024)
        print(f"Metadata: {size_mb:.2f} MB")
        results['metadata_size_mb'] = round(size_mb, 2)
    
    return results


def main():
    """Main cleanup function"""
    print("="*60)
    print("Comprehensive Memory and Log Cleanup")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Check F: drive logs
    logs_dir = Path("F:/Project Guardian/logs")
    if not logs_dir.exists():
        logs_dir = Path("c:/Users/mrnat/Project guardian")
        print(f"\n[INFO] F: drive logs not found, checking local directory")
    
    log_results = []
    
    # Find and clean log files
    if logs_dir.exists():
        log_files = list(logs_dir.glob("*.log"))
        if not log_files:
            # Try parent directory
            logs_dir = Path("c:/Users/mrnat/Project guardian")
            log_files = list(logs_dir.glob("*.log"))
        
        if log_files:
            print("\n" + "="*60)
            print("Log File Cleanup")
            print("="*60)
            
            for log_file in log_files:
                result = cleanup_log_file(log_file, archive_old=True, days_to_keep=7)
                log_results.append({
                    "file": log_file.name,
                    **result
                })
        else:
            print("\nNo log files found to clean")
    else:
        print(f"\n[INFO] Logs directory not found: {logs_dir}")
    
    # Clean up memory system
    memory_result = cleanup_memory_system()
    
    # Clean up vector memory
    vector_result = cleanup_vector_memory()
    
    # Summary
    print("\n" + "="*60)
    print("Cleanup Summary")
    print("="*60)
    
    total_log_reduction = 0
    for log_result in log_results:
        if "reduction_mb" in log_result:
            total_log_reduction += log_result["reduction_mb"]
            print(f"\n{log_result['file']}:")
            print(f"  Reduced by {log_result['reduction_mb']} MB ({log_result['reduction_pct']}%)")
    
    if total_log_reduction > 0:
        print(f"\nTotal log space freed: {total_log_reduction:.2f} MB")
    
    if "removed" in memory_result:
        print(f"\nMemory cleanup:")
        print(f"  Removed {memory_result.get('removed', 0):,} memories")
        print(f"  Final count: {memory_result.get('final_count', 0):,} memories")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    main()
