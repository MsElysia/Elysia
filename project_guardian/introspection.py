# project_guardian/introspection.py
# Introspection and Self-Reflection System for Project Guardian

import datetime
from typing import Dict, Any, List, Optional
from .memory import MemoryCore

class IntrospectionLens:
    """
    Memory analysis and introspection system for Project Guardian.
    Provides self-analysis and memory insights.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        
    def list_recent(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent memories.
        
        Args:
            count: Number of memories to retrieve
            
        Returns:
            List of recent memory entries
        """
        return self.memory.recall_last(count)
        
    def count_tags(self, tag_prefix: str = "[") -> int:
        """
        Count memories with specific tag prefixes.
        
        Args:
            tag_prefix: Tag prefix to search for
            
        Returns:
            Count of matching memories
        """
        mems = self.memory.get_recent_memories(limit=500, load_if_needed=True) if hasattr(self.memory, "get_recent_memories") else []
        return sum(1 for m in mems if m.get("thought", "").startswith(tag_prefix))
        
    def first_memory_time(self) -> str:
        """
        Get timestamp of oldest memory in a bounded recent sample.
        Uses get_recent_memories; for full history use dump_all (admin).
        """
        mems = self.memory.get_recent_memories(limit=500, load_if_needed=True) if hasattr(self.memory, "get_recent_memories") else []
        if not mems:
            return "N/A"
        times = [m.get("time", "") for m in mems if m.get("time")]
        return min(times) if times else "N/A"
        
    def get_memory_patterns(self) -> Dict[str, Any]:
        """
        Analyze memory patterns and statistics.
        
        Returns:
            Memory pattern analysis
        """
        mems = self.memory.get_recent_memories(limit=500, load_if_needed=True) if hasattr(self.memory, "get_recent_memories") else []
        # Category analysis (bounded sample)
        categories = {}
        for memory in mems:
            cat = memory.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        priorities = [m.get("priority", 0.5) for m in mems]
        avg_priority = sum(priorities) / len(priorities) if priorities else 0.0
        
        tag_counts = {}
        for memory in mems:
            thought = memory["thought"]
            if thought.startswith("["):
                tag_end = thought.find("]")
                if tag_end > 0:
                    tag = thought[1:tag_end]
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
                    
        return {
            "total_memories": len(mems),
            "categories": categories,
            "average_priority": avg_priority,
            "tag_counts": tag_counts,
            "first_memory": self.first_memory_time(),
            "memory_density": len(mems) / max(1, (datetime.datetime.now() - datetime.datetime.fromisoformat(self.first_memory_time())).days) if self.first_memory_time() != "N/A" else 0
        }
        
    def find_memory_clusters(self, keyword: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Find clusters of related memories.
        
        Args:
            keyword: Keyword to search for
            limit: Maximum number of clusters
            
        Returns:
            List of memory clusters
        """
        memories = self.memory.search_memories(keyword, min(limit * 10, 100))
        clusters = []
        
        # Group by category
        category_groups = {}
        for memory in memories:
            cat = memory.get("category", "unknown")
            if cat not in category_groups:
                category_groups[cat] = []
            category_groups[cat].append(memory)
            
        # Create clusters
        for category, group_memories in category_groups.items():
            if len(group_memories) >= 2:  # Only clusters with multiple memories
                clusters.append({
                    "category": category,
                    "memories": group_memories[:limit],
                    "count": len(group_memories),
                    "avg_priority": sum(m.get("priority", 0.5) for m in group_memories) / len(group_memories)
                })
                
        return sorted(clusters, key=lambda x: x["count"], reverse=True)[:limit]
        
    def get_memory_timeline(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get memory timeline for the last N hours.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            Timeline of memories
        """
        cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)
        mems = self.memory.get_recent_memories(limit=500, load_if_needed=True) if hasattr(self.memory, "get_recent_memories") else []
        timeline = []
        for memory in mems:
            try:
                memory_time = datetime.datetime.fromisoformat(memory["time"])
                if memory_time >= cutoff_time:
                    timeline.append({
                        "time": memory["time"],
                        "thought": memory["thought"],
                        "category": memory.get("category", "unknown"),
                        "priority": memory.get("priority", 0.5)
                    })
            except ValueError:
                continue
                
        return sorted(timeline, key=lambda x: x["time"])
        
    def get_memory_correlations(self, keyword: str, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Find correlated memories based on keywords and temporal proximity.
        
        Args:
            keyword: Keyword to search for correlations
            threshold: Minimum correlation score (0-1)
            
        Returns:
            List of correlated memory groups
        """
        memories = self.memory.search_memories(keyword, 50)
        if len(memories) < 2:
            return []
            
        correlations = []
        for i, mem1 in enumerate(memories):
            for mem2 in memories[i+1:]:
                # Calculate correlation based on shared keywords
                thought1 = mem1["thought"].lower()
                thought2 = mem2["thought"].lower()
                
                words1 = set(thought1.split())
                words2 = set(thought2.split())
                shared_words = words1.intersection(words2)
                
                if shared_words:
                    correlation = len(shared_words) / max(len(words1), len(words2))
                    
                    if correlation >= threshold:
                        # Check temporal proximity
                        try:
                            time1 = datetime.datetime.fromisoformat(mem1["time"])
                            time2 = datetime.datetime.fromisoformat(mem2["time"])
                            time_diff = abs((time1 - time2).total_seconds() / 3600)  # hours
                            temporal_proximity = 1.0 / (1.0 + time_diff / 24)  # Decay over days
                            
                            correlations.append({
                                "memory1": mem1["thought"][:100],
                                "memory2": mem2["thought"][:100],
                                "correlation_score": correlation,
                                "temporal_proximity": temporal_proximity,
                                "shared_keywords": list(shared_words)[:5],
                                "time_diff_hours": time_diff
                            })
                        except (ValueError, KeyError):
                            continue
                            
        return sorted(correlations, key=lambda x: x["correlation_score"], reverse=True)[:10]
        
    def analyze_memory_health(self) -> Dict[str, Any]:
        """
        Analyze the health and quality of the memory system (bounded sample).
        
        Returns:
            Memory health report
        """
        memories = self.memory.get_recent_memories(limit=500, load_if_needed=True) if hasattr(self.memory, "get_recent_memories") else []
        
        if not memories:
            return {
                "status": "empty",
                "total_memories": 0,
                "warnings": ["No memories stored"]
            }
            
        # Check for missing fields
        missing_fields = {
            "category": 0,
            "priority": 0,
            "thought": 0
        }
        
        for memory in memories:
            if "category" not in memory or not memory["category"]:
                missing_fields["category"] += 1
            if "priority" not in memory:
                missing_fields["priority"] += 1
            if "thought" not in memory or not memory["thought"]:
                missing_fields["thought"] += 1
                
        # Check for duplicate thoughts
        thought_texts = [m.get("thought", "") for m in memories]
        duplicates = len(thought_texts) - len(set(thought_texts))
        
        # Check timestamp validity
        invalid_timestamps = 0
        for memory in memories:
            try:
                datetime.datetime.fromisoformat(memory.get("time", ""))
            except (ValueError, KeyError):
                invalid_timestamps += 1
                
        # Calculate health score
        health_score = 1.0
        health_score -= (missing_fields["thought"] / len(memories)) * 0.5
        health_score -= (missing_fields["category"] / len(memories)) * 0.2
        health_score -= (missing_fields["priority"] / len(memories)) * 0.1
        health_score -= (invalid_timestamps / len(memories)) * 0.2
        health_score = max(0.0, health_score)
        
        warnings = []
        if missing_fields["thought"] > 0:
            warnings.append(f"{missing_fields['thought']} memories missing thought field")
        if missing_fields["category"] > len(memories) * 0.1:
            warnings.append(f"High percentage missing category: {missing_fields['category']}")
        if duplicates > len(memories) * 0.1:
            warnings.append(f"Possible duplicate memories detected: {duplicates}")
        if invalid_timestamps > 0:
            warnings.append(f"{invalid_timestamps} memories with invalid timestamps")
            
        status = "healthy" if health_score > 0.8 else "degraded" if health_score > 0.5 else "poor"
        
        return {
            "status": status,
            "health_score": health_score,
            "total_memories": len(memories),
            "missing_fields": missing_fields,
            "duplicate_count": duplicates,
            "invalid_timestamps": invalid_timestamps,
            "warnings": warnings if warnings else ["No issues detected"]
        }
        
    def get_focus_analysis(self, hours: int = 24) -> Dict[str, Any]:
        """
        Analyze what the system has been focusing on recently.
        
        Args:
            hours: Time window for analysis
            
        Returns:
            Focus analysis report
        """
        timeline = self.get_memory_timeline(hours)
        
        if not timeline:
            return {
                "time_window_hours": hours,
                "activity_count": 0,
                "primary_focus": "No activity",
                "focus_distribution": {},
                "priority_trend": "stable"
            }
            
        # Category distribution
        category_focus = {}
        priority_trend = []
        
        for entry in timeline:
            cat = entry.get("category", "unknown")
            category_focus[cat] = category_focus.get(cat, 0) + 1
            priority_trend.append(entry.get("priority", 0.5))
            
        # Calculate priority trend
        if len(priority_trend) > 1:
            first_half = priority_trend[:len(priority_trend)//2]
            second_half = priority_trend[len(priority_trend)//2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            
            if avg_second > avg_first + 0.1:
                trend = "increasing"
            elif avg_second < avg_first - 0.1:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"
            
        primary_focus = max(category_focus.items(), key=lambda x: x[1])[0] if category_focus else "unknown"
        
        return {
            "time_window_hours": hours,
            "activity_count": len(timeline),
            "primary_focus": primary_focus,
            "focus_distribution": category_focus,
            "priority_trend": trend,
            "average_priority": sum(priority_trend) / len(priority_trend) if priority_trend else 0.5,
            "most_active_period": self._identify_active_period(timeline)
        }
        
    def _identify_active_period(self, timeline: List[Dict[str, Any]]) -> str:
        """
        Identify the most active period from timeline.
        
        Args:
            timeline: Timeline of memories
            
        Returns:
            Most active period description
        """
        if not timeline:
            return "No activity"
            
        try:
            times = [datetime.datetime.fromisoformat(entry["time"]) for entry in timeline]
            if not times:
                return "Unknown"
                
            # Group by hour of day
            hour_counts = {}
            for t in times:
                hour = t.hour
                hour_counts[hour] = hour_counts.get(hour, 0) + 1
                
            if hour_counts:
                most_active_hour = max(hour_counts.items(), key=lambda x: x[1])[0]
                
                if 6 <= most_active_hour < 12:
                    return "Morning"
                elif 12 <= most_active_hour < 18:
                    return "Afternoon"
                elif 18 <= most_active_hour < 22:
                    return "Evening"
                else:
                    return "Night"
            else:
                return "Unknown"
        except (ValueError, KeyError):
            return "Unknown"

class SelfReflector:
    """
    Self-awareness and reflection system for Project Guardian.
    Provides identity awareness and status tracking.
    """
    
    def __init__(self, memory: MemoryCore, guardian_core):
        self.memory = memory
        self.guardian = guardian_core
        self.introspection = IntrospectionLens(memory)
        
    def summarize_self(self) -> Dict[str, Any]:
        """
        Generate a comprehensive self-summary.
        
        Returns:
            Self-summary dictionary
        """
        # Avoid circular dependency - get data directly instead of via get_system_status()
        patterns = self.introspection.get_memory_patterns()
        
        # Get recent activity
        recent_memories = self.memory.recall_last(5)
        last_memory = recent_memories[-1]["thought"] if recent_memories else "No recent activity"
        
        # Get active tasks
        active_tasks = self.guardian.tasks.get_active_tasks()
        task_summary = f"{len(active_tasks)} active tasks" if active_tasks else "No active tasks"
        
        # Calculate uptime directly
        uptime = (datetime.datetime.now() - self.guardian.start_time).total_seconds()
        
        # Get trust and consensus data directly
        trust_report = self.guardian.trust.get_trust_report()
        consensus_stats = self.guardian.consensus.get_agent_stats()
        safety_report = self.guardian.safety.get_safety_report()
        
        return {
            "identity": "Project Guardian - Autonomous AI Safety System",
            "uptime_seconds": uptime,
            "last_memory": last_memory,
            "active_tasks": task_summary,
            "memory_stats": {
                "total_memories": patterns["total_memories"],
                "categories": len(patterns["categories"]),
                "average_priority": patterns["average_priority"]
            },
            "system_health": {
                "trust_average": trust_report.get("average_trust", 0.5),
                "consensus_agents": consensus_stats.get("total_agents", 0),
                "safety_level": safety_report.get("safety_level", "unknown")
            },
            "capabilities": [
                "Memory Management",
                "Safe Code Mutation", 
                "Safety Validation",
                "Trust Management",
                "Task Management",
                "Consensus Decision Making",
                "Rollback Recovery"
            ]
        }
        
    def reflect_on_behavior(self) -> Dict[str, Any]:
        """
        Analyze recent behavior patterns.
        
        Returns:
            Behavior analysis
        """
        recent_memories = self.memory.recall_last(20)
        
        # Analyze recent activity patterns
        categories = {}
        priorities = []
        tags = {}
        
        for memory in recent_memories:
            # Category analysis
            cat = memory.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            
            # Priority analysis
            priorities.append(memory.get("priority", 0.5))
            
            # Tag analysis
            thought = memory["thought"]
            if thought.startswith("["):
                tag_end = thought.find("]")
                if tag_end > 0:
                    tag = thought[1:tag_end]
                    tags[tag] = tags.get(tag, 0) + 1
                    
        # Identify patterns
        dominant_category = max(categories.items(), key=lambda x: x[1])[0] if categories else "none"
        avg_priority = sum(priorities) / len(priorities) if priorities else 0.0
        dominant_tag = max(tags.items(), key=lambda x: x[1])[0] if tags else "none"
        
        return {
            "recent_activity_count": len(recent_memories),
            "dominant_category": dominant_category,
            "average_priority": avg_priority,
            "dominant_tag": dominant_tag,
            "behavior_pattern": self._classify_behavior(avg_priority, len(recent_memories)),
            "focus_areas": list(categories.keys())[:3],
            "active_tags": list(tags.keys())[:5]
        }
        
    def _classify_behavior(self, avg_priority: float, activity_count: int) -> str:
        """
        Classify behavior based on priority and activity.
        
        Args:
            avg_priority: Average priority of recent activities
            activity_count: Number of recent activities
            
        Returns:
            Behavior classification
        """
        if avg_priority > 0.8 and activity_count > 10:
            return "high_activity_high_priority"
        elif avg_priority > 0.8:
            return "focused_high_priority"
        elif activity_count > 10:
            return "high_activity_low_priority"
        else:
            return "quiet_observation"
            
    def get_identity_summary(self) -> str:
        """
        Get a human-readable identity summary.
        
        Returns:
            Identity summary string
        """
        summary = self.summarize_self()
        
        identity = f"[Guardian Identity] Project Guardian - Autonomous AI Safety System\n"
        identity += f"  Uptime: {summary['uptime_seconds']:.0f}s\n"
        identity += f"  Memories: {summary['memory_stats']['total_memories']}\n"
        identity += f"  Trust Level: {summary['system_health']['trust_average']:.2f}\n"
        identity += f"  Safety Level: {summary['system_health']['safety_level']}\n"
        identity += f"  Active Tasks: {summary['active_tasks']}\n"
        identity += f"  Last Activity: {summary['last_memory'][:50]}..."
        
        return identity
        
    def get_behavior_report(self) -> str:
        """
        Get a human-readable behavior report.
        
        Returns:
            Behavior report string
        """
        behavior = self.reflect_on_behavior()
        
        report = f"[Guardian Behavior] Recent Activity Analysis\n"
        report += f"  Activity Level: {behavior['recent_activity_count']} recent actions\n"
        report += f"  Focus Area: {behavior['dominant_category']}\n"
        report += f"  Priority Level: {behavior['average_priority']:.2f}\n"
        report += f"  Behavior Pattern: {behavior['behavior_pattern']}\n"
        report += f"  Active Tags: {', '.join(behavior['active_tags'])}\n"
        report += f"  Focus Areas: {', '.join(behavior['focus_areas'])}"
        
        return report
        
    def get_comprehensive_report(self) -> str:
        """
        Get a comprehensive introspection report combining all analyses.
        
        Returns:
            Comprehensive report string
        """
        identity = self.get_identity_summary()
        behavior = self.get_behavior_report()
        patterns = self.introspection.get_memory_patterns()
        health = self.introspection.analyze_memory_health()
        focus = self.introspection.get_focus_analysis(24)
        
        report = f"{identity}\n\n{behavior}\n\n"
        report += f"[Memory Statistics]\n"
        report += f"  Total Memories: {patterns['total_memories']}\n"
        report += f"  Categories: {len(patterns['categories'])}\n"
        report += f"  Memory Density: {patterns['memory_density']:.2f} memories/day\n"
        report += f"  Average Priority: {patterns['average_priority']:.2f}\n\n"
        
        report += f"[Memory Health]\n"
        report += f"  Status: {health['status'].upper()}\n"
        report += f"  Health Score: {health['health_score']:.2f}\n"
        for warning in health['warnings'][:3]:
            report += f"  ⚠ {warning}\n"
        report += f"\n"
        
        report += f"[Focus Analysis - Last 24h]\n"
        report += f"  Primary Focus: {focus['primary_focus']}\n"
        report += f"  Activity Count: {focus['activity_count']}\n"
        report += f"  Priority Trend: {focus['priority_trend']}\n"
        report += f"  Most Active Period: {focus['most_active_period']}\n"
        
        return report