# Master-Slave Architecture

**Architectural Principle**: One protected master Elysia program that is never shared to untrusted sources. All other instances are limited-functionality slaves.

---

## Core Architecture

### Master Elysia (Protected)
- **Location**: Never deployed, never shared
- **Capabilities**: Full system functionality
- **Security**: Maximum protection, never exposed
- **Purpose**: Central control, full memory, complete personality

### Slave Elysias (Deployable)
- **Location**: Deployed to untrusted targets
- **Capabilities**: Limited functionality based on role
- **Security**: Isolated, can be revoked
- **Purpose**: Distributed execution, task processing, data collection

---

## MasterSlaveController

### Features

**Slave Management:**
- Register new slaves with unique IDs
- Generate secure authentication tokens
- Track slave status (PENDING, ACTIVE, SUSPENDED, REVOKED)
- Role-based permissions (READ_ONLY, WORKER, TRUSTED, ADMIN)

**Security:**
- Secure token-based authentication
- Master token (never shared)
- Slave tokens (unique per slave)
- Separate secure storage for tokens

**Command & Control:**
- Send commands to slaves
- Command queue per slave
- Priority-based command ordering
- Command completion tracking

**Trust Management:**
- Trust scores start at 0.0 for new slaves
- Trust increases with successful performance
- Trust decreases with failures/violations
- Integration with TrustRegistry

**Lifecycle Management:**
- Deploy slaves to targets
- Monitor slave health (heartbeats)
- Suspend slaves (temporary disable)
- Revoke slaves (permanent termination)

---

## SlaveDeployment

### Deployment Methods

1. **SSH Deployment**
   - Secure shell deployment
   - Package transfer
   - Remote execution

2. **Docker Deployment**
   - Container-based deployment
   - Image creation
   - Container orchestration

3. **API Deployment**
   - REST API-based deployment
   - Remote package upload
   - Configuration injection

4. **File Transfer**
   - Direct file copy
   - Manual deployment support

### Slave Package Contents

**What's INCLUDED (Safe to Share):**
- Limited slave code (no master secrets)
- Configuration file (with auth token)
- Startup script
- Dependencies list
- Role-specific functionality

**What's NEVER INCLUDED:**
- Master code
- Master authentication tokens
- Master memory/personality data
- Master trust policies
- Master system architecture

---

## Security Model

### Master Protection
1. **Code Isolation**: Master code never leaves the master system
2. **Token Separation**: Master token stored separately, never shared
3. **Audit Logging**: All master-slave operations logged
4. **Policy Enforcement**: Trust policies apply to all slave commands

### Slave Security
1. **Limited Functionality**: Slaves only have capabilities assigned by master
2. **Token-Based Auth**: Each slave has unique authentication token
3. **Revocable**: Master can instantly revoke any slave
4. **Trust-Based**: Slaves start with zero trust, must earn it

---

## Workflow

### Slave Registration
```
1. Master creates slave registration
   → Generates slave_id and auth_token
   → Sets role and capabilities
   → Registers in TrustRegistry (trust = 0.0)
   
2. Master creates deployment package
   → Limited slave code only
   → Configuration with auth_token
   → Startup scripts
   
3. Master deploys to target
   → SSH/Docker/API deployment
   → Package installation
   → Slave startup
```

### Slave Operation
```
1. Slave authenticates with master
   → Uses auth_token
   → Master validates
   → Updates heartbeat
   
2. Master sends commands
   → Command queued by priority
   → Slave fetches commands
   → Slave executes
   → Slave reports completion
   
3. Master tracks performance
   → Success/failure recording
   → Trust score adjustment
   → Capability updates
```

### Slave Revocation
```
1. Master detects violation or policy breach
   → Trust score drops below threshold
   → Or manual revocation
   
2. Master revokes slave
   → Status set to REVOKED
   → Auth token removed
   → Commands rejected
   
3. Audit logging
   → All revocation events logged
   → Security alerts generated
```

---

## Role-Based Permissions

### READ_ONLY
- Can report status
- Can receive read-only queries
- Cannot execute tasks
- Cannot modify anything

### WORKER
- Can execute assigned tasks
- Can report results
- Cannot access master memory
- Cannot modify system state

### TRUSTED
- Can execute critical tasks
- Higher trust required
- May access limited master data
- Still cannot modify master

### ADMIN (Master Only)
- Full system control
- Can manage other slaves
- Access to all capabilities
- Only for master instance

---

## Integration Points

### With TrustRegistry
- Slaves registered with initial trust = 0.0
- Trust scores updated based on performance
- Trust-based command authorization

### With TrustPolicyManager
- Commands evaluated against policies
- Role-based policy enforcement
- Escalation for critical operations

### With NetworkDiscovery
- Slaves registered as network nodes
- Health monitoring
- Capability discovery

### With TrustAuditLog
- All slave operations logged
- Authentication attempts tracked
- Security events recorded

---

## Usage Example

```python
# Initialize master controller
controller = MasterSlaveController(
    master_id="master_001",
    master_name="Elysia-Master",
    trust_registry=trust_registry,
    trust_policy=trust_policy,
    audit_log=audit_log
)

# Register and deploy a slave
slave_id, auth_token = controller.register_slave(
    name="Worker-Node-1",
    deployment_target="192.168.1.100:8080",
    role=SlaveRole.WORKER,
    capabilities=["ai_generation", "storage"]
)

# Deploy slave
deployment = SlaveDeployment(controller)
await deployment.deploy_slave_to_target(
    slave_id,
    deployment_method=DeploymentMethod.SSH
)

# Send command to slave
controller.send_command(
    slave_id,
    "execute_task",
    data={"task_type": "ai_generation", "prompt": "..."},
    priority=8
)

# Monitor slave
slaves = controller.list_slaves(status=SlaveStatus.ACTIVE)
stats = controller.get_statistics()
```

---

## Security Best Practices

1. **Never Share Master Code**: Only deploy slave packages
2. **Secure Token Storage**: Tokens stored separately from slave data
3. **Audit Everything**: All operations logged for security
4. **Start with Zero Trust**: Slaves earn trust over time
5. **Immediate Revocation**: Revoke compromised slaves instantly
6. **Role Limitation**: Minimal permissions per slave
7. **Network Isolation**: Consider network segmentation
8. **Regular Audits**: Review slave activity regularly

---

## Benefits

1. **Master Protection**: Core code never exposed
2. **Scalability**: Distribute work to multiple slaves
3. **Security**: Revocable, isolated slave instances
4. **Flexibility**: Deploy to various targets
5. **Trust-Based**: Performance-based trust system
6. **Auditability**: Complete audit trail

---

## Future Enhancements

- Encrypted communication channels
- Slave-to-slave communication (with master approval)
- Automated trust-based role promotion
- Multi-master support (if needed)
- Geographic distribution optimization
- Slave capability marketplace

