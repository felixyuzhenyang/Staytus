"""Transactional, empty-target-only import; never print student records or tokens."""
import math
from pathlib import Path

from sqlalchemy import create_engine, func, select, text

from app.database_migrations import SchemaNotReady, require_current_schema, schema_differences
from app.schema import metadata


def _same_value(name, left, right):
    if name == "vector" and left is not None and right is not None:
        return len(left) == len(right) and all(math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-8)
                                              for a, b in zip(left, right))
    return left == right


def source_compatibility(connection):
    """Only two measured legacy differences are safe; everything else still fails."""
    tolerated = []
    for difference in schema_differences(connection):
        if difference[0] == "remove_table" and difference[1].name == "rule_change_proposals":
            if connection.scalar(text("SELECT count(*) FROM rule_change_proposals")) == 0:
                tolerated.append("empty_legacy_rule_change_proposals_retained_in_sqlite")
                continue
        if isinstance(difference, list) and len(difference) == 1:
            change = difference[0]
            if (change[:4] == ("modify_type", None, "source_capture_state", "retrieval_mode")
                    and getattr(change[-2], "length", None) == 24 and getattr(change[-1], "length", None) == 64):
                length = connection.scalar(text("SELECT max(length(retrieval_mode)) FROM source_capture_state"))
                if length is None or length <= 64:
                    tolerated.append("retrieval_mode_widened_from_24_to_64_without_truncation")
                    continue
        raise SchemaNotReady("Source schema differs from the baseline; no rows were imported.")
    return tolerated


def _copy_into_empty_target(original, target, destination):
    tables = metadata().sorted_tables
    target.execute(text("SET LOCAL lock_timeout = '10s'"))
    target.execute(text("SET LOCAL statement_timeout = '120s'"))
    target.execute(text("SELECT pg_advisory_xact_lock(7823946134021)"))
    names = ", ".join(destination.dialect.identifier_preparer.quote_identifier(table.name) for table in tables)
    target.exec_driver_sql(f"LOCK TABLE {names} IN ACCESS EXCLUSIVE MODE")
    if any(target.scalar(select(func.count()).select_from(table)) for table in tables):
        raise SchemaNotReady("Destination must be empty. Existing data will never be overwritten or merged.")
    counts = {}
    for table in tables:
        rows = [dict(row) for row in original.execute(select(table)).mappings()]
        for start in range(0, len(rows), 100):
            target.execute(table.insert(), rows[start:start + 100])
        restored = [dict(row) for row in target.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
        expected = sorted(rows, key=lambda row: tuple(row[column.name] for column in table.primary_key.columns))
        if len(expected) != len(restored) or any(
            not _same_value(name, left[name], right[name])
            for left, right in zip(expected, restored) for name in left
        ):
            raise SchemaNotReady("Imported values failed verification; the entire import was rolled back.")
        counts[table.name] = len(rows)
    return counts


def transfer_postgres(source, destination):
    """Copy the current PostgreSQL snapshot, never an older SQLite backup.

    Both revisions must match. The source transaction is repeatable-read and
    read-only; the target is empty and locked, and all values must match before
    its one transaction commits. Stop application writers before final cutover.
    """
    if source.dialect.name != "postgresql" or destination.dialect.name != "postgresql":
        raise SchemaNotReady("PostgreSQL transfer requires PostgreSQL at both ends.")
    require_current_schema(source)
    require_current_schema(destination)
    with source.connect().execution_options(isolation_level="REPEATABLE READ") as original, destination.begin() as target:
        original.exec_driver_sql("SET TRANSACTION READ ONLY")
        compatibility = source_compatibility(original)
        counts = _copy_into_empty_target(original, target, destination)
    return {"tables": counts, "source_unchanged": True, "source_snapshot": "repeatable_read_read_only",
            "values_verified": True, "legacy_compatibility": compatibility,
            "vector_float32_tolerance": 1e-6, "transaction_committed": True}


def transfer_sqlite(source_path: Path, destination):
    if destination.dialect.name != "postgresql":
        raise SchemaNotReady("The import destination must be PostgreSQL.")
    source_path = source_path.resolve(strict=True)
    require_current_schema(destination)
    import sqlite3
    source = create_engine("sqlite://", creator=lambda: sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True))
    try:
        with source.connect() as original, destination.begin() as target:
            original.exec_driver_sql("BEGIN")
            compatibility = source_compatibility(original)
            counts = _copy_into_empty_target(original, target, destination)
            original.rollback()
        return {"tables": counts, "source_unchanged": True, "values_verified": True,
                "legacy_compatibility": compatibility,
                "vector_float32_tolerance": 1e-6, "transaction_committed": True}
    finally:
        source.dispose()
