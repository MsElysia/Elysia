# project_guardian/missions.py
# Mission Management System for Project Guardian

import datetime
from typing import Dict, Any, List, Optional
from .memory import MemoryCore

class MissionDirector:
    """
    Mission management and tracking for Project Guardian.
    Provides goal-oriented task management and progress tracking.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        self.missions = []
        self.mission_counter = 0
        
    def create_mission(self, name: str, goal: str, priority: str = "medium", 
                      deadline: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        """
        Create a new mission.
        
        Args:
            name: Mission name
            goal: Mission goal description
            priority: Priority level (low, medium, high, critical)
            deadline: Optional deadline
            
        Returns:
            Mission dictionary
        """
        mission = {
            "id": self.mission_counter,
            "name": name,
            "goal": goal,
            "priority": priority,
            "created": datetime.datetime.now().isoformat(),
            "deadline": deadline.isoformat() if deadline else None,
            "status": "active",
            "progress": 0.0,
            "log": [],
            "subtasks": []
        }
        
        self.missions.append(mission)
        self.mission_counter += 1
        
        self.memory.remember(
            f"[Mission Created] {name}: {goal} (Priority: {priority})",
            category="mission",
            priority=0.8
        )
        
        return mission
        
    def log_progress(self, mission_name: str, update: str, progress: Optional[float] = None) -> bool:
        """
        Log progress for a mission.
        
        Args:
            mission_name: Name of the mission
            update: Progress update text
            progress: Optional progress percentage (0.0 to 1.0)
            
        Returns:
            True if mission found and updated
        """
        for mission in self.missions:
            if mission["name"] == mission_name:
                mission["log"].append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "update": update
                })
                
                if progress is not None:
                    mission["progress"] = max(0.0, min(1.0, progress))
                    
                self.memory.remember(
                    f"[Mission Progress] {mission_name}: {update}",
                    category="mission",
                    priority=0.7
                )
                return True
                
        return False
        
    def complete_mission(self, mission_name: str, completion_note: str = "") -> bool:
        """
        Mark a mission as complete.
        
        Args:
            mission_name: Name of the mission
            completion_note: Optional completion note
            
        Returns:
            True if mission found and completed
        """
        for mission in self.missions:
            if mission["name"] == mission_name:
                mission["status"] = "complete"
                mission["progress"] = 1.0
                mission["completed"] = datetime.datetime.now().isoformat()
                
                if completion_note:
                    mission["log"].append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "update": f"COMPLETED: {completion_note}"
                    })
                    
                self.memory.remember(
                    f"[Mission Complete] {mission_name}",
                    category="mission",
                    priority=0.9
                )
                return True
                
        return False
        
    def fail_mission(self, mission_name: str, failure_reason: str) -> bool:
        """
        Mark a mission as failed.
        
        Args:
            mission_name: Name of the mission
            failure_reason: Reason for failure
            
        Returns:
            True if mission found and failed
        """
        for mission in self.missions:
            if mission["name"] == mission_name:
                mission["status"] = "failed"
                mission["failed"] = datetime.datetime.now().isoformat()
                mission["failure_reason"] = failure_reason
                
                mission["log"].append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "update": f"FAILED: {failure_reason}"
                })
                
                self.memory.remember(
                    f"[Mission Failed] {mission_name}: {failure_reason}",
                    category="mission",
                    priority=0.8
                )
                return True
                
        return False
        
    def add_subtask(self, mission_name: str, subtask: str, priority: str = "medium") -> bool:
        """
        Add a subtask to a mission.
        
        Args:
            mission_name: Name of the mission
            subtask: Subtask description
            priority: Subtask priority
            
        Returns:
            True if mission found and subtask added
        """
        for mission in self.missions:
            if mission["name"] == mission_name:
                subtask_obj = {
                    "description": subtask,
                    "priority": priority,
                    "status": "pending",
                    "created": datetime.datetime.now().isoformat()
                }
                mission["subtasks"].append(subtask_obj)
                
                self.memory.remember(
                    f"[Subtask Added] {mission_name}: {subtask}",
                    category="mission",
                    priority=0.6
                )
                return True
                
        return False
        
    def complete_subtask(self, mission_name: str, subtask_description: str) -> bool:
        """
        Mark a subtask as complete.
        
        Args:
            mission_name: Name of the mission
            subtask_description: Description of the subtask
            
        Returns:
            True if subtask found and completed
        """
        for mission in self.missions:
            if mission["name"] == mission_name:
                for subtask in mission["subtasks"]:
                    if subtask["description"] == subtask_description:
                        subtask["status"] = "complete"
                        subtask["completed"] = datetime.datetime.now().isoformat()
                        
                        # Update mission progress
                        completed_subtasks = len([s for s in mission["subtasks"] if s["status"] == "complete"])
                        total_subtasks = len(mission["subtasks"])
                        if total_subtasks > 0:
                            mission["progress"] = completed_subtasks / total_subtasks
                            
                        self.memory.remember(
                            f"[Subtask Complete] {mission_name}: {subtask_description}",
                            category="mission",
                            priority=0.6
                        )
                        return True
                        
        return False
        
    def get_active_missions(self) -> List[Dict[str, Any]]:
        """
        Get all active missions.
        
        Returns:
            List of active missions
        """
        return [m for m in self.missions if m["status"] == "active"]
        
    def get_mission_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a mission by name.
        
        Args:
            name: Mission name
            
        Returns:
            Mission dictionary or None
        """
        for mission in self.missions:
            if mission["name"] == name:
                return mission
        return None
        
    def get_mission_stats(self) -> Dict[str, Any]:
        """
        Get mission statistics.
        
        Returns:
            Mission statistics dictionary
        """
        total_missions = len(self.missions)
        active_missions = len([m for m in self.missions if m["status"] == "active"])
        completed_missions = len([m for m in self.missions if m["status"] == "complete"])
        failed_missions = len([m for m in self.missions if m["status"] == "failed"])
        
        # Priority breakdown
        priority_counts = {}
        for mission in self.missions:
            priority = mission["priority"]
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
        return {
            "total_missions": total_missions,
            "active_missions": active_missions,
            "completed_missions": completed_missions,
            "failed_missions": failed_missions,
            "completion_rate": completed_missions / max(1, total_missions),
            "priority_breakdown": priority_counts,
            "recent_missions": [m["name"] for m in self.missions[-5:]]
        }
        
    def get_mission_summary(self) -> str:
        """
        Get a human-readable mission summary.
        
        Returns:
            Mission summary string
        """
        stats = self.get_mission_stats()
        
        summary = f"[Mission Director] Summary\n"
        summary += f"  Total Missions: {stats['total_missions']}\n"
        summary += f"  Active: {stats['active_missions']}\n"
        summary += f"  Completed: {stats['completed_missions']}\n"
        summary += f"  Failed: {stats['failed_missions']}\n"
        summary += f"  Completion Rate: {stats['completion_rate']:.1%}\n"
        
        if stats['active_missions'] > 0:
            summary += f"\nActive Missions:\n"
            for mission in self.get_active_missions():
                progress_pct = mission["progress"] * 100
                summary += f"  • {mission['name']}: {progress_pct:.0f}% complete\n"
                
        return summary
        
    def check_deadlines(self) -> List[Dict[str, Any]]:
        """
        Check for missions approaching or past deadline.
        
        Returns:
            List of missions with deadline issues
        """
        now = datetime.datetime.now()
        deadline_issues = []
        
        for mission in self.missions:
            if mission["status"] == "active" and mission["deadline"]:
                try:
                    deadline = datetime.datetime.fromisoformat(mission["deadline"])
                    time_until_deadline = deadline - now
                    
                    if time_until_deadline.total_seconds() < 0:
                        # Past deadline
                        deadline_issues.append({
                            "mission": mission["name"],
                            "issue": "past_deadline",
                            "days_overdue": abs(time_until_deadline.days)
                        })
                    elif time_until_deadline.days <= 1:
                        # Approaching deadline
                        deadline_issues.append({
                            "mission": mission["name"],
                            "issue": "approaching_deadline",
                            "hours_remaining": time_until_deadline.total_seconds() / 3600
                        })
                        
                except ValueError:
                    continue
                    
        return deadline_issues 