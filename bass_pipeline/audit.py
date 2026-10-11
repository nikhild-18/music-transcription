"""Stream archive checks without extracting or modifying original datasets."""

import hashlib
import stat
import tarfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath


def repository_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ValueError("path must remain inside the repository")
    return path


def safe_member(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError(f"unsafe archive member: {name!r}")


def inspect_archive(path: Path, expected_md5: str) -> dict:
    md5 = hashlib.md5(usedforsecurity=False)
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    if md5.hexdigest() != expected_md5:
        raise ValueError(f"published checksum mismatch: {path.name}")
    extensions = Counter()
    uncompressed_bytes = 0
    seen = set()

    def record(name: str, size: int) -> None:
        nonlocal uncompressed_bytes
        safe_member(name)
        normalized = str(PurePosixPath(name))
        if normalized in seen:
            raise ValueError(f"duplicate archive member: {name!r}")
        seen.add(normalized)
        extensions[PurePosixPath(name).suffix.lower() or "<none>"] += 1
        uncompressed_bytes += size

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                safe_member(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("archive links are not supported")
                if not member.is_dir():
                    record(member.filename, member.file_size)
    else:
        with tarfile.open(path, "r|gz") as archive:
            for member in archive:
                safe_member(member.name)
                if member.isfile():
                    record(member.name, member.size)
                elif not member.isdir():
                    raise ValueError("archive links/special files are not supported")
    return {
        "checksum_verified": True,
        "sha256": sha256.hexdigest(),
        "compressed_bytes": path.stat().st_size,
        "uncompressed_bytes": uncompressed_bytes,
        "file_count": len(seen),
        "extensions": dict(sorted(extensions.items())),
    }
