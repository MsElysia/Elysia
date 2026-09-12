"""Focused tests for distributed discovery and slave deployment completion work."""

import asyncio
import json
import os
import socket
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from project_guardian.master_slave_controller import MasterSlaveController, SlaveRole, SlaveStatus
from project_guardian.network_discovery import NetworkDiscovery, NodeStatus
from project_guardian.slave_deployment import DeploymentMethod, SlaveDeployment
from project_guardian.trust_registry import TrustRegistry


def test_network_discovery_scans_seeded_tcp_target(tmp_path):
    storage_path = tmp_path / "network_nodes.json"
    discovery = NetworkDiscovery(storage_path=str(storage_path))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]

    try:
        discovered = asyncio.run(
            discovery.discover_nodes(
                address_range="127.0.0.1",
                port_range=(port, port),
            )
        )
    finally:
        server.close()

    assert discovered
    node = discovery.get_node(discovered[0])
    assert node is not None
    assert node.address == "127.0.0.1"
    assert node.port == port
    assert node.status == NodeStatus.ACTIVE


def test_master_slave_controller_deploys_without_running_loop(tmp_path):
    trust_registry = TrustRegistry(storage_path=str(tmp_path / "trust_registry.json"))
    controller = MasterSlaveController(
        master_id="test-master",
        storage_path=str(tmp_path / "master_slaves.json"),
        auth_token_path=str(tmp_path / "slave_tokens.json"),
        trust_registry=trust_registry,
    )
    slave_id, _token = controller.register_slave(
        name="Deploy Test Slave",
        deployment_target="127.0.0.1:8080",
        role=SlaveRole.WORKER,
    )

    old_delay = os.environ.get("ELYSIA_SLAVE_SIMULATED_DEPLOY_DELAY_SEC")
    os.environ["ELYSIA_SLAVE_SIMULATED_DEPLOY_DELAY_SEC"] = "0.01"
    try:
        assert controller.deploy_slave(slave_id) is True
        time.sleep(0.2)
    finally:
        if old_delay is None:
            os.environ.pop("ELYSIA_SLAVE_SIMULATED_DEPLOY_DELAY_SEC", None)
        else:
            os.environ["ELYSIA_SLAVE_SIMULATED_DEPLOY_DELAY_SEC"] = old_delay

    slave = controller.get_slave(slave_id)
    assert slave is not None
    assert slave.status == SlaveStatus.ACTIVE
    assert slave.deployed_at is not None


def test_slave_deployment_file_transfer_copies_real_package(tmp_path):
    trust_registry = TrustRegistry(storage_path=str(tmp_path / "trust_registry.json"))
    controller = MasterSlaveController(
        master_id="test-master",
        storage_path=str(tmp_path / "master_slaves.json"),
        auth_token_path=str(tmp_path / "slave_tokens.json"),
        trust_registry=trust_registry,
    )
    target_root = tmp_path / "deploy_target"
    slave_id, _token = controller.register_slave(
        name="File Transfer Slave",
        deployment_target=str(target_root),
        role=SlaveRole.WORKER,
    )

    deployment = SlaveDeployment(
        master_controller=controller,
        subprocess_runner=MagicMock(),
        deployment_config={"file_transfer_root": str(target_root)},
    )

    assert asyncio.run(
        deployment.deploy_slave_to_target(
            slave_id,
            deployment_method=DeploymentMethod.FILE_TRANSFER,
        )
    )

    copied_dir = target_root / f"elysia_slave_{slave_id}"
    assert (copied_dir / "slave_config.json").exists()
    assert (copied_dir / "start_slave.sh").exists()
    assert (copied_dir / "slave_runtime.py").exists()
    slave = controller.get_slave(slave_id)
    assert slave is not None
    assert slave.status == SlaveStatus.ACTIVE
    assert slave.metadata["last_deployment"]["method"] == "file_transfer"


def test_slave_deployment_api_posts_package_payload(tmp_path):
    trust_registry = TrustRegistry(storage_path=str(tmp_path / "trust_registry.json"))
    controller = MasterSlaveController(
        master_id="test-master",
        storage_path=str(tmp_path / "master_slaves.json"),
        auth_token_path=str(tmp_path / "slave_tokens.json"),
        trust_registry=trust_registry,
    )
    slave_id, _token = controller.register_slave(
        name="API Deploy Slave",
        deployment_target="deploy.example:9000",
        role=SlaveRole.WORKER,
    )

    deployment = SlaveDeployment(
        master_controller=controller,
        subprocess_runner=MagicMock(),
        deployment_config={
            "api_base_url": "http://deploy.example:9000",
            "api_deploy_path": "/deploy",
        },
    )

    captured_requests = []

    class _FakeResponse:
        status = 201

        def read(self):
            return b'{"success": true}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(request, timeout=30):
        captured_requests.append(request)
        return _FakeResponse()

    with patch("project_guardian.slave_deployment.urllib.request.urlopen", side_effect=_fake_urlopen):
        assert asyncio.run(
            deployment.deploy_slave_to_target(
                slave_id,
                deployment_method=DeploymentMethod.API,
            )
        )

    assert captured_requests
    request = captured_requests[0]
    assert request.full_url == "http://deploy.example:9000/deploy"
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["slave_id"] == slave_id
    assert "slave_runtime.py" in payload["files"]
    slave = controller.get_slave(slave_id)
    assert slave is not None
    assert slave.metadata["last_deployment"]["method"] == "api"
