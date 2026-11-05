"""Packaging checks must accept new migrated tables and reject real schema drift."""
import pytest
from sqlalchemy import Column, String, Table

from app.container_checks import check_package
from app.schema import metadata


def test_installed_package_migrations_match_models_and_config():
    result = check_package()
    assert result["migration_schema_matches"] and result["school"] == "penn"
    assert result["sources"] > 0 and result["migration_head"]


def test_packaging_rejects_a_registered_table_without_a_migration():
    registered = metadata()
    table = Table("synthetic_unmigrated_packaging_table", registered, Column("id", String, primary_key=True))
    try:
        with pytest.raises(RuntimeError, match="migrations and application models differ"):
            check_package()
    finally:
        registered.remove(table)


def test_packaging_rejects_missing_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr("app.source_registry.CONFIG_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        check_package()
