from app.tools.factory import build_tool_registry


def test_registry_contains_only_labmate_tools() -> None:
    class _Retriever:
        pass

    registry = build_tool_registry(_Retriever())  # type: ignore[arg-type]
    assert set(registry.names()) == {
        "search_lab_equipment",
        "get_lab_equipment_status",
        "check_lab_equipment_availability",
        "request_lab_equipment_reservation",
        "create_lab_maintenance_ticket",
        "search_knowledge",
    }
