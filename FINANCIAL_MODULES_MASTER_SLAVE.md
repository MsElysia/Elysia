# Financial Modules - Master-Slave Architecture

**Critical Principle**: Financial operations are MASTER-ONLY. Master controls all financial strategy and sensitive operations. Slaves execute limited tasks under strict control.

---

## Architecture

### Master Financial Control
- **All Financial APIs**: Master only (Gumroad, payment processors, etc.)
- **Revenue Strategy**: Master determines strategies
- **Asset Management**: Master tracks all assets
- **Financial Reporting**: Master generates reports

### Slave Financial Tasks
- **Limited Execution**: Slaves execute tasks, don't access financial APIs
- **Service Provision**: Trusted slaves can provide services
- **Content Creation**: Worker slaves create content (master monetizes)
- **Task Execution**: Slaves execute revenue-generating tasks assigned by master

---

## Financial Modules

### ✅ GumroadClient (`project_guardian/gumroad_client.py`)
**Status**: MASTER-ONLY  
**Purpose**: Gumroad API integration for product sales

**Master Functions**:
- List products (MASTER-ONLY)
- Get sales data (MASTER-ONLY)
- Create/update products (MASTER-ONLY)
- Revenue statistics (MASTER-ONLY)
- Access token management (MASTER-ONLY)

**Never Deployed to Slaves**: This module handles direct financial API access and is never included in slave packages.

---

### ✅ IncomeExecutor (`project_guardian/income_executor.py`)
**Status**: Master Controls, Slaves Execute  
**Purpose**: Autonomous revenue generation

**Master Functions**:
- Create revenue streams (MASTER-ONLY)
- Determine revenue strategies (MASTER-ONLY)
- Execute product sales (MASTER-ONLY - uses GumroadClient)
- Financial reporting (MASTER-ONLY)
- Asset tracking integration (MASTER-ONLY)

**Slave Delegation**:
- Service provision: Trusted slaves can provide services
- Content creation: Worker slaves create content (master monetizes)
- Automation tasks: Slaves execute automated revenue tasks

**Security**:
- Slaves never access financial APIs directly
- All revenue flows through master
- Master tracks all financial transactions
- Slave execution requires minimum trust (default 0.7)

---

### ✅ AssetManager (`project_guardian/asset_manager.py`)
**Status**: MASTER-ONLY  
**Purpose**: Financial asset tracking

**Master Functions**:
- Track all assets (MASTER-ONLY)
- Record transactions (MASTER-ONLY)
- Generate financial reports (MASTER-ONLY)
- Asset valuation (MASTER-ONLY)

**Never Deployed to Slaves**: Contains sensitive financial data.

---

### ✅ RevenueSharing (`project_guardian/revenue_sharing.py`)
**Status**: CRITICAL - Secure Revenue Sharing  
**Purpose**: Slaves earn money, master automatically receives share

**How It Works**:
1. **Slave Reports Earnings**: Slave calls `report_slave_earnings()` with payment proof
2. **Master Verification**: Master verifies payment proof and approves transaction
3. **Share Calculation**: Automatic calculation of master/slave shares
4. **Distribution**: Funds distributed to master (via AssetManager) and slave accounts
5. **Trust Rewards**: Successful earnings increase slave trust score

**Security Features**:
- Payment proof verification required
- Master approval before distribution
- Escrow support (optional)
- Complete audit trail
- Trust-based verification

**Master Share**:
- Default: 30% (configurable per slave)
- Higher trust slaves can have lower share rates
- Master share goes to AssetManager
- Slave share tracked separately

**Example Flow**:
```
Slave earns $100 → Reports with payment proof → Master verifies → 
Master receives $30 (30%) → Slave receives $70 (70%) → 
Slave trust increases → AssetManager updated
```

---

## Security Model

### Financial API Protection
1. **Master Only Access**: Financial APIs (Gumroad, payment processors) only accessible from master
2. **Token Security**: API tokens stored securely, never in slave packages
3. **No Direct Access**: Slaves cannot directly call financial APIs
4. **Audit Trail**: All financial operations logged

### Revenue Flow
```
Slave executes task → Reports to master → Master records revenue → AssetManager updated
```

### Trust Requirements
- **Product Sales**: Master-only (requires API access)
- **Service Provision**: Requires TRUSTED role (min trust 0.7)
- **Content Creation**: Requires WORKER role (min trust 0.5)
- **Automation**: Requires WORKER role (min trust 0.6)

---

## Usage Example

```python
# MASTER SETUP
# Initialize financial modules (master-only)
gumroad = GumroadClient(access_token="...")
asset_manager = AssetManager()
income_executor = IncomeExecutor(
    gumroad_client=gumroad,
    asset_manager=asset_manager,
    master_slave=master_slave_controller
)

# Create revenue stream (master-only)
stream_id = income_executor.create_revenue_stream(
    name="Digital Products",
    strategy=IncomeStrategy.PRODUCT_SALES,
    monthly_target=1000.0
)

# Execute strategy (master determines, can delegate to slaves)
result = await income_executor.execute_strategy(
    stream_id,
    use_slaves=True,  # Allow slave execution for applicable strategies
    min_slave_trust=0.7
)

# Master tracks all revenue
report = income_executor.get_revenue_report(days=30)
```

---

## Slave Deployment Considerations

### What's NEVER in Slave Packages
- GumroadClient code
- API access tokens
- AssetManager code
- Financial API credentials
- Revenue strategy logic

### What Slaves CAN Do
- Execute assigned revenue tasks
- Create content (master monetizes)
- Provide services (trusted slaves)
- Report task completion
- Request new tasks

---

## Integration with Master-Slave Controller

```python
# Master creates revenue strategy
stream_id = income_executor.create_revenue_stream(...)

# Master can delegate to slaves
if strategy == IncomeStrategy.SERVICE_PROVISION:
    # Find trusted slave
    trusted_slaves = master_slave.list_slaves(
        status=SlaveStatus.ACTIVE,
        role=SlaveRole.TRUSTED,
        min_trust=0.7
    )
    
    if trusted_slaves:
        # Send command to slave
        master_slave.send_command(
            trusted_slaves[0].slave_id,
            "provide_service",
            data={"service_type": "...", "stream_id": stream_id}
        )
```

---

## Financial Security Checklist

- ✅ Financial APIs only in master
- ✅ API tokens stored separately
- ✅ Slaves cannot access financial APIs
- ✅ All revenue flows through master
- ✅ Complete audit trail
- ✅ Trust-based slave authorization
- ✅ Master approval for all financial operations

---

## Future Enhancements

- Multi-payment processor support (Stripe, PayPal, etc.)
- Automated revenue optimization
- Predictive revenue forecasting
- Tax calculation and reporting
- Multi-currency support
- Financial goal tracking

