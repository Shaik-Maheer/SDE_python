from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    settings = Settings(
        database_path=tmp_path / "test.db",
        upload_dir=tmp_path / "uploads",
        max_upload_bytes=2 * 1024 * 1024,
        max_archive_members=20,
        max_archive_uncompressed_bytes=10 * 1024 * 1024,
    )
    transport = ASGITransport(app=create_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def sample_kml() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <name>Office</name>
      <Point><coordinates>77.5946,12.9716,0</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Short road</name>
      <LineString><coordinates>77.5946,12.9716,0 77.5956,12.9716,0</coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>Survey plot</name>
      <Polygon><outerBoundaryIs><LinearRing><coordinates>
        77.5946,12.9716,0 77.5956,12.9716,0 77.5956,12.9726,0
        77.5946,12.9726,0 77.5946,12.9716,0
      </coordinates></LinearRing></outerBoundaryIs></Polygon>
    </Placemark>
  </Document>
</kml>"""
