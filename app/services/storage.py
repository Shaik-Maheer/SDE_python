from __future__ import annotations

import shutil
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from app.config import Settings


class InvalidUpload(ValueError):
    pass


ALLOWED_EXTENSIONS = {".kml", ".zip"}
SHAPEFILE_REQUIRED_EXTENSIONS = {".shp", ".shx", ".dbf"}


def normalized_filename(filename: str | None) -> str:
    if not filename:
        raise InvalidUpload("A filename is required.")
    name = Path(filename).name
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise InvalidUpload("Only .kml files and .zip Shapefile archives are supported.")
    return name


async def save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with destination.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise InvalidUpload(f"Upload exceeds the {max_bytes}-byte size limit.")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    if written == 0:
        destination.unlink(missing_ok=True)
        raise InvalidUpload("The uploaded file is empty.")
    return written


def validate_and_extract_shapefile(archive: Path, output_dir: Path, settings: Settings) -> Path:
    try:
        zip_file = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise InvalidUpload("The uploaded ZIP archive is invalid.") from exc

    with zip_file:
        members = [member for member in zip_file.infolist() if not member.is_dir()]
        if len(members) > settings.max_archive_members:
            raise InvalidUpload("The ZIP archive contains too many files.")
        if sum(member.file_size for member in members) > settings.max_archive_uncompressed_bytes:
            raise InvalidUpload("The uncompressed ZIP archive is too large.")

        for member in members:
            member_path = PurePosixPath(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise InvalidUpload("The ZIP archive contains an unsafe path.")
            if member.flag_bits & 0x1:
                raise InvalidUpload("Encrypted ZIP archives are not supported.")

        shapefiles = [
            member for member in members if Path(member.filename).suffix.lower() == ".shp"
        ]
        if len(shapefiles) != 1:
            raise InvalidUpload("The ZIP archive must contain exactly one .shp file.")

        stem = Path(shapefiles[0].filename).stem.lower()
        sibling_extensions = {
            Path(member.filename).suffix.lower()
            for member in members
            if Path(member.filename).stem.lower() == stem
        }
        missing = SHAPEFILE_REQUIRED_EXTENSIONS - sibling_extensions
        if missing:
            raise InvalidUpload(
                "The Shapefile archive is missing required component(s): "
                + ", ".join(sorted(missing))
            )

        output_dir.mkdir(parents=True, exist_ok=False)
        for member in members:
            target = output_dir.joinpath(*PurePosixPath(member.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)

    return output_dir.joinpath(*PurePosixPath(shapefiles[0].filename).parts)
