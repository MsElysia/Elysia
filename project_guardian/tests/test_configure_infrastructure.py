"""Tests for configure_* helpers on infrastructure modules."""

from types import SimpleNamespace

import pytest

from project_guardian.metacoder import MetaCoder, configure_metacoder
from project_guardian.master_slave_controller import (
    MasterSlaveController,
    configure_master_slave_controller,
)
from project_guardian.network_discovery import NetworkDiscovery, configure_network_discovery
from project_guardian.recovery_vault import RecoveryVault, configure_recovery_vault
from project_guardian.franchise_manager import FranchiseManager, configure_franchise_manager
from project_guardian.task_assignment_engine import (
    TaskAssignmentEngine,
    TrustRegistry as AssignmentTrustRegistry,
    configure_task_assignment_engine,
)
from project_guardian.trust_audit_log import TrustAuditLog, configure_trust_audit_log
from project_guardian.trust_policy_manager import (
    TrustPolicyManager,
    configure_trust_policy_manager,
)
from project_guardian.trust_registry import TrustRegistry, configure_trust_registry


def test_configure_trust_audit_log_returns_explicit_instance(tmp_path):
    log = TrustAuditLog(storage_path=str(tmp_path / "explicit.json"))
    assert configure_trust_audit_log(audit_log=log) is log


def test_configure_trust_audit_log_from_guardian(tmp_path):
    log = TrustAuditLog(storage_path=str(tmp_path / "from_g.json"))
    g = SimpleNamespace(trust_audit_log=log)
    assert configure_trust_audit_log(guardian=g) is log


def test_configure_trust_audit_log_creates_when_missing(tmp_path):
    p = str(tmp_path / "audit.json")
    log = configure_trust_audit_log(storage_path=p)
    assert isinstance(log, TrustAuditLog)
    assert str(log.storage_path) == p


def test_configure_recovery_vault_passes_audit_from_guardian(tmp_path):
    audit = configure_trust_audit_log(storage_path=str(tmp_path / "a.json"))
    g = SimpleNamespace(trust_audit_log=audit)
    vault = configure_recovery_vault(
        vault_path=str(tmp_path / "vault"),
        guardian=g,
    )
    assert isinstance(vault, RecoveryVault)
    assert vault.audit_log is audit


def test_configure_metacoder_resolves_mutation_engine(tmp_path):
    from project_guardian.mutation_engine import MutationEngine

    mut_path = tmp_path / "m.json"
    mut_path.write_text('{"mutations":{}}', encoding="utf-8")
    eng = MutationEngine(storage_path=str(mut_path))
    g = SimpleNamespace(mutation_engine=eng)
    meta_path = tmp_path / "meta.json"
    meta_path.write_text('{"mutation_history":[]}', encoding="utf-8")
    mc = configure_metacoder(
        guardian=g,
        storage_path=str(meta_path),
        project_root=".",
    )
    assert isinstance(mc, MetaCoder)
    assert mc.mutation_engine is eng


def test_configure_trust_registry_from_guardian(tmp_path):
    reg = TrustRegistry(storage_path=str(tmp_path / "tr.json"))
    g = SimpleNamespace(trust_registry=reg)
    assert configure_trust_registry(guardian=g) is reg


def test_configure_trust_registry_creates_when_missing(tmp_path):
    p = str(tmp_path / "registry.json")
    reg = configure_trust_registry(storage_path=p, trust_decay_rate=0.02)
    assert isinstance(reg, TrustRegistry)
    assert str(reg.storage_path) == p
    assert reg.trust_decay_rate == 0.02


def test_configure_trust_policy_manager_from_guardian(tmp_path):
    mgr = TrustPolicyManager(storage_path=str(tmp_path / "tp.json"))
    g = SimpleNamespace(trust_policy_manager=mgr)
    assert configure_trust_policy_manager(guardian=g) is mgr


def test_configure_trust_policy_manager_creates_when_missing(tmp_path):
    p = str(tmp_path / "policy.json")
    mgr = configure_trust_policy_manager(storage_path=p, default_deny=False)
    assert isinstance(mgr, TrustPolicyManager)
    assert str(mgr.storage_path) == p
    assert mgr.default_deny is False


def test_configure_master_slave_controller_from_guardian(tmp_path):
    controller = MasterSlaveController(
        master_id="m1",
        storage_path=str(tmp_path / "ms.json"),
        auth_token_path=str(tmp_path / "tokens.json"),
    )
    g = SimpleNamespace(master_slave_controller=controller)
    assert configure_master_slave_controller(guardian=g) is controller


def test_configure_master_slave_controller_creates_when_missing(tmp_path):
    c = configure_master_slave_controller(
        master_id="m2",
        master_name="Master-2",
        storage_path=str(tmp_path / "master.json"),
        auth_token_path=str(tmp_path / "slave_tokens.json"),
    )
    assert isinstance(c, MasterSlaveController)
    assert c.master_id == "m2"
    assert c.master_name == "Master-2"


def test_configure_franchise_manager_requires_master_slave(tmp_path):
    with pytest.raises(ValueError, match="master_slave"):
        configure_franchise_manager(storage_path=str(tmp_path / "franchise.json"))


def test_configure_franchise_manager_resolves_from_guardian(tmp_path):
    controller = MasterSlaveController(
        master_id="m3",
        storage_path=str(tmp_path / "ms2.json"),
        auth_token_path=str(tmp_path / "tokens2.json"),
    )
    g = SimpleNamespace(master_slave_controller=controller)
    manager = configure_franchise_manager(
        guardian=g,
        storage_path=str(tmp_path / "franchise.json"),
    )
    assert isinstance(manager, FranchiseManager)
    assert manager.master_slave is controller


def test_configure_network_discovery_from_guardian(tmp_path):
    nd = NetworkDiscovery(storage_path=str(tmp_path / "nodes.json"))
    g = SimpleNamespace(network_discovery=nd)
    assert configure_network_discovery(guardian=g) is nd


def test_configure_network_discovery_creates_when_missing(tmp_path):
    nd = configure_network_discovery(
        local_name="ND-Test",
        storage_path=str(tmp_path / "network_nodes.json"),
        discovery_interval=2,
        node_timeout=7,
    )
    assert isinstance(nd, NetworkDiscovery)
    assert nd.local_name == "ND-Test"
    assert nd.discovery_interval == 2
    assert nd.node_timeout == 7


def test_configure_task_assignment_engine_from_guardian(tmp_path):
    class _Runtime:
        def submit_task(self, func, args=(), kwargs=None, priority=5, module="x"):
            return "task-1"

    reg = AssignmentTrustRegistry(storage_path=str(tmp_path / "assignment_trust.json"))
    engine = TaskAssignmentEngine(runtime_loop=_Runtime(), trust_registry=reg)
    g = SimpleNamespace(task_assignment_engine=engine)
    assert configure_task_assignment_engine(guardian=g) is engine


def test_configure_task_assignment_engine_creates_when_missing(tmp_path):
    class _Runtime:
        def submit_task(self, func, args=(), kwargs=None, priority=5, module="x"):
            return "task-1"

    engine = configure_task_assignment_engine(
        runtime_loop=_Runtime(),
        trust_registry_path=str(tmp_path / "assignment_trust_registry.json"),
        min_trust_for_assignment=0.25,
        trial_task_probability=0.3,
    )
    assert isinstance(engine, TaskAssignmentEngine)
    assert isinstance(engine.trust_registry, AssignmentTrustRegistry)
    assert engine.min_trust_for_assignment == 0.25
    assert engine.trial_task_probability == 0.3
