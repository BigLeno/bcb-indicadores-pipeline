import pytest

from bcb_pipeline.settings import MissingSettingError, WarehouseSettings

ENV = {
    "WAREHOUSE_HOST": "warehouse",
    "WAREHOUSE_DB": "bcb",
    "WAREHOUSE_USER": "bcb",
    "WAREHOUSE_PASSWORD": "segredo",
}


def test_from_env_uses_default_port() -> None:
    settings = WarehouseSettings.from_env(ENV)

    assert settings.port == 5432
    assert "host=warehouse" in settings.conninfo


def test_from_env_requires_password() -> None:
    env = {k: v for k, v in ENV.items() if k != "WAREHOUSE_PASSWORD"}

    with pytest.raises(MissingSettingError, match="WAREHOUSE_PASSWORD"):
        WarehouseSettings.from_env(env)


def test_repr_hides_password() -> None:
    assert "segredo" not in repr(WarehouseSettings.from_env(ENV))
