# Geospatial File Measurement API

A production-minded FastAPI service that accepts KML files or zipped Shapefiles, extracts their
features, and calculates metric area and length with correct CRS handling.

## Highlights

- KML and zipped Shapefile (`.shp`, `.shx`, `.dbf`) uploads
- Geometry, CRS, attributes, and source ID extraction for every feature
- Area in square metres for Polygon/MultiPolygon features
- Length in metres for LineString/MultiLineString features
- Point and unsupported geometry types returned without crashing
- Geographic coordinates projected to a locally appropriate UTM CRS before measurement
- SQLite persistence for uploaded-file metadata and feature results
- Upload limits plus ZIP traversal, archive-bomb, and malformed-file protection
- Interactive OpenAPI documentation, Docker image, health check, and automated tests

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for the interactive API. A small example is available at
`examples/sample.kml`.

### Docker

```bash
docker build -t geospatial-measurement-api .
docker run --rm -p 8000:8000 -v geo-data:/data geospatial-measurement-api
```

## API

### Upload and process a file

`POST /api/files/` accepts one multipart field named `file`.

```bash
curl -X POST http://localhost:8000/api/files/ \
  -F "file=@examples/sample.kml"
```

Example response:

```json
{
  "id": "8393b652-e9d9-4214-8eb2-c4345d504c65",
  "filename": "sample.kml",
  "status": "COMPLETED",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32643",
  "error": null,
  "created_at": "2026-10-08T12:00:00Z"
}
```

The request is rejected with a useful `4xx` response if its extension, archive structure, or
geospatial content is invalid.

### Read uploaded-file information

```bash
curl http://localhost:8000/api/files/8393b652-e9d9-4214-8eb2-c4345d504c65/
```

### Read feature measurements

```bash
curl http://localhost:8000/api/files/8393b652-e9d9-4214-8eb2-c4345d504c65/measurements/
```

Each item contains `feature_index`, `source_id`, `geometry_type`, GeoJSON-like `geometry`,
`properties`, and one of `area_square_metres` or `length_metres`. `measurement_status` explains
whether a measurement was calculated, not applicable, or failed for that feature.

### Health check

`GET /health` returns `{"status":"ok"}`.

## Tests and linting

```bash
pytest
ruff check .
```

The test suite covers KML and Shapefile uploads, CRS transformation, Point/LineString/Polygon
behavior, persistence and retrieval, invalid formats, malformed archives, and ZIP path traversal.

## Architecture

```text
app/
├── main.py                 # HTTP routes and application factory
├── config.py               # Environment-backed limits and paths
├── database.py             # SQLite schema and repository operations
├── schemas.py              # Public response contracts
└── services/
    ├── storage.py          # Streaming upload and safe ZIP extraction
    └── geospatial.py       # Parsing, projection, and measurement
```

Processing flow:

1. The upload is streamed to a UUID-scoped directory with a configurable size limit.
2. ZIP archives are inspected and safely extracted; exactly one complete Shapefile is required.
3. Pyogrio/GDAL loads the layer into a GeoDataFrame.
4. The source CRS is inspected. Geographic or non-metric data is transformed to the UTM zone
   estimated from the dataset center; already metric projected data stays in its source CRS.
5. Measurements are calculated from projected geometries and stored with original geometry and
   attributes in SQLite.
6. File metadata and per-feature results are returned by independent read endpoints.

## Design decisions

**Synchronous processing.** The assignment API processes an upload in the request so the result is
immediately consistent and the project has no infrastructure dependency beyond SQLite. Processing
is isolated in a service module, so a production version can enqueue that same function in Celery,
RQ, or a cloud queue and return `202 PROCESSING` without changing the read APIs.

**Dataset-level UTM projection.** Measuring EPSG:4326 coordinates directly would return meaningless
degree units. A local UTM CRS gives accurate metre-based results for normal survey-scale datasets
and is easy to audit. Very large or cross-zone datasets are better served by geodesic measurement
or per-feature projections.

**Original geometry in API responses.** Geometry stays in its source coordinate system so clients
can render it alongside the original attributes. Only the internal measurement copy is projected.

**SQLite.** It is relational, transactional, requires no setup, and is appropriate for an
assignment/single-instance deployment. The repository boundary makes PostgreSQL a straightforward
upgrade for multiple application instances.

**Defensive archive handling.** Shapefiles are multipart datasets commonly delivered as ZIP files.
The service rejects traversal paths, encrypted archives, excessive entry counts, excessive
uncompressed size, missing components, and multiple `.shp` files before extraction.

## Configuration

| Variable | Default | Purpose |
|---|---:|---|
| `DATA_DIR` | `data` | Default database/upload parent |
| `DATABASE_PATH` | `$DATA_DIR/app.db` | SQLite database location |
| `UPLOAD_DIR` | `$DATA_DIR/uploads` | Stored upload location |
| `MAX_UPLOAD_BYTES` | `52428800` | Maximum compressed upload size |
| `MAX_ARCHIVE_MEMBERS` | `100` | Maximum entries in a ZIP |
| `MAX_ARCHIVE_UNCOMPRESSED_BYTES` | `262144000` | Maximum expanded ZIP size |

## Deployment

The repository includes a `Dockerfile` and `render.yaml`. On Render, create a Blueprint from the
repository; the included free demo stores data on the instance's ephemeral filesystem, so data may
reset when the service restarts. For durable production storage, select a paid persistent disk
mounted at `/data` and set `DATA_DIR=/data`, or migrate the repository layer to PostgreSQL/PostGIS.
The same image also works on Fly.io, Railway, ECS, or any container host with a persistent volume.

## Learning and future scope

The key lesson is that spatial measurement is primarily a coordinate-system problem: parsing a
geometry is easy, but selecting a valid metric CRS and preserving original data needs explicit
design. Shapefile archive validation is also part of the domain, not just generic upload handling.

Next steps for higher production load would be asynchronous processing with progress states,
PostgreSQL/PostGIS, object storage for originals, per-feature geodesic measurement for global
datasets, pagination, authentication, rate limiting, malware scanning, and retention policies.
