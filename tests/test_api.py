from __future__ import annotations

import io
import zipfile
from pathlib import Path
from uuid import uuid4

import geopandas as gpd
import pytest
from httpx import AsyncClient
from shapely.geometry import Polygon

pytestmark = pytest.mark.anyio


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_upload_kml_and_retrieve_measurements(client: AsyncClient, sample_kml: bytes) -> None:
    upload = await client.post(
        "/api/files/",
        files={"file": ("survey.kml", sample_kml, "application/vnd.google-earth.kml+xml")},
    )

    assert upload.status_code == 201
    file_info = upload.json()
    assert file_info["status"] == "COMPLETED"
    assert file_info["feature_count"] == 3
    assert file_info["crs"] == "EPSG:4326"
    assert file_info["measurement_crs"].startswith("EPSG:326")

    details = await client.get(f"/api/files/{file_info['id']}/")
    assert details.status_code == 200
    assert details.json()["filename"] == "survey.kml"

    response = await client.get(f"/api/files/{file_info['id']}/measurements/")
    assert response.status_code == 200
    measurements = response.json()["measurements"]
    assert len(measurements) == 3

    point = next(item for item in measurements if item["geometry_type"] == "Point")
    line = next(item for item in measurements if item["geometry_type"] == "LineString")
    polygon = next(item for item in measurements if item["geometry_type"] == "Polygon")
    assert point["measurement_status"] == "NOT_APPLICABLE"
    assert 100 < line["length_metres"] < 120
    assert 11_000 < polygon["area_square_metres"] < 13_500


async def test_upload_zipped_shapefile(client: AsyncClient, tmp_path: Path) -> None:
    source_dir = tmp_path / "shape-source"
    source_dir.mkdir()
    shape_path = source_dir / "features.shp"
    frame = gpd.GeoDataFrame(
        {"label": ["plot-a", "plot-b"]},
        geometry=[
            Polygon(
                [
                    (77.59, 12.97),
                    (77.591, 12.97),
                    (77.591, 12.971),
                    (77.59, 12.971),
                ]
            ),
            Polygon(
                [
                    (77.592, 12.97),
                    (77.593, 12.97),
                    (77.593, 12.971),
                    (77.592, 12.971),
                ]
            ),
        ],
        crs="EPSG:4326",
    )
    frame.to_file(shape_path, engine="pyogrio")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        for component in source_dir.iterdir():
            output.write(component, component.name)

    response = await client.post(
        "/api/files/",
        files={"file": ("features.zip", archive.getvalue(), "application/zip")},
    )

    assert response.status_code == 201
    assert response.json()["feature_count"] == 2


async def test_rejects_unsupported_file_type(client: AsyncClient) -> None:
    response = await client.post(
        "/api/files/", files={"file": ("features.geojson", b"{}", "application/geo+json")}
    )

    assert response.status_code == 415
    assert "Only .kml" in response.json()["detail"]


async def test_rejects_invalid_zip(client: AsyncClient) -> None:
    response = await client.post(
        "/api/files/", files={"file": ("features.zip", b"not-a-zip", "application/zip")}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "The uploaded ZIP archive is invalid."


async def test_rejects_zip_path_traversal(client: AsyncClient) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../features.shp", b"shp")
        output.writestr("../features.shx", b"shx")
        output.writestr("../features.dbf", b"dbf")

    response = await client.post(
        "/api/files/", files={"file": ("features.zip", archive.getvalue(), "application/zip")}
    )

    assert response.status_code == 422
    assert "unsafe path" in response.json()["detail"]


async def test_unknown_file_returns_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/api/files/{uuid4()}/")

    assert response.status_code == 404


async def test_invalid_uuid_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/files/not-a-uuid/")

    assert response.status_code == 422
