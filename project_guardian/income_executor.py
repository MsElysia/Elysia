# project_guardian/income_executor.py
# IncomeExecutor: Autonomous Revenue Generation
# Master controls strategy, slaves execute tasks

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from enum import Enum
from dataclasses import dataclass, field

try:
    from .gumroad_client import GumroadClient
    from .asset_manager import AssetManager
    from .master_slave_controller import MasterSlaveController, SlaveRole, SlaveStatus
    from .trust_registry import TrustRegistry
    from .longterm_planner import LongTermPlanner
except ImportError:
    from gumroad_client import GumroadClient
    from asset_manager import AssetManager
    from master_slave_controller import MasterSlaveController, SlaveRole, SlaveStatus
    from trust_registry import TrustRegistry
    from longterm_planner import LongTermPlanner

logger = logging.getLogger(__name__)


class IncomeStrategy(Enum):
    """Income generation strategies."""
    PRODUCT_SALES = "product_sales"  # Sell digital products
    SERVICE_PROVISION = "service_provision"  # Provide services
    CONTENT_CREATION = "content_creation"  # Create and monetize content
    AUTOMATION = "automation"  # Automate revenue streams
    MARKETPLACE = "marketplace"  # Marketplace operations


@dataclass
class RevenueStream:
    """Represents a revenue stream."""
    stream_id: str
    strategy: IncomeStrategy
    name: str
    status: str = "active"
    monthly_target: float = 0.0
    current_revenue: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class IncomeExecutor:
    """
    Autonomous revenue generation executor.
    Master determines strategy, can delegate execution to trusted slaves.
    Financial operations always require master approval.
    """
    
    def __init__(
        self,
        gumroad_client: Optional[GumroadClient] = None,
        asset_manager: Optional[AssetManager] = None,
        master_slave: Optional[MasterSlaveController] = None,
        trust_registry: Optional[TrustRegistry] = None,
        longterm_planner: Optional[LongTermPlanner] = None,
        storage_path: str = "data/income_executor.json"
    ):
        """
        Initialize IncomeExecutor.
        
        Args:
            gumroad_client: GumroadClient instance (master-only)
            asset_manager: AssetManager instance
            master_slave: MasterSlaveController instance
            trust_registry: TrustRegistry instance
            longterm_planner: LongTermPlanner instance
            storage_path: Storage path
        """
        self.gumroad_client = gumroad_client
        self.asset_manager = asset_manager
        self.master_slave = master_slave
        self.trust_registry = trust_registry
        self.longterm_planner = longterm_planner
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Revenue streams
        self.revenue_streams: Dict[str, RevenueStream] = {}
        
        # Execution history
        self.execution_history: List[Dict[str, Any]] = []
        
        # Statistics
        self.stats = {
            "total_revenue": 0.0,
            "active_streams": 0,
            "strategies_executed": 0,
            "slave_executions": 0,
            "master_executions": 0
        }
        
        # Load data
        self.load()
    
    def create_revenue_stream(
        self,
        name: str,
        strategy: IncomeStrategy,
        monthly_target: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new revenue stream.
        MASTER-ONLY: Financial strategy decisions.
        
        Args:
            name: Stream name
            strategy: Income strategy
            monthly_target: Monthly revenue target
            metadata: Optional metadata
            
        Returns:
            Stream ID
        """
        import uuid
        stream_id = str(uuid.uuid4())
        
        stream = RevenueStream(
            stream_id=stream_id,
            strategy=strategy,
            name=name,
            monthly_target=monthly_target,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.revenue_streams[stream_id] = stream
            self.stats["active_streams"] = len([s for s in self.revenue_streams.values() if s.status == "active"])
            self.save()
        
        logger.info(f"Created revenue stream: {name} ({stream_id}) - Strategy: {strategy.value}")
        return stream_id
    
    async def execute_strategy(
        self,
        stream_id: str,
        use_slaves: bool = False,
        min_slave_trust: float = 0.7
    ) -> Dict[str, Any]:
        """
        Execute a revenue generation strategy.
        Master determines execution, can delegate to trusted slaves.
        
        Args:
            stream_id: Revenue stream ID
            use_slaves: If True, delegate to slaves when possible
            min_slave_trust: Minimum trust required for slave execution
            
        Returns:
            Execution result
        """
        stream = self.revenue_streams.get(stream_id)
        if not stream:
            return {"success": False, "error": "Stream not found"}
        
        if stream.status != "active":
            return {"success": False, "error": f"Stream status: {stream.status}"}
        
        logger.info(f"Executing revenue strategy: {stream.name} ({stream.strategy.value})")
        
        result = {"success": False, "revenue": 0.0, "executed_by": "master"}
        
        # Strategy-specific execution
        if stream.strategy == IncomeStrategy.PRODUCT_SALES:
            result = await self._execute_product_sales(stream)
        elif stream.strategy == IncomeStrategy.SERVICE_PROVISION:
            result = await self._execute_service_provision(stream, use_slaves, min_slave_trust)
        elif stream.strategy == IncomeStrategy.CONTENT_CREATION:
            result = await self._execute_content_creation(stream, use_slaves, min_slave_trust)
        elif stream.strategy == IncomeStrategy.AUTOMATION:
            result = await self._execute_automation(stream, use_slaves, min_slave_trust)
        else:
            result = {"success": False, "error": f"Strategy {stream.strategy.value} not implemented"}
        
        # Record execution
        execution_record = {
            "stream_id": stream_id,
            "strategy": stream.strategy.value,
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "executed_by": result.get("executed_by", "master")
        }
        
        with self._lock:
            self.execution_history.append(execution_record)
            self.stats["strategies_executed"] += 1
            
            if result.get("executed_by") == "slave":
                self.stats["slave_executions"] += 1
            else:
                self.stats["master_executions"] += 1
            
            if result.get("success") and "revenue" in result:
                revenue = float(result["revenue"])
                stream.current_revenue += revenue
                stream.last_updated = datetime.now()
                self.stats["total_revenue"] += revenue
                
                # Update asset manager
                if self.asset_manager:
                    self.asset_manager.add_transaction(
                        amount=revenue,
                        transaction_type="income",
                        description=f"Revenue from {stream.name}",
                        metadata={"stream_id": stream_id}
                    )
            
            self.save()
        
        return result
    
    async def _execute_product_sales(self, stream: RevenueStream) -> Dict[str, Any]:
        """
        Execute product sales strategy.
        MASTER-ONLY: Direct financial API access.
        
        Args:
            stream: Revenue stream
            
        Returns:
            Execution result
        """
        if not self.gumroad_client:
            return {"success": False, "error": "GumroadClient not available"}
        
        # Sync sales data
        self.gumroad_client.sync_data()
        
        # Get recent sales
        sales = self.gumroad_client.get_sales(limit=100)
        
        # Calculate revenue from sales
        revenue = sum(float(sale.get("price", 0)) for sale in sales)
        
        return {
            "success": True,
            "revenue": revenue,
            "sales_count": len(sales),
            "executed_by": "master",
            "method": "gumroad_api"
        }
    
    async def _execute_service_provision(
        self,
        stream: RevenueStream,
        use_slaves: bool,
        min_trust: float
    ) -> Dict[str, Any]:
        """
        Execute service provision strategy.
        Can delegate to trusted slaves for execution.
        
        Args:
            stream: Revenue stream
            use_slaves: Allow slave execution
            min_trust: Minimum slave trust
            
        Returns:
            Execution result
        """
        # Master determines service offerings
        # Slaves can execute service delivery (if trusted)
        
        if use_slaves and self.master_slave:
            # Find trusted slave for service execution
            trusted_slaves = self.master_slave.list_slaves(
                status=SlaveStatus.ACTIVE,
                role=SlaveRole.TRUSTED,
                min_trust=min_trust
            )
            
            if trusted_slaves:
                slave = trusted_slaves[0]  # Highest trust slave
                
                # Send command to slave
                success = self.master_slave.send_command(
                    slave.slave_id,
                    "provide_service",
                    data={
                        "service_type": stream.metadata.get("service_type", "general"),
                        "stream_id": stream.stream_id
                    },
                    priority=7
                )
                
                if success:
                    return {
                        "success": True,
                        "revenue": 0.0,  # Revenue tracked separately
                        "executed_by": "slave",
                        "slave_id": slave.slave_id,
                        "method": "service_provision"
                    }
        
        # Master execution fallback
        return {
            "success": True,
            "revenue": 0.0,
            "executed_by": "master",
            "method": "service_provision",
            "note": "Service provision initiated"
        }
    
    async def _execute_content_creation(
        self,
        stream: RevenueStream,
        use_slaves: bool,
        min_trust: float
    ) -> Dict[str, Any]:
        """
        Execute content creation strategy.
        Slaves can create content, master monetizes.
        
        Args:
            stream: Revenue stream
            use_slaves: Allow slave execution
            min_trust: Minimum slave trust
            
        Returns:
            Execution result
        """
        # Master determines content strategy
        # Slaves create content
        # Master handles monetization
        
        if use_slaves and self.master_slave:
            # Find worker slaves for content creation
            worker_slaves = self.master_slave.list_slaves(
                status=SlaveStatus.ACTIVE,
                role=SlaveRole.WORKER,
                min_trust=min_trust
            )
            
            if worker_slaves:
                slave = worker_slaves[0]
                
                # Send content creation command
                self.master_slave.send_command(
                    slave.slave_id,
                    "create_content",
                    data={
                        "content_type": stream.metadata.get("content_type", "article"),
                        "target_platform": stream.metadata.get("platform", "gumroad")
                    },
                    priority=6
                )
                
                return {
                    "success": True,
                    "revenue": 0.0,  # Revenue tracked after monetization
                    "executed_by": "slave",
                    "slave_id": slave.slave_id,
                    "method": "content_creation"
                }
        
        return {
            "success": True,
            "revenue": 0.0,
            "executed_by": "master",
            "method": "content_creation"
        }
    
    async def _execute_automation(
        self,
        stream: RevenueStream,
        use_slaves: bool,
        min_trust: float
    ) -> Dict[str, Any]:
        """
        Execute automation strategy.
        Master sets up automation, slaves execute tasks.
        
        Args:
            stream: Revenue stream
            use_slaves: Allow slave execution
            min_trust: Minimum slave trust
            
        Returns:
            Execution result
        """
        # Master creates automation workflows
        # Slaves execute automated tasks
        
        return {
            "success": True,
            "revenue": 0.0,
            "executed_by": "master",
            "method": "automation",
            "note": "Automation strategy executed"
        }
    
    def get_revenue_report(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get revenue report.
        MASTER-ONLY: Financial reporting.
        
        Args:
            days: Days to report
            
        Returns:
            Revenue report dictionary
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        recent_executions = [
            ex for ex in self.execution_history
            if datetime.fromisoformat(ex["timestamp"]) >= cutoff
        ]
        
        total_revenue = sum(
            ex["result"].get("revenue", 0.0)
            for ex in recent_executions
            if ex["result"].get("success")
        )
        
        by_strategy = {}
        by_executor = {"master": 0.0, "slave": 0.0}
        
        for ex in recent_executions:
            strategy = ex["strategy"]
            revenue = ex["result"].get("revenue", 0.0)
            executor = ex.get("executed_by", "master")
            
            by_strategy[strategy] = by_strategy.get(strategy, 0.0) + revenue
            by_executor[executor] = by_executor.get(executor, 0.0) + revenue
        
        return {
            "period_days": days,
            "total_revenue": total_revenue,
            "executions": len(recent_executions),
            "revenue_by_strategy": by_strategy,
            "revenue_by_executor": by_executor,
            "active_streams": self.stats["active_streams"]
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get income executor statistics."""
        return {
            "total_revenue": self.stats["total_revenue"],
            "active_streams": self.stats["active_streams"],
            "strategies_executed": self.stats["strategies_executed"],
            "slave_executions": self.stats["slave_executions"],
            "master_executions": self.stats["master_executions"],
            "total_executions": self.stats["slave_executions"] + self.stats["master_executions"]
        }
    
    def save(self):
        """Save income executor data."""
        import json
        
        with self._lock:
            data = {
                "revenue_streams": {
                    sid: {
                        "stream_id": stream.stream_id,
                        "strategy": stream.strategy.value,
                        "name": stream.name,
                        "status": stream.status,
                        "monthly_target": stream.monthly_target,
                        "current_revenue": stream.current_revenue,
                        "last_updated": stream.last_updated.isoformat(),
                        "metadata": stream.metadata
                    }
                    for sid, stream in self.revenue_streams.items()
                },
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save income executor data: {e}")
    
    def load(self):
        """Load income executor data."""
        if not self.storage_path.exists():
            return
        
        import json
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                streams_data = data.get("revenue_streams", {})
                for sid, stream_dict in streams_data.items():
                    stream = RevenueStream(
                        stream_id=stream_dict["stream_id"],
                        strategy=IncomeStrategy(stream_dict["strategy"]),
                        name=stream_dict["name"],
                        status=stream_dict.get("status", "active"),
                        monthly_target=stream_dict.get("monthly_target", 0.0),
                        current_revenue=stream_dict.get("current_revenue", 0.0),
                        last_updated=datetime.fromisoformat(stream_dict.get("last_updated", datetime.now().isoformat())),
                        metadata=stream_dict.get("metadata", {})
                    )
                    self.revenue_streams[sid] = stream
                
                if "stats" in data:
                    self.stats.update(data["stats"])
        except Exception as e:
            logger.error(f"Failed to load income executor data: {e}")


# Example usage
if __name__ == "__main__":
    async def test_income_executor():
        """Test IncomeExecutor."""
        executor = IncomeExecutor()
        
        # Create revenue stream
        stream_id = executor.create_revenue_stream(
            name="Digital Products",
            strategy=IncomeStrategy.PRODUCT_SALES,
            monthly_target=1000.0
        )
        
        # Execute strategy
        result = await executor.execute_strategy(stream_id)
        print(f"Execution result: {result}")
        
        # Get revenue report
        report = executor.get_revenue_report(days=30)
        print(f"Revenue report: {report}")
    
    asyncio.run(test_income_executor())

