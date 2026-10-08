from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    upload_dir: Path
    max_upload_bytes: int
    max_archive_members: int
    max_archive_uncompressed_bytes: int

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        return cls(
            database_path=Path(os.getenv("DATABASE_PATH", data_dir / "app.db")),
            upload_dir=Path(os.getenv("UPLOAD_DIR", data_dir / "uploads")),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)),
            max_archive_members=int(os.getenv("MAX_ARCHIVE_MEMBERS", 100)),
            max_archive_uncompressed_bytes=int(
                os.getenv("MAX_ARCHIVE_UNCOMPRESSED_BYTES", 250 * 1024 * 1024)
            ),
        )
