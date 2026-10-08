from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS uploaded_files (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    status TEXT NOT NULL,
    feature_count INTEGER NOT NULL DEFAULT 0,
    crs TEXT,
    measurement_crs TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT NOT NULL REFERENCES uploaded_files(id) ON DELETE CASCADE,
    feature_index INTEGER NOT NULL,
    source_id TEXT,
    geometry_type TEXT,
    geometry_json TEXT,
    properties_json TEXT NOT NULL,
    area_square_metres REAL,
    length_metres REAL,
    measurement_status TEXT NOT NULL,
    measurement_error TEXT,
    UNIQUE(file_id, feature_index)
);

CREATE INDEX IF NOT EXISTS idx_features_file_id ON features(file_id);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def create_file(self, record: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO uploaded_files
                    (id, filename, stored_path, status, created_at)
                VALUES (:id, :filename, :stored_path, :status, :created_at)
                """,
                record,
            )

    def update_file(self, file_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self.connect() as connection:
            connection.execute(
                f"UPDATE uploaded_files SET {assignments} WHERE id = ?",  # noqa: S608
                [*fields.values(), file_id],
            )

    def get_file(self, file_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM uploaded_files WHERE id = ?", (file_id,)
            ).fetchone()
        return dict(row) if row else None

    def insert_features(self, file_id: str, features: list[dict[str, Any]]) -> None:
        rows = [
            {
                **feature,
                "file_id": file_id,
                "geometry_json": json.dumps(feature["geometry"]),
                "properties_json": json.dumps(feature["properties"], default=str),
            }
            for feature in features
        ]
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO features (
                    file_id, feature_index, source_id, geometry_type, geometry_json,
                    properties_json, area_square_metres, length_metres,
                    measurement_status, measurement_error
                ) VALUES (
                    :file_id, :feature_index, :source_id, :geometry_type, :geometry_json,
                    :properties_json, :area_square_metres, :length_metres,
                    :measurement_status, :measurement_error
                )
                """,
                rows,
            )

    def list_features(self, file_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT feature_index, source_id, geometry_type, geometry_json,
                       properties_json, area_square_metres, length_metres,
                       measurement_status, measurement_error
                FROM features WHERE file_id = ? ORDER BY feature_index
                """,
                (file_id,),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["geometry"] = (
                json.loads(item.pop("geometry_json")) if item["geometry_json"] else None
            )
            item["properties"] = json.loads(item.pop("properties_json"))
            results.append(item)
        return results
