# enhanced_memory_core.py
# Enhanced Memory Core with Project Guardian features

import datetime
import json
import os
from typing import List, Dict, Optional, Any

class EnhancedMemoryCore:
    def __init__(self, filepath="memory_log.json"):
        self.memory_log = []
        self.filepath = filepath
        self.categories = {}
        self.priority_levels = {}
        self.load()

    def remember(self, thought, category="general", priority=0.5, tags=None):
        """
        Enhanced remember method with categories, priority, and tags
        Maintains backward compatibility with original remember()
        """
        timestamp = datetime.datetime.now().isoformat()
        entry = {
            "time": timestamp, 
            "thought": thought,
            "category": category,
            "priority": priority,
            "tags": tags or []
        }
        self.memory_log.append(entry)
        
        # Update category and priority tracking
        if category not in self.categories:
            self.categories[category] = []
        self.categories[category].append(len(self.memory_log) - 1)
        
        self._save()
        print(f"[Memory] {timestamp}: {thought} (Category: {category}, Priority: {priority})")
        return entry

    def recall_last(self, count=1, category=None):
        """Enhanced recall with category filtering"""
        if category:
            category_indices = self.categories.get(category, [])
            filtered_memories = [self.memory_log[i] for i in category_indices]
            return filtered_memories[-count:]
        return self.memory_log[-count:]

    def search_memories(self, keyword: str, category: Optional[str] = None) -> List[Dict]:
        """Search memories by keyword"""
        results = []
        memories_to_search = self.memory_log
        
        if category:
            category_indices = self.categories.get(category, [])
            memories_to_search = [self.memory_log[i] for i in category_indices]
        
        for memory in memories_to_search:
            if keyword.lower() in memory["thought"].lower():
                results.append(memory)
        
        return results

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        stats = {
            "total_memories": len(self.memory_log),
            "categories": len(self.categories),
            "category_breakdown": {},
            "average_priority": 0.0,
            "recent_activity": 0
        }
        
        if self.memory_log:
            priorities = [m.get("priority", 0.5) for m in self.memory_log]
            stats["average_priority"] = sum(priorities) / len(priorities)
            
            # Count recent memories (last 24 hours)
            cutoff = datetime.datetime.now() - datetime.timedelta(hours=24)
            recent_count = 0
            for memory in self.memory_log:
                memory_time = datetime.datetime.fromisoformat(memory["time"])
                if memory_time > cutoff:
                    recent_count += 1
            stats["recent_activity"] = recent_count
        
        # Category breakdown
        for category, indices in self.categories.items():
            stats["category_breakdown"][category] = len(indices)
        
        return stats

    def get_high_priority_memories(self, threshold=0.7) -> List[Dict]:
        """Get memories above priority threshold"""
        return [m for m in self.memory_log if m.get("priority", 0.5) >= threshold]

    def forget(self, category=None):
        """Enhanced forget with category support"""
        if category:
            # Remove memories from specific category
            category_indices = self.categories.get(category, [])
            for index in reversed(category_indices):
                if index < len(self.memory_log):
                    del self.memory_log[index]
            self.categories[category] = []
            print(f"[Memory] Cleared all memories in category: {category}")
        else:
            # Original behavior - clear all
            self.memory_log = []
            self.categories = {}
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
            print("[Memory] All memories cleared.")

    def dump_all(self):
        return self.memory_log

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.memory_log, f, indent=2)
        except Exception as e:
            print(f"[Memory] Save failed: {e}")

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.memory_log = json.load(f)
                
                # Rebuild category indices
                self.categories = {}
                for i, memory in enumerate(self.memory_log):
                    category = memory.get("category", "general")
                    if category not in self.categories:
                        self.categories[category] = []
                    self.categories[category].append(i)
                
                print(f"[Memory] Loaded {len(self.memory_log)} past memories.")
            except Exception as e:
                print(f"[Memory] Load failed: {e}")

# Backward compatibility alias
MemoryCore = EnhancedMemoryCore 