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
from typing import Dict, Any, List, Optional
from pathlib import Path
from enum import Enum

try:
    from .master_slave_controller import MasterSlaveController, SlaveInstance, SlaveRole
except ImportError:
    from master_slave_controller import MasterSlaveController, SlaveInstance, SlaveRole

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
        deployment_config: Optional[Dict[str, Any]] = None
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
        commands = [
            f"scp -P {port} {package_path} {host}:/tmp/elysia_slave.zip",
            f"ssh -p {port} {host} 'mkdir -p /opt/elysia_slave && cd /opt/elysia_slave && unzip -o /tmp/elysia_slave.zip && chmod +x start_slave.sh && ./start_slave.sh {slave.auth_token}'"
        ]
        
        try:
            for cmd in commands:
                # Route through SubprocessRunner gateway (background mode for async-like behavior)
                # Note: We split the shell command into parts for safety
                cmd_parts = cmd.split()
                if len(cmd_parts) < 1:
                    continue
                
                # For shell commands like "scp -P ...", we need to handle them carefully
                # SubprocessRunner doesn't support shell=True, so we need to use the actual command
                # For scp/ssh, we'll use background mode
                result = self.subprocess_runner.run_command_background(
                    command=cmd_parts,
                    caller_identity="SlaveDeployment",
                    task_id=None
                )
                
                # Background mode returns pid, not result - we'd need to poll or wait
                # For now, we'll use synchronous run_command for deployment commands
                # that need to wait for completion
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
            
            logger.info(f"Slave deployed via SSH to {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"SSH deployment error: {e}")
            return False
    
    async def _deploy_via_docker(self, slave: SlaveInstance) -> bool:
        """Deploy via Docker."""
        # Create Docker deployment
        dockerfile = self._create_dockerfile(slave)
        
        # Build and push Docker image
        image_name = f"elysia-slave-{slave.slave_id[:8]}"
        
        commands = [
            f"docker build -t {image_name} -f {dockerfile} .",
            f"docker push {image_name}",
            f"docker run -d --name elysia-slave-{slave.slave_id} -e AUTH_TOKEN={slave.auth_token} {image_name}"
        ]
        
        # Execute Docker commands (route through SubprocessRunner gateway)
        for cmd in commands:
            cmd_parts = cmd.split()
            if len(cmd_parts) < 1:
                continue
            
            sync_result = self.subprocess_runner.run_command(
                command=cmd_parts,
                caller_identity="SlaveDeployment",
                task_id=None,
                timeout=600  # 10 minute timeout for Docker operations
            )
            
            if sync_result.get("returncode", -1) != 0:
                stderr = sync_result.get("stderr", "")
                logger.error(f"Docker command failed: {cmd} - {stderr}")
                return False
        
        logger.info(f"Slave deployed via Docker: {image_name}")
        return True
    
    async def _deploy_via_api(self, slave: SlaveInstance) -> bool:
        """Deploy via API endpoint."""
        # Placeholder for API-based deployment
        # Would POST slave package to deployment API
        logger.info(f"API deployment not yet implemented for {slave.slave_id}")
        return False
    
    async def _deploy_via_file_transfer(self, slave: SlaveInstance) -> bool:
        """Deploy via file transfer."""
        # Placeholder for file transfer deployment
        logger.info(f"File transfer deployment not yet implemented for {slave.slave_id}")
        return False
    
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
            "capabilities": slave.capabilities
        }
        
        config_path = package_dir / "slave_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        # Create startup script
        startup_script = f"""#!/bin/bash
# Elysia Slave Startup Script
# Slave ID: {slave.slave_id}
# Role: {slave.role.value}

export ELYSIA_SLAVE_ID={slave.slave_id}
export ELYSIA_AUTH_TOKEN={slave.auth_token}
export ELYSIA_ROLE={slave.role.value}
export ELYSIA_MASTER_ENDPOINT={self.deployment_config.get("master_endpoint", "localhost:8080")}

python3 -m elysia_slave.main
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

# Copy only slave code (limited functionality)
COPY slave_code/ /app/
COPY slave_config.json /app/config.json
COPY start_slave.sh /app/

RUN chmod +x /app/start_slave.sh

ENV ELYSIA_SLAVE_ID={slave.slave_id}
ENV ELYSIA_ROLE={slave.role.value}

CMD ["/app/start_slave.sh"]
"""
        
        dockerfile_path = Path("deployments") / slave.slave_id / "Dockerfile"
        dockerfile_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        return dockerfile_path

