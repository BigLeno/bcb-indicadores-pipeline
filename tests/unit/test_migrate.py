from pathlib import Path

import pytest

from bcb_pipeline.migrate import Migration, MigrationError, discover

REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "sql" / "migrations"


def test_discover_orders_by_version(tmp_path: Path) -> None:
    (tmp_path / "002_b.sql").write_text("SELECT 2;")
    (tmp_path / "010_c.sql").write_text("SELECT 10;")
    (tmp_path / "001_a.sql").write_text("SELECT 1;")

    assert [m.version for m in discover(tmp_path)] == ["001", "002", "010"]


def test_discover_rejects_bad_name(tmp_path: Path) -> None:
    (tmp_path / "1_sem_zeros.sql").write_text("SELECT 1;")

    with pytest.raises(MigrationError, match="fora do padrão"):
        discover(tmp_path)


def test_discover_rejects_duplicated_version(tmp_path: Path) -> None:
    (tmp_path / "001_a.sql").write_text("SELECT 1;")
    (tmp_path / "001_b.sql").write_text("SELECT 1;")

    with pytest.raises(MigrationError, match="duplicada"):
        discover(tmp_path)


def test_checksum_changes_with_content() -> None:
    original = Migration("001", "a", "SELECT 1;")
    edited = Migration("001", "a", "SELECT 2;")

    assert original.checksum != edited.checksum


def test_repository_migrations_are_valid() -> None:
    migrations = discover(REPO_MIGRATIONS)

    assert migrations, "nenhuma migration encontrada em sql/migrations"
    assert migrations[0].version == "001"
