from app.services.trade_service import TradeService

_service: TradeService | None = None


def set_service(service_instance: TradeService) -> None:
    global _service
    _service = service_instance


def get_service() -> TradeService:
    if _service is None:
        raise RuntimeError("TradeService not initialised. Call set_service() at startup.")
    return _service
