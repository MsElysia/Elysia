# project_guardian/slave_deployment.py
# SlaveDeployment: Deploy Limited Slave Instances to Untrusted Targets
# Only deploys limited functionality, never master code
#
# SECURITY: This module is MASTER-ONLY and handles deployment operations.
# It should never be imported or used in slave instances.
# All subprocess operations route through SubprocessRunner gateway.

import logging
import json
import asyncio
import shutil
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from pathlib import Path
from enum import Enum
from datetime import datetime

try:
    from .master_slave_controller import MasterSlaveController, SlaveInstance, SlaveRole, SlaveStatus
except ImportError:
    from master_slave_controller import MasterSlaveController, SlaveInstance, SlaveRole, SlaveStatus

logger = logging.getLogger(__name__)


class DeploymentMethod(Enum):
    """Deployment methods."""
    SSH = "ssh"
    DOCKER = "docker"
    API = "api"
    FILE_TRANSFER = "file_transfer"


class SlaveDeployment:
    """
    Handles deployment of slave Elysia instances to targets.
    Only deploys limited slave code, never master code.
    """
    
    def __init__(
        self,
        master_controller: MasterSlaveController,
        subprocess_runner,  # SubprocessRunner instance (required for gateway)
        slave_code_package: str = "slave_elysia_package.zip",
        deployment_config: Optional[Dict[str, Any]] = None,
        eai_safety: Optional[Any] = None,
    ):
        """
        Initialize SlaveDeployment.
        
        Args:
            master_controller: MasterSlaveController instance
            subprocess_runner: SubprocessRunner instance (required for gateway)
            slave_code_package: Path to slave code package
            deployment_config: Deployment configuration
        """
        self.master_controller = master_controller
        self.subprocess_runner = subprocess_runner
        self.slave_code_package = Path(slave_code_package)
        self.deployment_config = deployment_config or {}
        self.eai_safety = eai_safety
    
    async def deploy_slave_to_target(
        self,
        slave_id: str,
        deployment_method: DeploymentMethod = DeploymentMethod.SSH
    ) -> bool:
        """
        Deploy slave code to target.
        
        Args:
            slave_id: Slave ID to deploy
            deployment_method: Deployment method to use
            
        Returns:
            True if deployment successful
        """
        slave = self.master_controller.get_slave(slave_id)
        if not slave:
            logger.error(f"Slave {slave_id} not found")
            return False

        eai_assessment = self._evaluate_eai_deployment(slave, deployment_method)
        if eai_assessment is not None:
            slave.metadata["eai_safety_deployment"] = eai_assessment.to_dict()
            decision = eai_assessment.decision.value
            eai_approved = bool(
                slave.metadata.get("human_approved")
                or getattr(eai_assessment, "approval_verified", False)
            )
            if decision in {"deny", "review"} and not eai_approved:
                logger.warning(
                    "EAI safety gate blocked slave deployment %s: %s",
                    slave_id,
                    eai_assessment.reasoning,
                )
                self._record_deployment_result(
                    slave,
                    deployment_method,
                    False,
                    {"error": f"eai_safety_{decision}", "assessment": eai_assessment.to_dict()},
                )
                return False
        
        logger.info(f"Deploying slave {slave.name} to {slave.deployment_target} using {deployment_method.value}")
        
        try:
            if deployment_method == DeploymentMethod.SSH:
                return await self._deploy_via_ssh(slave)
            elif deployment_method == DeploymentMethod.DOCKER:
                return await self._deploy_via_docker(slave)
            elif deployment_method == DeploymentMethod.API:
                return await self._deploy_via_api(slave)
            elif deployment_method == DeploymentMethod.FILE_TRANSFER:
                return await self._deploy_via_file_transfer(slave)
            else:
                logger.error(f"Unknown deployment method: {deployment_method}")
                return False
        except Exception as e:
            logger.error(f"Deployment failed for slave {slave_id}: {e}")
            return False
    
    async def _deploy_via_ssh(self, slave: SlaveInstance) -> bool:
        """Deploy via SSH."""
        # Parse target
        parts = slave.deployment_target.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 22
        
        # Create deployment package
        package_path = self._create_deployment_package(slave)
        if not package_path:
            return False
        
        # SSH deployment commands
        remote_dir = f"/tmp/elysia_slave_{slave.slave_id}"
        commands = [
            ["scp", "-P", str(port), "-r", str(package_path), f"{host}:{remote_dir}"],
            [
                "ssh",
                "-p",
                str(port),
                host,
                (
                    "mkdir -p /opt/elysia_slave && "
                    "rm -rf /opt/elysia_slave/* && "
                    f"cp -r {remote_dir}/* /opt/elysia_slave/ && "
                    "chmod +x /opt/elysia_slave/start_slave.sh && "
                    "cd /opt/elysia_slave && ./start_slave.sh"
                ),
            ],
        ]
        
        try:
            for cmd_parts in commands:
                sync_result = self.subprocess_runner.run_command(
                    command=cmd_parts,
                    caller_identity="SlaveDeployment",
                    task_id=None,
                    timeout=300  # 5 minute timeout for deployment
                )
                
                if sync_result.get("returncode", -1) != 0:
                    stderr = sync_result.get("stderr", "")
                    logger.error(f"SSH command failed: {stderr}")
                    return False
            
            self._record_deployment_result(slave, DeploymentMethod.SSH, True, {"target": f"{host}:{port}"})
            logger.info(f"Slave deployed via SSH to {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"SSH deployment error: {e}")
            self._record_deployment_result(slave, DeploymentMethod.SSH, False, {"error": str(e)})
            return False
    
    async def _deploy_via_docker(self, slave: SlaveInstance) -> bool:
        """Deploy via Docker."""
        # Create Docker deployment
        dockerfile = self._create_dockerfile(slave)
        
        # Build and push Docker image
        image_name = f"elysia-slave-{slave.slave_id[:8]}"
        
        commands = [
            ["docker", "build", "-t", image_name, "-f", str(dockerfile), "."],
            ["docker", "push", image_name],
            [
                "docker",
                "run",
                "-d",
                "--name",
                f"elysia-slave-{slave.slave_id}",
                "-e",
                f"AUTH_TOKEN={slave.auth_token}",
                image_name,
            ],
        ]

        # Execute Docker commands (route through SubprocessRunner gateway)
        for cmd_parts in commands:
            sync_result = self.subprocess_runner.run_command(
                command=cmd_parts,
                caller_identity="SlaveDeployment",
                task_id=None,
                timeout=600  # 10 minute timeout for Docker operations
            )
            
            if sync_result.get("returncode", -1) != 0:
                stderr = sync_result.get("stderr", "")
                logger.error(f"Docker command failed: {cmd_parts} - {stderr}")
                self._record_deployment_result(
                    slave,
                    DeploymentMethod.DOCKER,
                    False,
                    {"stderr": stderr[:800]},
                )
                return False
        
        self._record_deployment_result(slave, DeploymentMethod.DOCKER, True, {"image_name": image_name})
        logger.info(f"Slave deployed via Docker: {image_name}")
        return True
    
    async def _deploy_via_api(self, slave: SlaveInstance) -> bool:
        """Deploy via API endpoint."""
        package_path = self._create_deployment_package(slave)
        if not package_path:
            return False

        target = str(self.deployment_config.get("api_base_url") or slave.deployment_target).strip()
        if not target:
            logger.error("API deployment target missing for %s", slave.slave_id)
            return False

        if not target.startswith(("http://", "https://")):
            target = f"http://{target}"

        deploy_path = str(self.deployment_config.get("api_deploy_path", "/deploy") or "/deploy")
        url = target.rstrip("/") + (deploy_path if deploy_path.startswith("/") else f"/{deploy_path}")

        files: Dict[str, str] = {}
        for file_path in package_path.rglob("*"):
            if file_path.is_file():
                files[str(file_path.relative_to(package_path)).replace("\\", "/")] = file_path.read_text(encoding="utf-8")

        payload = {
            "slave_id": slave.slave_id,
            "name": slave.name,
            "role": slave.role.value,
            "auth_token": slave.auth_token,
            "capabilities": slave.capabilities,
            "files": files,
        }

        def _post_package() -> bool:
            request = urllib.request.Request(
                url=url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(
                request,
                timeout=int(self.deployment_config.get("api_timeout", 30) or 30),
            ) as response:
                body = response.read().decode("utf-8", errors="replace").strip()
                if response.status not in (200, 201, 202):
                    raise RuntimeError(f"Unexpected deployment status: {response.status}")
                if body:
                    try:
                        parsed = json.loads(body)
                    except json.JSONDecodeError:
                        return True
                    if isinstance(parsed, dict) and parsed.get("success") is False:
                        raise RuntimeError(str(parsed.get("error", "API deployment rejected")))
                return True

        try:
            success = await asyncio.to_thread(_post_package)
        except (urllib.error.URLError, RuntimeError, OSError) as e:
            logger.error("API deployment error for %s: %s", slave.slave_id, e)
            self._record_deployment_result(slave, DeploymentMethod.API, False, {"error": str(e)})
            return False

        self._record_deployment_result(slave, DeploymentMethod.API, success, {"url": url})
        return success
    
    async def _deploy_via_file_transfer(self, slave: SlaveInstance) -> bool:
        """Deploy via file transfer."""
        package_path = self._create_deployment_package(slave)
        if not package_path:
            return False

        destination_root = self.deployment_config.get("file_transfer_root") or slave.deployment_target
        destination = Path(destination_root)
        if "://" in str(destination_root):
            logger.error("File transfer target must be a filesystem path, got: %s", destination_root)
            return False

        try:
            if destination.exists() and destination.is_file():
                raise ValueError(f"Destination path is a file: {destination}")

            destination.mkdir(parents=True, exist_ok=True)
            target_dir = destination / f"elysia_slave_{slave.slave_id}"
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(package_path, target_dir)
        except Exception as e:
            logger.error("File transfer deployment error for %s: %s", slave.slave_id, e)
            self._record_deployment_result(
                slave,
                DeploymentMethod.FILE_TRANSFER,
                False,
                {"error": str(e)},
            )
            return False

        self._record_deployment_result(
            slave,
            DeploymentMethod.FILE_TRANSFER,
            True,
            {"target_dir": str(target_dir)},
        )
        return True

    def _evaluate_eai_deployment(
        self,
        slave: SlaveInstance,
        deployment_method: DeploymentMethod,
    ) -> Optional[Any]:
        """Run optional EAI safety gate before a concrete deployment."""
        eai_safety = self.eai_safety or getattr(self.master_controller, "eai_safety", None)
        if eai_safety is None:
            return None

        try:
            return eai_safety.assess_action(
                action_type=f"deploy_slave_{deployment_method.value}",
                actor="SlaveDeployment",
                target=slave.deployment_target,
                metadata={
                    "slave_id": slave.slave_id,
                    "name": slave.name,
                    "role": slave.role.value,
                    "capabilities": slave.capabilities,
                    "deployment_method": deployment_method.value,
                    "autonomous": True,
                    "human_approved": slave.metadata.get("human_approved", False),
                    "request_id": slave.metadata.get("request_id"),
                    "review_id": slave.metadata.get("review_id"),
                    "approval_id": slave.metadata.get("approval_id"),
                    "controlled_evolution": slave.metadata.get("controlled_evolution", False),
                    "lineage_parent_ids": slave.metadata.get("lineage_parent_ids", []),
                },
                lineage_parent_ids=slave.metadata.get("lineage_parent_ids", []),
            )
        except Exception as e:
            logger.warning("EAI safety assessment failed for deployment %s: %s", slave.slave_id, e)
            return None

    def _record_deployment_result(
        self,
        slave: SlaveInstance,
        method: DeploymentMethod,
        success: bool,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist deployment result back onto the master controller."""
        details = details or {}
        controller_slave = self.master_controller.get_slave(slave.slave_id)
        if controller_slave is None:
            return

        with self.master_controller._lock:
            was_active = controller_slave.status == SlaveStatus.ACTIVE
            controller_slave.metadata["last_deployment"] = {
                "method": method.value,
                "success": success,
                "details": details,
                "completed_at": datetime.now().isoformat(),
            }
            if success:
                controller_slave.status = SlaveStatus.ACTIVE
                controller_slave.deployed_at = datetime.now()
                controller_slave.last_heartbeat = datetime.now()
                if not was_active:
                    self.master_controller.stats["active_slaves"] += 1
            else:
                controller_slave.status = SlaveStatus.ERROR
            self.master_controller.save()
    
    def _create_deployment_package(self, slave: SlaveInstance) -> Optional[Path]:
        """
        Create deployment package with limited slave code.
        NEVER includes master code - only limited slave functionality.
        
        Args:
            slave: Slave instance
            
        Returns:
            Path to package file
        """
        # This would create a zip package containing:
        # - Limited slave code (no master secrets)
        # - Configuration with auth token
        # - Startup script
        # - Required dependencies list
        
        package_dir = Path("deployments") / slave.slave_id
        package_dir.mkdir(parents=True, exist_ok=True)
        
        # Create slave configuration
        config = {
            "slave_id": slave.slave_id,
            "master_endpoint": self.deployment_config.get("master_endpoint", "localhost:8080"),
            "auth_token": slave.auth_token,
            "role": slave.role.value,
            "capabilities": slave.capabilities,
            "api_port": int(self.deployment_config.get("api_port", 8080) or 8080),
        }
        
        config_path = package_dir / "slave_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Create startup script
        slave_runtime = """#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def _load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="slave_config.json")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = _load_config(str(config_path))
    status_path = config_path.with_name("slave_status.json")
    commands_path = config_path.with_name("slave_commands.json")
    port = int(config.get("api_port", 8080))

    def _status_payload() -> dict:
        return {
            "slave_id": config.get("slave_id"),
            "role": config.get("role"),
            "capabilities": config.get("capabilities", []),
            "status": "active",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/health", "/status"):
                payload = _status_payload()
                status_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                self._write_json(payload)
                return
            if self.path == "/commands":
                if commands_path.exists():
                    payload = json.loads(commands_path.read_text(encoding="utf-8"))
                else:
                    payload = []
                self._write_json({"commands": payload})
                return
            self._write_json({"error": "not_found"}, status=404)

        def do_POST(self):
            if self.path != "/commands":
                self._write_json({"error": "not_found"}, status=404)
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            commands = []
            if commands_path.exists():
                commands = json.loads(commands_path.read_text(encoding="utf-8"))
            commands.append(
                {
                    "received_at": datetime.utcnow().isoformat() + "Z",
                    "payload": payload,
                }
            )
            commands_path.write_text(json.dumps(commands, indent=2), encoding="utf-8")
            self._write_json({"success": True, "queued": True, "count": len(commands)}, status=202)

        def log_message(self, format, *args):
            return

    status_path.write_text(json.dumps(_status_payload(), indent=2), encoding="utf-8")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

        runtime_path = package_dir / "slave_runtime.py"
        with open(runtime_path, "w", encoding="utf-8") as f:
            f.write(slave_runtime)

        startup_script = f"""#!/bin/bash
# Elysia Slave Startup Script
# Slave ID: {slave.slave_id}
# Role: {slave.role.value}

export ELYSIA_SLAVE_ID={slave.slave_id}
export ELYSIA_AUTH_TOKEN={slave.auth_token}
export ELYSIA_ROLE={slave.role.value}
export ELYSIA_MASTER_ENDPOINT={self.deployment_config.get("master_endpoint", "localhost:8080")}

python3 slave_runtime.py --config slave_config.json
"""
        
        script_path = package_dir / "start_slave.sh"
        with open(script_path, 'w') as f:
            f.write(startup_script)
        script_path.chmod(0o755)
        
        # Package would be created here
        # In production: zip package_dir to package.zip
        
        logger.info(f"Created deployment package for slave {slave.slave_id}")
        return package_dir
    
    def _create_dockerfile(self, slave: SlaveInstance) -> Path:
        """Create Dockerfile for slave deployment."""
        dockerfile_content = f"""FROM python:3.9-slim

WORKDIR /app

# Copy generated slave package
COPY deployments/{slave.slave_id}/ /app/

RUN chmod +x /app/start_slave.sh

ENV ELYSIA_SLAVE_ID={slave.slave_id}
ENV ELYSIA_ROLE={slave.role.value}
EXPOSE 8080

CMD ["/app/start_slave.sh"]
"""
        
        dockerfile_path = Path("deployments") / slave.slave_id / "Dockerfile"
        dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        return dockerfile_path

