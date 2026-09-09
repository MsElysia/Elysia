"""Focused tests for IncomeExecutor automation orchestration."""

import asyncio

from project_guardian.asset_manager import AssetManager
from project_guardian.income_executor import IncomeExecutor, IncomeStrategy
from project_guardian.longterm_planner import LongTermPlanner
from project_guardian.master_slave_controller import MasterSlaveController, SlaveRole, SlaveStatus
from project_guardian.trust_registry import TrustRegistry


def test_income_executor_automation_creates_objective_dispatches_slave_and_records_asset(tmp_path):
    trust_registry = TrustRegistry(storage_path=str(tmp_path / "trust.json"))
    master_slave = MasterSlaveController(
        master_id="master-test",
        storage_path=str(tmp_path / "master_slave.json"),
        auth_token_path=str(tmp_path / "slave_tokens.json"),
        trust_registry=trust_registry,
    )
    asset_manager = AssetManager(storage_path=str(tmp_path / "assets.json"))
    planner = LongTermPlanner(storage_path=str(tmp_path / "planner.json"))

    slave_id, _token = master_slave.register_slave(
        name="Automation Worker",
        deployment_target="localhost",
        role=SlaveRole.WORKER,
    )
    slave = master_slave.get_slave(slave_id)
    assert slave is not None
    slave.status = SlaveStatus.ACTIVE
    slave.trust_score = 0.95
    master_slave.save()

    executor = IncomeExecutor(
        master_slave=master_slave,
        asset_manager=asset_manager,
        trust_registry=trust_registry,
        longterm_planner=planner,
        storage_path=str(tmp_path / "income.json"),
    )

    stream_id = executor.create_revenue_stream(
        name="Automation Revenue",
        strategy=IncomeStrategy.AUTOMATION,
        metadata={
            "automation_type": "lead_capture",
            "objective_description": "Capture leads. Qualify promising leads. Prepare a handoff package.",
            "steps": ["capture", "qualify", "handoff"],
            "dispatch_limit": 1,
            "expected_revenue": 12.5,
        },
    )

    result = asyncio.run(executor.execute_strategy(stream_id, use_slaves=True, min_slave_trust=0.7))

    assert result["success"] is True
    assert result["method"] == "automation_orchestration"
    assert result["executed_by"] == "slave"
    assert result["objective_id"]
    assert result["task_ids"]
    assert result["dispatched_slave_ids"] == [slave_id]
    assert result["revenue"] == 12.5

    objective = planner.get_objective(result["objective_id"])
    assert objective is not None
    pending_commands = master_slave.get_pending_commands(slave_id)
    assert pending_commands[0]["command"] == "run_automation"
    assert pending_commands[0]["data"]["stream_id"] == stream_id

    asset = asset_manager.get_asset("master_income")
    assert asset is not None
    assert asset.quantity == 12.5
    assert asset.total_value == 12.5
