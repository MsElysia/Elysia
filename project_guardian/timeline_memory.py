# project_guardian/timeline_memory.py
# TimelineMemory: SQLite-Backed Event Logging and Timeline
# Based on ElysiaLoop-Core Event Loop Design

import logging
import sqlite3
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class TimelineMemory:
    """
    SQLite-backed event logging and timeline.
    Provides persistent storage for system events, task execution history, and timeline tracking.
    """
    
    def __init__(
        self,
        db_path: str = "data/timeline_memory.db"
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database with required tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    task_id TEXT,
                    summary TEXT,
                    payload TEXT,
                    module TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Task execution history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_seconds REAL,
                    result TEXT,
                    error TEXT,
                    module TEXT,
                    priority INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Timeline index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                ON events(timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_type 
                ON events(event_type)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_history_task_id 
                ON task_history(task_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_history_status 
                ON task_history(status)
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Access columns by name
        try:
            yield conn
        finally:
            conn.close()
    
    def log_event(
        self,
        event_type: str,
        summary: str = "",
        task_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        module: Optional[str] = None
    ) -> int:
        """
        Log an event to the timeline.
        
        Args:
            event_type: Type of event
            summary: Event summary
            task_id: Optional associated task ID
            payload: Optional event payload (will be JSON-encoded)
            module: Optional module name
            
        Returns:
            Event ID
        """
        timestamp = datetime.now().isoformat()
        payload_json = json.dumps(payload) if payload else None
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO events (timestamp, event_type, task_id, summary, payload, module)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (timestamp, event_type, task_id, summary, payload_json, module))
                
                event_id = cursor.lastrowid
                conn.commit()
        
        logger.debug(f"Logged event: {event_type} - {summary}")
        return event_id
    
    def record_task_execution(
        self,
        task_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        module: Optional[str] = None,
        priority: Optional[int] = None
    ) -> int:
        """
        Record task execution in history.
        
        Args:
            task_id: Task ID
            status: Task status
            started_at: Start time
            completed_at: Completion time
            result: Task result (will be JSON-encoded)
            error: Error message if failed
            module: Module name
            priority: Task priority
            
        Returns:
            History record ID
        """
        started_at_str = started_at.isoformat() if started_at else None
        completed_at_str = completed_at.isoformat() if completed_at else None
        
        duration = None
        if started_at and completed_at:
            duration = (completed_at - started_at).total_seconds()
        
        result_json = json.dumps(result) if result is not None else None
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO task_history 
                    (task_id, status, started_at, completed_at, duration_seconds, result, error, module, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (task_id, status, started_at_str, completed_at_str, duration, result_json, error, module, priority))
                
                record_id = cursor.lastrowid
                conn.commit()
        
        logger.debug(f"Recorded task execution: {task_id} - {status}")
        return record_id
    
    def get_events(
        self,
        event_type: Optional[str] = None,
        task_id: Optional[str] = None,
        module: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query events from timeline.
        
        Args:
            event_type: Filter by event type
            task_id: Filter by task ID
            module: Filter by module
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of results
            
        Returns:
            List of event dictionaries
        """
        conditions = []
        params = []
        
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        
        if module:
            conditions.append("module = ?")
            params.append(module)
        
        if start_time:
            conditions.append("timestamp >= ?")
            params.append(start_time.isoformat())
        
        if end_time:
            conditions.append("timestamp <= ?")
            params.append(end_time.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT * FROM events
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)
        
        events = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                for row in cursor.fetchall():
                    event = dict(row)
                    
                    # Parse JSON payload if present
                    if event["payload"]:
                        try:
                            event["payload"] = json.loads(event["payload"])
                        except json.JSONDecodeError:
                            pass
                    
                    events.append(event)
        
        return events
    
    def get_task_history(
        self,
        task_id: Optional[str] = None,
        status: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get task execution history.
        
        Args:
            task_id: Filter by task ID
            status: Filter by status
            module: Filter by module
            limit: Maximum number of results
            
        Returns:
            List of task history records
        """
        conditions = []
        params = []
        
        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if module:
            conditions.append("module = ?")
            params.append(module)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        query = f"""
            SELECT * FROM task_history
            WHERE {where_clause}
            ORDER BY started_at DESC
            LIMIT ?
        """
        params.append(limit)
        
        records = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                
                for row in cursor.fetchall():
                    record = dict(row)
                    
                    # Parse JSON result if present
                    if record["result"]:
                        try:
                            record["result"] = json.loads(record["result"])
                        except json.JSONDecodeError:
                            pass
                    
                    records.append(record)
        
        return records
    
    def get_timeline(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get timeline of events (combined events and task history).
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of results
            
        Returns:
            Combined timeline of events and task history
        """
        # Get events
        events = self.get_events(
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        # Get task history
        if start_time or end_time:
            task_history = []
            # Would need time filtering for task_history
            # For simplicity, just get recent tasks
            task_history = self.get_task_history(limit=limit)
        else:
            task_history = self.get_task_history(limit=limit)
        
        # Combine and sort by timestamp
        timeline = []
        
        for event in events:
            timeline.append({
                "type": "event",
                "timestamp": event["timestamp"],
                "data": event
            })
        
        for task in task_history:
            timeline.append({
                "type": "task",
                "timestamp": task.get("started_at") or task.get("created_at"),
                "data": task
            })
        
        # Sort by timestamp
        timeline.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        
        return timeline[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get timeline memory statistics."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Event statistics
                cursor.execute("SELECT COUNT(*) as count FROM events")
                event_count = cursor.fetchone()["count"]
                
                cursor.execute("SELECT COUNT(DISTINCT event_type) as count FROM events")
                event_types = cursor.fetchone()["count"]
                
                # Task history statistics
                cursor.execute("SELECT COUNT(*) as count FROM task_history")
                task_count = cursor.fetchone()["count"]
                
                cursor.execute("SELECT COUNT(DISTINCT status) as count FROM task_history")
                task_statuses = cursor.fetchone()["count"]
                
                # Recent activity (last 24 hours)
                yesterday = (datetime.now() - timedelta(days=1)).isoformat()
                cursor.execute("SELECT COUNT(*) as count FROM events WHERE timestamp >= ?", (yesterday,))
                recent_events = cursor.fetchone()["count"]
                
                cursor.execute("SELECT COUNT(*) as count FROM task_history WHERE started_at >= ?", (yesterday,))
                recent_tasks = cursor.fetchone()["count"]
                
                return {
                    "total_events": event_count,
                    "event_types": event_types,
                    "total_tasks": task_count,
                    "task_statuses": task_statuses,
                    "recent_events_24h": recent_events,
                    "recent_tasks_24h": recent_tasks,
                    "database_path": str(self.db_path),
                    "database_size_mb": self.db_path.stat().st_size / (1024 * 1024) if self.db_path.exists() else 0
                }
    
    def cleanup_old_events(self, older_than_days: int = 90):
        """
        Clean up events older than specified days.
        
        Args:
            older_than_days: Remove events older than this many days
        """
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Delete old events
                cursor.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
                events_deleted = cursor.rowcount
                
                # Delete old task history
                cursor.execute("DELETE FROM task_history WHERE started_at < ?", (cutoff,))
                tasks_deleted = cursor.rowcount
                
                # Vacuum database to reclaim space
                cursor.execute("VACUUM")
                
                conn.commit()
        
        logger.info(f"Cleaned up {events_deleted} old events and {tasks_deleted} old task records")


# Example usage
if __name__ == "__main__":
    timeline = TimelineMemory()
    
    # Log some events
    timeline.log_event("system_start", "System initialized", module="bootstrap")
    timeline.log_event("task_submitted", "New task submitted", task_id="task_123", module="runtime")
    
    # Record task execution
    timeline.record_task_execution(
        task_id="task_123",
        status="completed",
        started_at=datetime.now() - timedelta(seconds=5),
        completed_at=datetime.now(),
        module="runtime",
        priority=7
    )
    
    # Get events
    events = timeline.get_events(limit=10)
    print(f"Events: {len(events)}")
    
    # Get statistics
    stats = timeline.get_statistics()
    print(f"Statistics: {stats}")

