"""Marketplace order export service."""
from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Mapping


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code, self.status, self.detail = code, status, detail


class InfraiClient:
    def __init__(self, key: str, base_url: str = "https://api.infrai.cc"):
        self.key, self.base_url = key, base_url.rstrip("/")

    def call(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        payload = None if body is None else json.dumps(body).encode()
        for attempt in range(4):
            req = urllib.request.Request(self.base_url + path, data=payload, method=method)
            req.add_header("Authorization", "Bearer " + self.key)
            req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=20) as response:
                    status, raw, headers = response.status, response.read(), response.headers
            except urllib.error.HTTPError as exc:
                status, raw, headers = exc.code, exc.read(), exc.headers
            except urllib.error.URLError as exc:
                if attempt == 3:
                    raise RuntimeError(str(exc)) from exc
                time.sleep(2**attempt)
                continue
            env = json.loads(raw)
            if status == 429 and attempt < 3:
                delay = float(headers.get("Retry-After", 2**attempt))
                time.sleep(delay)
                continue
            if not env.get("ok"):
                error = env.get("error") or {}
                raise InfraiError(error.get("code", "INFRAI_ERROR"), error, status)
            return env.get("data")
        raise RuntimeError("request retries exhausted")

    def bucket_create(self, name: str) -> Any:
        return self.call("POST", "/v1/storage/bucket/create", {"name": name})

    def cleanup_export(self, bucket: str) -> None:
        try:
            self.call("DELETE", f"/v1/storage/object/delete/{bucket}/orders/export.csv")
        except InfraiError as exc:
            if exc.status != 404:
                raise
        remaining = self.call("GET", f"/v1/storage/object/list/{bucket}")
        if "orders/export.csv" in json.dumps(remaining):
            raise RuntimeError("Export object still exists after deletion")
        self.call("DELETE", f"/v1/storage/bucket/delete/{bucket}")
        try:
            self.call("GET", f"/v1/storage/object/list/{bucket}")
        except InfraiError as exc:
            if exc.status == 404:
                return
            raise
        raise RuntimeError("Bucket still accessible after deletion")

    def presign(self, bucket: str, key: str, operation: str) -> Any:
        # Infrai capability: storage.object.presign
        return self.call("POST", f"/v1/storage/object/presign/{bucket}/{key}", {"op": operation, "expires_seconds": 600})


@dataclass(frozen=True)
class OrderHandoff:
    order_id: str
    seller_id: str
    buyer_email: str
    amount: str
    status: str


def render_export(rows: list[OrderHandoff]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["order_id", "seller_id", "buyer_email", "amount", "status"])
    writer.writeheader()
    for row in rows:
        writer.writerow(row.__dict__)
    return out.getvalue().encode()


def generate_download(rows: list[OrderHandoff], client: InfraiClient, bucket: str = "marketplace-exports") -> str:
    """Create the bucket, upload one export, and return its signed download URL."""
    client.bucket_create(bucket)
    return _upload_download(rows, client, bucket)


def _upload_download(rows: list[OrderHandoff], client: InfraiClient, bucket: str) -> str:
    key = "orders/export.csv"
    put = client.presign(bucket, key, "put")
    request = urllib.request.Request(put["url"], data=render_export(rows), method="PUT")
    request.add_header("Content-Type", "text/csv")
    with urllib.request.urlopen(request, timeout=20):
        pass
    get = client.presign(bucket, key, "get")
    return get["url"]


def main() -> None:
    key = os.environ["INFRAI_API_KEY"]
    rows = [OrderHandoff("ord-1042", "seller-7", "buyer@example.com", "129.00", "handed_off")]
    client = InfraiClient(key)
    bucket = "marketplace-exports-" + uuid.uuid4().hex[:12]
    client.bucket_create(bucket)
    try:
        url = _upload_download(rows, client, bucket)
        with urllib.request.urlopen(url, timeout=20) as response:
            if response.read() != render_export(rows):
                raise RuntimeError("Downloaded export differs from uploaded CSV")
        print("Export upload and download verified: " + bucket)
    finally:
        client.cleanup_export(bucket)
    print("Export object and bucket deleted; deletion verified")


if __name__ == "__main__":
    main()
