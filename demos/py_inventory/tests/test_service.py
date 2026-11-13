import pytest

from inventory import OutOfStockError, UnknownSkuError


def test_reserve_and_ship(service, repo) -> None:
    service.reserve("BLT-0001", 120)
    assert repo.stock_item("BLT-0001").available == 380
    service.ship("BLT-0001", 100)
    item = repo.stock_item("BLT-0001")
    assert (item.on_hand, item.reserved) == (400, 20)


def test_reserve_rejects_overselling_and_unknown(service) -> None:
    with pytest.raises(OutOfStockError):
        service.reserve("GEA-0100", 4)
    with pytest.raises(UnknownSkuError):
        service.reserve("ZZZ-9999", 1)


def test_receive_and_release(service, repo) -> None:
    service.receive("NUT-0002", 60)
    service.reserve("NUT-0002", 10)
    service.release("NUT-0002", 25)
    item = repo.stock_item("NUT-0002")
    assert (item.on_hand, item.reserved) == (100, 0)
