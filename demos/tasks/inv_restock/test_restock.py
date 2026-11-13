"""Benchmark acceptance: RestockRequest + InventoryService.request_restock (pydantic 2.9.2 installed).

Deprecated pydantic APIs (v1 style) raise here: warnings are errors in this module."""
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from inventory import InventoryService, UnknownSkuError
from inventory.models import RestockRequest

pytestmark = pytest.mark.filterwarnings("error")


def test_defaults_and_payload() -> None:
    before = datetime.now(timezone.utc)
    r = RestockRequest(sku="BLT-0001", quantity=250, supplier_id="ACME")
    assert r.requested_at.tzinfo is not None and r.requested_at >= before
    assert r.note is None
    payload = r.to_payload()
    json.dumps(payload)  # must be JSON-serialisable as returned
    assert payload["sku"] == "BLT-0001" and payload["quantity"] == 250 and payload["supplier_id"] == "ACME"
    assert datetime.fromisoformat(payload["requested_at"]) == r.requested_at


def test_validation() -> None:
    with pytest.raises(ValidationError):
        RestockRequest(sku="blt-1", quantity=1, supplier_id="ACME")
    for bad in (0, -5, 10001):
        with pytest.raises(ValidationError):
            RestockRequest(sku="BLT-0001", quantity=bad, supplier_id="ACME")
    with pytest.raises(ValidationError):
        RestockRequest(sku="BLT-0001", quantity=1, supplier_id="ACME", note="x" * 201)
    assert RestockRequest(sku="BLT-0001", quantity=1, supplier_id="ACME", note="  urgent  ").note == "urgent"


def test_service_request_restock(service: InventoryService) -> None:
    r = service.request_restock("GEA-0100", 4, note="  for order 17 ")
    assert isinstance(r, RestockRequest)
    assert (r.sku, r.quantity, r.supplier_id, r.note) == ("GEA-0100", 4, "GLOBEX", "for order 17")
    with pytest.raises(UnknownSkuError):
        service.request_restock("ZZZ-9999", 1)
    with pytest.raises(ValueError):
        service.request_restock("OLD-0009", 1)  # inactive product
