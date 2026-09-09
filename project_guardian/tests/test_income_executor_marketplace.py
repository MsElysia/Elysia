"""Focused tests for marketplace income execution."""

import asyncio

from project_guardian.income_executor import IncomeExecutor, IncomeStrategy


class _MockGumroadClient:
    def __init__(self, sales):
        self.sales = list(sales)
        self.sync_calls = 0
        self.created_products = []

    def sync_data(self):
        self.sync_calls += 1

    def get_sales(self, limit=100, **kwargs):
        return self.sales[:limit]

    def create_product(self, name, price, description="", metadata=None):
        self.created_products.append(
            {
                "name": name,
                "price": price,
                "description": description,
                "metadata": metadata or {},
            }
        )
        return {"id": "product-123"}


def test_marketplace_strategy_syncs_filtered_sales(tmp_path):
    gumroad_client = _MockGumroadClient(
        [
            {"product_id": "product-123", "price": 15.0},
            {"product_id": "product-999", "price": 40.0},
            {"product_id": "product-123", "price": 10.0},
        ]
    )
    executor = IncomeExecutor(
        gumroad_client=gumroad_client,
        storage_path=str(tmp_path / "income.json"),
    )

    stream_id = executor.create_revenue_stream(
        name="Marketplace Sync",
        strategy=IncomeStrategy.MARKETPLACE,
        metadata={
            "platform": "gumroad",
            "operation": "sync",
            "product_id": "product-123",
            "sales_limit": 10,
        },
    )

    result = asyncio.run(executor.execute_strategy(stream_id))

    assert result["success"] is True
    assert result["method"] == "marketplace_sync"
    assert result["revenue"] == 25.0
    assert result["sales_count"] == 2
    assert gumroad_client.sync_calls == 1


def test_marketplace_strategy_can_create_listing(tmp_path):
    gumroad_client = _MockGumroadClient([])
    executor = IncomeExecutor(
        gumroad_client=gumroad_client,
        storage_path=str(tmp_path / "income.json"),
    )

    stream_id = executor.create_revenue_stream(
        name="New Marketplace Listing",
        strategy=IncomeStrategy.MARKETPLACE,
        metadata={
            "platform": "gumroad",
            "operation": "create_listing",
            "price": 19.99,
            "description": "Autonomous marketplace test product",
            "product_metadata": {"category": "tests"},
        },
    )

    result = asyncio.run(executor.execute_strategy(stream_id))

    assert result["success"] is True
    assert result["method"] == "marketplace_listing"
    assert result["product_id"] == "product-123"
    assert gumroad_client.created_products == [
        {
            "name": "New Marketplace Listing",
            "price": 19.99,
            "description": "Autonomous marketplace test product",
            "metadata": {"category": "tests"},
        }
    ]
    assert executor.revenue_streams[stream_id].metadata["product_id"] == "product-123"
