"""Test API source (Phase 2, ADR-0015): paged JSON orders behind a bearer token, standard library only.

GET /v1/orders?page=1&page_size=100[&updated_date=YYYY-MM-DD]
  -> {"data": [...], "meta": {"page": 1, "page_size": 100, "total": 250}}
1000 orders spread over 2026-10-20..2026-10-29, so a date filter returns about 100. Answers HTTP 429 to every 7th
request, so the fetch task's retries are exercised too. GET /v1/health needs no token.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TOKEN = os.environ["API_TOKEN"]
STATUSES = ["new", "paid", "shipped", "cancelled"]
ORDERS = [
    {
        "order_id": i,
        "customer_id": 1 + i % 97,
        "amount": round(10 + (i * 7.31) % 490, 2),
        "status": STATUSES[i % len(STATUSES)],
        "updated_date": (date(2026, 10, 20) + timedelta(days=i % 10)).isoformat(),
        "items": [{"sku": f"SKU-{i % 13:03d}", "qty": 1 + i % 3}],
    }
    for i in range(1, 1001)
]
requests_served = 0


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: object, headers: dict[str, str] | None = None) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        global requests_served
        url = urlparse(self.path)
        if url.path == "/v1/health":
            return self._send(200, {"status": "ok"})
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self._send(401, {"error": "missing or wrong bearer token"})
        if url.path != "/v1/orders":
            return self._send(404, {"error": "not found"})
        requests_served += 1
        if requests_served % 7 == 0:
            return self._send(429, {"error": "slow down"}, {"Retry-After": "1"})
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        page, size = int(query.get("page", 1)), min(int(query.get("page_size", 100)), 500)
        rows = [o for o in ORDERS if o["updated_date"] == query["updated_date"]] if "updated_date" in query else ORDERS
        meta = {"page": page, "page_size": size, "total": len(rows)}
        self._send(200, {"data": rows[(page - 1) * size : page * size], "meta": meta})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
