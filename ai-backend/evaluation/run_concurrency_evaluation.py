#!/usr/bin/env python3
"""Measure API-level concurrent RAG stability without storing medical data."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_QUESTION = "知识库中提到 PPGL 的生化检查和影像检查应如何结合？"


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def request_once(index: int, endpoint: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            response.read()
            status = response.status
            error = ""
    except HTTPError as exc:
        status = exc.code
        error = exc.read().decode("utf-8", errors="replace")[:300]
    except URLError as exc:
        status = 0
        error = f"network error: {exc.reason}"
    except TimeoutError:
        status = 0
        error = "timeout"
    return {"request_id": index, "http_status": status, "wall_time_s": round(time.perf_counter() - started, 3), "error": error}


def run_level(concurrency: int, repeats: int, endpoint: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    count = concurrency * repeats
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(request_once, index + 1, endpoint, headers, payload, timeout) for index in range(count)]
        for future in as_completed(futures):
            rows.append(future.result())
    elapsed = time.perf_counter() - started
    timings = [item["wall_time_s"] for item in rows]
    success = sum(item["http_status"] == 200 for item in rows)
    return {
        "concurrency": concurrency,
        "request_count": count,
        "elapsed_s": round(elapsed, 3),
        "requests_per_second": round(count / elapsed, 3) if elapsed else 0,
        "success": success,
        "success_rate": success / count if count else 0,
        "average_wall_time_s": round(statistics.mean(timings), 3) if timings else 0,
        "p50_wall_time_s": round(percentile(timings, 0.5), 3),
        "p95_wall_time_s": round(percentile(timings, 0.95), 3),
        "failures": [item for item in rows if item["http_status"] != 200],
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# RAG 并发稳定性测试记录",
        "",
        "> 本测试只记录 API 状态和延迟；使用固定知识库问题，不包含病例、影像或密钥。",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- 接口：`{result['endpoint']}`",
        f"- 每并发级别每工作线程请求数：{result['repeats']}",
        "",
        "| 并发数 | 请求数 | 成功率 | 平均耗时 | P50 | P95 | 吞吐量 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in result["levels"]:
        lines.append(
            f"| {item['concurrency']} | {item['request_count']} | {item['success_rate']:.0%} | "
            f"{item['average_wall_time_s']:.2f} s | {item['p50_wall_time_s']:.2f} s | "
            f"{item['p95_wall_time_s']:.2f} s | {item['requests_per_second']:.2f} req/s |"
        )
    failures = [failure for item in result["levels"] for failure in item["failures"]]
    lines.extend(["", "## 失败请求", ""])
    if failures:
        for failure in failures:
            lines.append(f"- HTTP {failure['http_status']}：{failure['error'] or 'no detail'}")
    else:
        lines.append("无失败请求。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run concurrent RAG API stability evaluation.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/api/rag/query")
    parser.add_argument("--api-key-env", default="PPGL_INTERNAL_API_KEY")
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    if any(level < 1 for level in args.levels) or args.repeats < 1:
        raise ValueError("levels and repeats must be positive")
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"{args.api_key_env} is not configured")

    headers = {"X-PPGL-Internal-Key": api_key}
    payload = {
        "question": args.question,
        "top_k": 5,
        "retrieve_k": 20,
        "retrieval_mode": "hybrid_rerank",
        "max_tokens": 256,
    }
    levels = []
    for level in args.levels:
        print(f"Testing concurrency={level}...", flush=True)
        levels.append(run_level(level, args.repeats, args.endpoint, headers, payload, args.timeout))
    result = {
        "schema_version": "medvision_concurrency_evaluation_result_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "endpoint": args.endpoint,
        "repeats": args.repeats,
        "levels": levels,
    }
    for output in [args.output_json, args.output_markdown]:
        output.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_markdown.write_text(markdown_report(result), encoding="utf-8")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_markdown}")


if __name__ == "__main__":
    main()
