from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from app.config import Settings
from app.database import Database
from app.schemas import FileInformation, HealthResponse, MeasurementsResponse
from app.services.geospatial import ProcessingError, process_geospatial_file
from app.services.storage import (
    InvalidUpload,
    normalized_filename,
    save_upload,
    validate_and_extract_shapefile,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()
    app_settings.upload_dir.mkdir(parents=True, exist_ok=True)
    database = Database(app_settings.database_path)
    database.initialize()

    app = FastAPI(
        title="Geospatial File Measurement API",
        version="1.0.0",
        description=(
            "Upload KML or zipped Shapefiles and calculate metric area/length "
            "after CRS-aware projection."
        ),
    )
    app.state.settings = app_settings
    app.state.database = database

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"message": "Geospatial File Measurement API", "documentation": "/docs"}

    @app.get("/health", response_model=HealthResponse, tags=["System"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/files/",
        response_model=FileInformation,
        status_code=status.HTTP_201_CREATED,
        tags=["Files"],
    )
    async def upload_file(file: Annotated[UploadFile, File()]) -> dict:
        try:
            filename = normalized_filename(file.filename)
        except InvalidUpload as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc

        file_id = str(uuid4())
        file_dir = app_settings.upload_dir / file_id
        stored_path = file_dir / filename
        record = {
            "id": file_id,
            "filename": filename,
            "stored_path": str(stored_path),
            "status": "PROCESSING",
            "created_at": datetime.now(UTC).isoformat(),
        }
        database.create_file(record)

        try:
            await save_upload(file, stored_path, app_settings.max_upload_bytes)
            processing_path: Path = stored_path
            if stored_path.suffix.lower() == ".zip":
                processing_path = validate_and_extract_shapefile(
                    stored_path, file_dir / "extracted", app_settings
                )
            result = process_geospatial_file(processing_path)
            database.insert_features(file_id, result.features)
            database.update_file(
                file_id,
                status="COMPLETED",
                feature_count=len(result.features),
                crs=result.source_crs,
                measurement_crs=result.measurement_crs,
            )
        except InvalidUpload as exc:
            database.update_file(file_id, status="FAILED", error=str(exc))
            shutil.rmtree(file_dir, ignore_errors=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProcessingError as exc:
            database.update_file(file_id, status="FAILED", error=str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            database.update_file(file_id, status="FAILED", error="Unexpected processing failure.")
            raise HTTPException(status_code=500, detail="Unexpected processing failure.") from exc

        return database.get_file(file_id)

    @app.get("/api/files/{file_id}/", response_model=FileInformation, tags=["Files"])
    async def get_file(file_id: UUID) -> dict:
        record = database.get_file(str(file_id))
        if not record:
            raise HTTPException(status_code=404, detail="File not found.")
        return record

    @app.get(
        "/api/files/{file_id}/measurements/",
        response_model=MeasurementsResponse,
        tags=["Files"],
    )
    async def get_measurements(file_id: UUID) -> dict:
        record = database.get_file(str(file_id))
        if not record:
            raise HTTPException(status_code=404, detail="File not found.")
        features = database.list_features(str(file_id))
        return {
            "file_id": str(file_id),
            "status": record["status"],
            "count": len(features),
            "measurements": features,
        }

    return app


app = create_app()
