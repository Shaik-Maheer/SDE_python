from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class FileInformation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    filename: str
    status: Literal["PROCESSING", "COMPLETED", "FAILED"]
    feature_count: int
    crs: str | None = None
    measurement_crs: str | None = None
    error: str | None = None
    created_at: datetime


class FeatureMeasurement(BaseModel):
    feature_index: int
    source_id: str | None = None
    geometry_type: str | None = None
    geometry: dict[str, Any] | None = None
    properties: dict[str, Any]
    area_square_metres: float | None = None
    length_metres: float | None = None
    measurement_status: Literal["CALCULATED", "NOT_APPLICABLE", "FAILED"]
    measurement_error: str | None = None


class MeasurementsResponse(BaseModel):
    file_id: str
    status: str
    count: int
    measurements: list[FeatureMeasurement]


class HealthResponse(BaseModel):
    status: Literal["ok"]
