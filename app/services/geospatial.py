from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import pyogrio
from pyproj import CRS
from shapely.geometry import mapping


class ProcessingError(ValueError):
    pass


@dataclass(frozen=True)
class ProcessingResult:
    source_crs: str
    measurement_crs: str
    features: list[dict[str, Any]]


def _read_file(path: Path) -> gpd.GeoDataFrame:
    try:
        layers = pyogrio.list_layers(path)
        if len(layers) == 0:
            raise ProcessingError("The file does not contain a readable layer.")
        if len(layers) > 1:
            raise ProcessingError("Files containing multiple layers are not supported.")
        return pyogrio.read_dataframe(path, layer=layers[0][0])
    except ProcessingError:
        raise
    except Exception as exc:
        raise ProcessingError(f"Unable to read geospatial data: {exc}") from exc


def _measurement_crs(frame: gpd.GeoDataFrame) -> CRS:
    if frame.crs is None:
        raise ProcessingError("The uploaded data has no CRS; measurements would be ambiguous.")

    source = CRS.from_user_input(frame.crs)
    if source.is_projected and all(
        (axis.unit_name or "").lower() in {"metre", "meter"} for axis in source.axis_info
    ):
        return source

    try:
        geographic = frame.to_crs("EPSG:4326")
        projected = geographic.estimate_utm_crs()
    except Exception as exc:
        raise ProcessingError("Could not select an appropriate projected CRS.") from exc
    if projected is None:
        raise ProcessingError("Could not select an appropriate projected CRS for this dataset.")
    return CRS.from_user_input(projected)


def _clean_properties(row: Any, geometry_column: str) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for column, value in row.items():
        if column == geometry_column:
            continue
        if value is None or (not isinstance(value, str | bytes) and _is_nan(value)):
            properties[column] = None
        elif hasattr(value, "item"):
            properties[column] = value.item()
        else:
            properties[column] = value
    return properties


def _is_nan(value: Any) -> bool:
    try:
        return bool(math.isnan(value))
    except (TypeError, ValueError):
        return False


def process_geospatial_file(path: Path) -> ProcessingResult:
    frame = _read_file(path)
    if frame.empty:
        raise ProcessingError("The uploaded file contains no features.")

    source_crs = CRS.from_user_input(frame.crs) if frame.crs else None
    projected_crs = _measurement_crs(frame)
    try:
        projected_geometries = frame.geometry.to_crs(projected_crs)
    except Exception as exc:
        raise ProcessingError("Failed to transform geometries for measurement.") from exc

    features: list[dict[str, Any]] = []
    for index, (_, row) in enumerate(frame.iterrows()):
        geometry = row[frame.geometry.name]
        projected_geometry = projected_geometries.iloc[index]
        geometry_type = geometry.geom_type if geometry is not None else None
        feature: dict[str, Any] = {
            "feature_index": index,
            "source_id": str(row.get("id", index)),
            "geometry_type": geometry_type,
            "geometry": mapping(geometry) if geometry is not None else None,
            "properties": _clean_properties(row, frame.geometry.name),
            "area_square_metres": None,
            "length_metres": None,
            "measurement_status": "NOT_APPLICABLE",
            "measurement_error": None,
        }

        if geometry is None or geometry.is_empty:
            feature["measurement_status"] = "FAILED"
            feature["measurement_error"] = "Feature has no geometry."
        elif not geometry.is_valid:
            feature["measurement_status"] = "FAILED"
            feature["measurement_error"] = "Feature geometry is invalid."
        elif geometry_type in {"Polygon", "MultiPolygon"}:
            feature["area_square_metres"] = float(projected_geometry.area)
            feature["measurement_status"] = "CALCULATED"
        elif geometry_type in {"LineString", "MultiLineString"}:
            feature["length_metres"] = float(projected_geometry.length)
            feature["measurement_status"] = "CALCULATED"

        features.append(feature)

    return ProcessingResult(
        source_crs=source_crs.to_string() if source_crs else "",
        measurement_crs=projected_crs.to_string(),
        features=features,
    )
