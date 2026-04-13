#!/usr/bin/env python3
"""
Elysia Trial Run - Runs until 7am
Monitors system, logs activity, and shuts down gracefully at 7am
"""

import sys
import os
import time
import logging
import signal
from datetime import datetime, timedelta
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "core_modules" / "elysia_core_comprehensive"))
sys.path.insert(0, str(Path(__file__).parent / "project_guardian"))

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# Also log to unified autonomous system log
unified_log = Path(__file__).parent / "organized_project" / "data" / "logs" / "unified_autonomous_system.log"
unified_log.parent.mkdir(parents=True, exist_ok=True)

log_file = log_dir / f"elysia_trial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Create handlers
handlers = [
    logging.FileHandler(log_file),
    logging.StreamHandler()
]

# Add unified log handler if file exists or can be created
try:
    handlers.append(logging.FileHandler(unified_log, mode='a'))
except Exception as e:
    print(f"Warning: Could not write to unified log: {e}")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)


class TrialRunManager:
    """Manages trial run until 7am"""
    
    def __init__(self, target_hour: int = 7):
        """
        Initialize trial run manager.
        
        Args:
            target_hour: Target hour to stop (24-hour format, default 7am)
        """
        self.target_hour = target_hour
        self.running = False
        self.start_time = datetime.now()
        self.system = None
        self.status_updates = []
        
        logger.info("="*70)
        logger.info("ELYSIA TRIAL RUN MANAGER")
        logger.info("="*70)
        logger.info(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Target Stop Time: {self._get_target_time().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*70)
    
    def _get_target_time(self) -> datetime:
        """Get target stop time (7am today or tomorrow)"""
        now = datetime.now()
        target = now.replace(hour=self.target_hour, minute=0, second=0, microsecond=0)
        
        # If target time has passed today, use tomorrow
        if target <= now:
            target += timedelta(days=1)
        
        return target
    
    def _time_until_target(self) -> timedelta:
        """Calculate time until target"""
        return self._get_target_time() - datetime.now()
    
    def _should_continue(self) -> bool:
        """Check if should continue running"""
        if not self.running:
            return False
        
        now = datetime.now()
        target = self._get_target_time()
        
        return now < target
    
    def initialize_system(self):
        """Initialize Elysia system"""
        logger.info("Initializing Elysia System...")
        try:
            from run_elysia_unified import UnifiedElysiaSystem
            
            # Configuration with F: drive
            from memory_storage_config import MemoryStorageConfig
            storage_config = MemoryStorageConfig(primary_drive="F:", fallback_local=True)
            storage_info = storage_config.get_config()
            
            logger.info(f"Memory Storage: {storage_info['storage_path']}")
            logger.info(f"Thumb Drive Available: {storage_info['thumb_drive_available']}")
            
            config = {
                "memory_file": str(storage_config.get_memory_file_path()),
                "trust_file": str(storage_config.get_trust_file_path()),
                "tasks_file": str(storage_config.get_tasks_file_path()),
                "hestia": {
                    "hestia_path": r"C:\Users\mrnat\Hestia",
                    "api_url": "http://localhost:8501"
                }
            }
            
            self.system = UnifiedElysiaSystem(config=config)
            self.system.start()
            
            logger.info("✓ Elysia System initialized and started")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to initialize system: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def log_status(self):
        """Log current system status"""
        try:
            status = self.system.get_status() if self.system else {}
            
            status_log = {
                "timestamp": datetime.now().isoformat(),
                "uptime": str(datetime.now() - self.start_time),
                "time_until_target": str(self._time_until_target()),
                "components": status.get("components", {}),
                "integrated_modules": status.get("components", {}).get("integrated_modules", 0)
            }
            
            # Add Hestia status if available
            if self.system and hasattr(self.system, 'modules') and 'hestia_bridge' in self.system.modules:
                hestia_status = self.system.modules['hestia_bridge'].get_status()
                status_log["hestia"] = {
                    "connected": hestia_status.get("connected", False),
                    "data_available": hestia_status.get("data_available", False)
                }
            
            self.status_updates.append(status_log)
            
            logger.info("="*70)
            logger.info("STATUS UPDATE")
            logger.info(f"Uptime: {status_log['uptime']}")
            logger.info(f"Time Until 7am: {status_log['time_until_target']}")
            logger.info(f"Components Active: {status_log['components']}")
            logger.info("="*70)
            
        except Exception as e:
            logger.error(f"Failed to log status: {e}")
    
    def run(self):
        """Run trial until 7am"""
        logger.info("Starting trial run...")
        
        # Initialize system
        if not self.initialize_system():
            logger.error("Failed to initialize system. Exiting.")
            return False
        
        self.running = True
        
        # Setup signal handlers
        def signal_handler(sig, frame):
            logger.info("\nShutdown signal received...")
            self.shutdown()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Main loop
        last_status_log = time.time()
        status_interval = 300  # Log status every 5 minutes
        
        logger.info("="*70)
        logger.info("TRIAL RUN ACTIVE")
        logger.info(f"Will run until: {self._get_target_time().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("Press Ctrl+C to stop early")
        logger.info("="*70)
        
        try:
            while self._should_continue():
                # Periodic status updates
                if time.time() - last_status_log >= status_interval:
                    self.log_status()
                    last_status_log = time.time()
                
                # Sleep for a bit
                time.sleep(10)  # Check every 10 seconds
                
                # Check if approaching target time
                time_remaining = self._time_until_target()
                if time_remaining.total_seconds() <= 60:  # 1 minute warning
                    logger.warning(f"Approaching target time. {time_remaining} remaining.")
            
            # Reached target time
            logger.info("="*70)
            logger.info("TARGET TIME REACHED (7am)")
            logger.info("Shutting down gracefully...")
            logger.info("="*70)
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Error during trial run: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            self.shutdown()
        
        return True
    
    def shutdown(self):
        """Shutdown system gracefully"""
        logger.info("Shutting down system...")
        self.running = False
        
        if self.system:
            try:
                self.system.shutdown()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
        
        # Final status log
        self.log_status()
        
        # Save status updates to file
        try:
            status_file = Path("logs") / f"trial_status_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            import json
            with open(status_file, 'w') as f:
                json.dump({
                    "start_time": self.start_time.isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "duration": str(datetime.now() - self.start_time),
                    "status_updates": self.status_updates
                }, f, indent=2)
            logger.info(f"Status updates saved to {status_file}")
        except Exception as e:
            logger.error(f"Failed to save status: {e}")
        
        logger.info("="*70)
        logger.info("TRIAL RUN COMPLETE")
        logger.info(f"Duration: {datetime.now() - self.start_time}")
        logger.info(f"Status Updates: {len(self.status_updates)}")
        logger.info("="*70)


def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("ELYSIA TRIAL RUN - UNTIL 7AM")
    print("="*70)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Calculate target time
    now = datetime.now()
    target = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    
    print(f"Target Stop Time: {target.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration: {target - now}")
    print("="*70)
    print("\nSystem will:")
    print("  - Initialize Elysia with F: drive memory storage")
    print("  - Connect to Hestia (if available)")
    print("  - Run until 7am")
    print("  - Log status every 5 minutes")
    print("  - Shutdown gracefully at 7am")
    print("\nPress Ctrl+C to stop early\n")
    
    # Create and run manager
    manager = TrialRunManager(target_hour=7)
    success = manager.run()
    
    if success:
        print("\n✓ Trial run completed successfully")
    else:
        print("\n✗ Trial run encountered errors")
        sys.exit(1)


if __name__ == "__main__":
    main()

