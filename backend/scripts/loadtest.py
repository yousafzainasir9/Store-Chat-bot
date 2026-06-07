"""Async load test for the chat endpoint (Phase 8).

Drives concurrent ``/chat`` requests and reports throughput + latency
percentiles against the SLO targets (DEVELOPMENT_PLAN.md §8.3). Point it at a
running backend; in demo mode it exercises the full pipeline with no paid API.

Usage:
    python -m scripts.loadtest --url http://localhost:8000 --concurrency 20 --requests 500
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

_QUESTIONS = [
    "How long does shipping take?",
    "What is your return policy?",
    "Do you have any dresses?",
    "What size am I if my bust is 36 inches?",
    "Recommend a jacket under $80",
    "Is the black dress in stock?",
]

# SLO targets to compare against (§8.3).
_SLO_P95_FIRST_TOKEN_S = 2.5


async def _one(client: httpx.AsyncClient, url: str, q: str) -> float:
    start = time.perf_counter()
    async with client.stream("POST", f"{url}/chat", json={"message": q}) as resp:
        resp.raise_for_status()
        async for _ in resp.aiter_lines():
            break  # measure time-to-first-byte/line (proxy for first token)
    return time.perf_counter() - start


async def _worker(client: httpx.AsyncClient, url: str, n: int, idx: int, out: list[float]) -> None:
    for i in range(n):
        q = _QUESTIONS[(idx + i) % len(_QUESTIONS)]
        out.append(await _one(client, url, q))


async def run(url: str, concurrency: int, requests: int) -> None:
    per = max(1, requests // concurrency)
    latencies: list[float] = []
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        await asyncio.gather(*[_worker(client, url, per, i, latencies) for i in range(concurrency)])
    elapsed = time.perf_counter() - started

    latencies.sort()
    p50 = statistics.median(latencies)
    p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
    p99 = latencies[min(len(latencies) - 1, int(0.99 * len(latencies)))]
    qps = len(latencies) / elapsed if elapsed else 0.0

    print(f"\nRequests: {len(latencies)}  Concurrency: {concurrency}  Elapsed: {elapsed:.2f}s")
    print(f"Throughput: {qps:.1f} req/s")
    print(f"Latency  p50={p50 * 1000:.0f}ms  p95={p95 * 1000:.0f}ms  p99={p99 * 1000:.0f}ms")
    verdict = "PASS" if p95 <= _SLO_P95_FIRST_TOKEN_S else "FAIL"
    print(f"SLO p95 first-token < {_SLO_P95_FIRST_TOKEN_S}s: {verdict}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat load test")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--requests", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(run(args.url, args.concurrency, args.requests))


if __name__ == "__main__":
    main()
