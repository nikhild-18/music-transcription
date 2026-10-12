"""Read-only localhost audio/annotation reviewer. No uploads or dataset edits."""

import argparse
import io
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import mido
import numpy as np
import soundfile as sf

from bass_pipeline.artifacts import discover
from bass_pipeline.audit import repository_path
from bass_pipeline.core import Note


class Catalog:
    def __init__(self, root: Path, manifest: Path | None = None):
        self.root = root.resolve()
        self.manifest = manifest
        self.refresh()

    def refresh(self):
        if self.manifest is None:
            self.rows, self.report = discover(self.root)
        else:
            self.rows = json.loads(self.manifest.read_text())
            self.report = json.loads((self.manifest.parent / "report.json").read_text())

    def details(self, uid):
        row = next(r for r in self.rows if r.get("uid") == uid)
        result = {"steps": row.get("steps", []), "source": None}
        relative = row.get("source_annotation_path")
        if relative:
            result["path"] = relative
            try:
                path = repository_path(self.root, relative)
                if path.suffix.lower() in (".mid", ".midi"):
                    midi = mido.MidiFile(path)
                    result["source"] = "\n".join(
                        f"track {i}: {message}"
                        for i, track in enumerate(midi.tracks)
                        for message in track[:250]
                    )[:20000]
                    result["notice"] = (
                        "Raw MIDI events, truncated preview; "
                        "times are delta ticks, not seconds."
                    )
                else:
                    with path.open() as stream:
                        result["source"] = stream.read(20000)
                    result["notice"] = (
                        "Source text preview, limited to 20,000 characters."
                    )
            except (OSError, ValueError, EOFError) as error:
                result["error"] = str(error)
        return result

    def clip(self, index: int, start: float, length: float):
        if isinstance(index, str):
            index = next(
                (i for i, r in enumerate(self.rows) if r.get("uid") == index), -1
            )
        if not 0 <= index < len(self.rows):
            raise ValueError("unknown recording")
        if not math.isfinite(start) or start < 0:
            raise ValueError("invalid start")
        if not math.isfinite(length) or not 1 <= length <= 30:
            raise ValueError("clip length must be 1–30 seconds")
        row = self.rows[index]
        audio = repository_path(self.root, row["audio_path"])
        layers = row.get(
            "layers",
            [
                {
                    "id": "reference",
                    "kind": "reference",
                    "path": row.get("annotation_path"),
                    "time_origin_seconds": 0,
                }
            ],
        )
        origin = row.get("audio_origin", 0)
        with sf.SoundFile(audio) as stream:
            frame = round((start - origin) * stream.samplerate)
            if frame < 0 or frame >= len(stream):
                raise ValueError("start is beyond recording")
            stream.seek(frame)
            data = stream.read(round(length * stream.samplerate), always_2d=True)
            rate = stream.samplerate
        start = origin + frame / rate
        end = start + len(data) / rate
        # Display envelope uses the maximum absolute value across channels.
        envelope = np.max(np.abs(data), axis=1)
        peaks = [float(x.max()) for x in np.array_split(envelope, min(1000, len(data)))]
        selected = []
        layer_errors = []
        for layer in layers:
            try:
                notes = json.loads(
                    repository_path(self.root, layer["path"]).read_text()
                )
                for note in notes:
                    Note(
                        **{
                            k: note[k]
                            for k in ("pitch_midi", "onset_seconds", "offset_seconds")
                        }
                    )
            except (OSError, ValueError, TypeError, KeyError) as error:
                layer_errors.append(f"{layer['id']}: {error}")
                continue
            for note in notes:
                Note(
                    **{
                        k: note[k]
                        for k in ("pitch_midi", "onset_seconds", "offset_seconds")
                    }
                )
                n = {
                    **note,
                    "onset_seconds": note["onset_seconds"]
                    + layer["time_origin_seconds"],
                    "offset_seconds": note["offset_seconds"]
                    + layer["time_origin_seconds"],
                    "layer": layer["id"],
                    "kind": layer["kind"],
                }
                if n["onset_seconds"] < end and n["offset_seconds"] > start:
                    selected.append(n)
        output = io.BytesIO()
        sf.write(output, data, rate, format="WAV", subtype="PCM_16")
        return {
            "start": start,
            "end": end,
            "notes": selected,
            "peaks": peaks,
            "sample_rate": rate,
            "layer_errors": layer_errors,
        }, output.getvalue()


def make_handler(catalog: Catalog):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Reject foreign host/origin requests; never serve arbitrary paths.
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                self.send_error(403)
                return
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{expected}":
                self.send_error(403)
                return
            url = urlsplit(self.path)
            try:
                if url.path == "/":
                    body = Path(__file__).with_name("viewer.html").read_bytes()
                    kind = "text/html; charset=utf-8"
                elif url.path == "/catalog":
                    catalog.refresh()
                    body = json.dumps(
                        {"rows": catalog.rows, "report": catalog.report}
                    ).encode()
                    kind = "application/json"
                elif url.path == "/details":
                    body = json.dumps(
                        catalog.details(parse_qs(url.query)["id"][0])
                    ).encode()
                    kind = "application/json"
                elif url.path in ("/clip", "/audio"):
                    query = parse_qs(url.query)
                    meta, wav = catalog.clip(
                        query["id"][0]
                        if catalog.manifest is None
                        else int(query["id"][0]),
                        float(query["start"][0]),
                        float(query["length"][0]),
                    )
                    body = wav if url.path == "/audio" else json.dumps(meta).encode()
                    kind = "audio/wav" if url.path == "/audio" else "application/json"
                else:
                    self.send_error(404)
                    return
            except (
                ValueError,
                KeyError,
                IndexError,
                OSError,
                RuntimeError,
                StopIteration,
            ):
                self.send_error(400, "Unable to read requested clip")
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; "
                "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                "media-src 'self' blob:; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--manifest", help="Optional legacy single-manifest mode")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    catalog = Catalog(
        root, repository_path(root, args.manifest) if args.manifest else None
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(catalog))
    print(
        f"Read-only viewer: http://127.0.0.1:{server.server_port} (Ctrl-C to stop)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
