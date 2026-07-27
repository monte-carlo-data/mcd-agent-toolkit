"""Minimal local OTLP/HTTP trace receiver.

Listens on ``POST /v1/traces`` (protobuf, optionally gzipped) and appends each
received span as one JSON object per line to ``--output``. Spans are recorded
in a flat, framework-neutral shape that downstream converters
(see ``scripts/sources/otel_spans.py``) can normalize for the compare-trace
skill.

Usage::

    python local_otlp_receiver.py --output run-a.jsonl --port 4318

Send ``SIGINT`` / ``SIGTERM`` to stop. The script flushes the output file and
exits ``0`` on graceful shutdown.

Dependencies: ``opentelemetry-proto`` (already a transitive dep of any
``opentelemetry-sdk`` install).
"""

from __future__ import annotations

import argparse
import gzip
import json
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2
from opentelemetry.proto.common.v1 import common_pb2
from opentelemetry.proto.trace.v1 import trace_pb2

_SPAN_KIND_NAMES = {
    trace_pb2.Span.SPAN_KIND_UNSPECIFIED: "UNSPECIFIED",
    trace_pb2.Span.SPAN_KIND_INTERNAL: "INTERNAL",
    trace_pb2.Span.SPAN_KIND_SERVER: "SERVER",
    trace_pb2.Span.SPAN_KIND_CLIENT: "CLIENT",
    trace_pb2.Span.SPAN_KIND_PRODUCER: "PRODUCER",
    trace_pb2.Span.SPAN_KIND_CONSUMER: "CONSUMER",
}

_STATUS_CODE_NAMES = {
    trace_pb2.Status.STATUS_CODE_UNSET: "UNSET",
    trace_pb2.Status.STATUS_CODE_OK: "OK",
    trace_pb2.Status.STATUS_CODE_ERROR: "ERROR",
}


def _anyvalue_to_python(value: common_pb2.AnyValue) -> Any:
    kind = value.WhichOneof("value")
    if kind == "string_value":
        return value.string_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "int_value":
        return value.int_value
    if kind == "double_value":
        return value.double_value
    if kind == "bytes_value":
        return value.bytes_value.hex()
    if kind == "array_value":
        return [_anyvalue_to_python(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _anyvalue_to_python(kv.value) for kv in value.kvlist_value.values}
    return None


def _attrs_to_dict(attrs) -> dict[str, Any]:
    return {kv.key: _anyvalue_to_python(kv.value) for kv in attrs}


def _span_to_dict(
    span: trace_pb2.Span,
    resource_attrs: dict[str, Any],
    scope_name: str,
) -> dict[str, Any]:
    return {
        "trace_id": span.trace_id.hex(),
        "span_id": span.span_id.hex(),
        "parent_span_id": span.parent_span_id.hex() if span.parent_span_id else None,
        "name": span.name,
        "kind": _SPAN_KIND_NAMES.get(span.kind, "UNSPECIFIED"),
        "start_time_unix_nano": int(span.start_time_unix_nano),
        "end_time_unix_nano": int(span.end_time_unix_nano),
        "duration_ms": (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000.0,
        "status": {
            "code": _STATUS_CODE_NAMES.get(span.status.code, "UNSET"),
            "message": span.status.message,
        },
        "attributes": _attrs_to_dict(span.attributes),
        "events": [
            {
                "name": ev.name,
                "time_unix_nano": int(ev.time_unix_nano),
                "attributes": _attrs_to_dict(ev.attributes),
            }
            for ev in span.events
        ],
        "resource": resource_attrs,
        "scope": scope_name,
    }


class _Handler(BaseHTTPRequestHandler):
    output_path: Path = Path("/dev/null")
    file_lock: threading.Lock = threading.Lock()
    span_count: int = 0

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401
        sys.stderr.write(f"[receiver] {self.address_string()} - {fmt % args}\n")

    def do_POST(self) -> None:
        if self.path != "/v1/traces":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if self.headers.get("Content-Encoding", "").lower() == "gzip":
            try:
                body = gzip.decompress(body)
            except OSError as e:
                sys.stderr.write(f"[receiver] gzip decompress failed: {e}\n")
                self.send_response(400)
                self.end_headers()
                return

        req = trace_service_pb2.ExportTraceServiceRequest()
        try:
            req.ParseFromString(body)
        except Exception as e:  # pragma: no cover
            sys.stderr.write(f"[receiver] proto parse failed: {e}\n")
            self.send_response(400)
            self.end_headers()
            return

        new_spans: list[str] = []
        for rspans in req.resource_spans:
            resource_attrs = _attrs_to_dict(rspans.resource.attributes)
            for sspans in rspans.scope_spans:
                scope_name = sspans.scope.name
                for span in sspans.spans:
                    new_spans.append(
                        json.dumps(_span_to_dict(span, resource_attrs, scope_name))
                    )

        if new_spans:
            with type(self).file_lock:
                with type(self).output_path.open("a") as fh:
                    fh.write("\n".join(new_spans))
                    fh.write("\n")
                type(self).span_count += len(new_spans)
            sys.stderr.write(f"[receiver] wrote {len(new_spans)} spans (total {type(self).span_count})\n")

        resp = trace_service_pb2.ExportTraceServiceResponse()
        body_out = resp.SerializeToString()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", str(len(body_out)))
        self.end_headers()
        self.wfile.write(body_out)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, help="JSONL output file for received spans")
    p.add_argument("--port", type=int, default=4318)
    p.add_argument("--host", default="127.0.0.1")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.touch()
    _Handler.output_path = out_path
    _Handler.file_lock = threading.Lock()
    _Handler.span_count = 0

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    sys.stderr.write(f"[receiver] listening on http://{args.host}:{args.port}/v1/traces\n")
    sys.stderr.write(f"[receiver] writing spans to {out_path}\n")

    stop = threading.Event()

    def _shutdown(signum: int, _frame: Any) -> None:
        sys.stderr.write(f"[receiver] caught signal {signum}, shutting down\n")
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.serve_forever()
    finally:
        server.server_close()
        sys.stderr.write(f"[receiver] stopped; received {_Handler.span_count} spans total\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
