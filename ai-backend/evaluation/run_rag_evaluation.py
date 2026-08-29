#!/usr/bin/env python3
"""Run a reproducible end-to-end RAG retrieval and citation evaluation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import statistics
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> tuple[int, dict[str, Any], float]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8")), time.perf_counter() - started
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload, time.perf_counter() - started
    except URLError as exc:
        return 0, {"detail": f"network error: {exc.reason}"}, time.perf_counter() - started


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * ratio
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def evaluate_case(case: dict[str, Any], endpoint: str, headers: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    status, payload, elapsed = post_json(
        endpoint,
        {
            "question": case["question"],
            "top_k": args.top_k,
            "retrieve_k": args.retrieve_k,
            "retrieval_mode": args.retrieval_mode,
            "max_tokens": args.max_tokens,
        },
        headers,
        args.timeout,
    )
    row: dict[str, Any] = {
        "id": case["id"],
        "question": case["question"],
        "expected_document_ids": case["expected_document_ids"],
        "http_status": status,
        "wall_time_s": round(elapsed, 3),
    }
    if status != 200:
        row["error"] = payload.get("detail", "unknown error")
        row["retrieval_hit"] = False
        row["valid_citation"] = False
        row["expected_source_cited"] = False
        return row

    answer = str(payload.get("answer", ""))
    citations = payload.get("citations", []) if isinstance(payload.get("citations"), list) else []
    retrieved_document_ids = [str(item.get("document_id", "")) for item in citations]
    citation_ids = sorted({int(item) for item in re.findall(r"\[(\d+)\]", answer)})
    valid_ids = [item for item in citation_ids if 1 <= item <= len(citations)]
    cited_document_ids = [retrieved_document_ids[item - 1] for item in valid_ids]
    expected = set(case["expected_document_ids"])
    row.update(
        {
            "answer": answer,
            "retrieved_document_ids": retrieved_document_ids,
            "cited_document_ids": cited_document_ids,
            "retrieval_hit": bool(expected.intersection(retrieved_document_ids)),
            "valid_citation": bool(valid_ids),
            "expected_source_cited": bool(expected.intersection(cited_document_ids)),
            "evidence_assessment": payload.get("metadata", {}).get("evidence_assessment", {}),
            "model": payload.get("metadata", {}).get("model", ""),
            "retrieval_latency_ms": payload.get("metadata", {}).get("retrieval_latency_ms", {}),
        }
    )
    return row


def markdown_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# RAG 引用正确率评测记录",
        "",
        "> 本评测检查本地知识库的检索命中、回答中引用编号是否合法，以及引用结果中是否包含预期文献。它不替代医学专家对答案临床正确性的复核。",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- 接口：`{result['endpoint']}`",
        f"- 题库：`{result['case_library']}`，共 {summary['total']} 题",
        f"- 检索模式：`{result['retrieval_mode']}`；top_k={result['top_k']}；retrieve_k={result['retrieve_k']}",
        "",
        "## 汇总",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 接口成功率 | {summary['success_rate']:.0%} ({summary['success']}/{summary['total']}) |",
        f"| 预期文献检索命中率 | {summary['retrieval_hit_rate']:.0%} ({summary['retrieval_hits']}/{summary['total']}) |",
        f"| 回答有效引用率 | {summary['valid_citation_rate']:.0%} ({summary['valid_citations']}/{summary['total']}) |",
        f"| 预期文献被正确引用率 | {summary['expected_source_cited_rate']:.0%} ({summary['expected_sources_cited']}/{summary['total']}) |",
        f"| 平均端到端耗时 | {summary['average_wall_time_s']:.2f} s |",
        f"| P95 端到端耗时 | {summary['p95_wall_time_s']:.2f} s |",
        "",
        "## 失败或需复核题目",
        "",
    ]
    flagged = [
        item for item in result["cases"]
        if not (item["retrieval_hit"] and item["valid_citation"] and item["expected_source_cited"])
    ]
    if not flagged:
        lines.append("全部题目均检索到并引用了预期文献。")
    else:
        for item in flagged:
            failures = []
            if not item["retrieval_hit"]:
                failures.append("未检索到预期文献")
            if not item["valid_citation"]:
                failures.append("回答没有有效引用编号")
            if not item["expected_source_cited"]:
                failures.append("未引用预期文献")
            lines.append(f"- `{item['id']}`：{'；'.join(failures)}。")
    lines.extend(["", "原始问题、回答、检索文献 ID 和引用映射见同名 JSON 文件。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MedVision RAG retrieval and citation behaviour.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/api/rag/query")
    parser.add_argument("--cases", type=Path, default=Path(__file__).with_name("rag_evaluation_cases.json"))
    parser.add_argument("--api-key-env", default="PPGL_INTERNAL_API_KEY")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--retrieve-k", type=int, default=20)
    parser.add_argument("--retrieval-mode", choices=["dense", "hybrid", "hybrid_rerank"], default="hybrid_rerank")
    parser.add_argument("--max-tokens", type=int, default=384)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()

    library = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = library.get("cases", [])
    if not isinstance(cases, list) or len(cases) != 20:
        raise ValueError("RAG evaluation library must contain exactly 20 cases")
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"{args.api_key_env} is not configured")
    headers = {"X-PPGL-Internal-Key": api_key}

    rows: list[dict[str, Any]] = []
    if args.workers == 1:
        for case in cases:
            print(f"Evaluating {case['id']}...", flush=True)
            rows.append(evaluate_case(case, args.endpoint, headers, args))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(evaluate_case, case, args.endpoint, headers, args): case for case in cases}
            for future in as_completed(futures):
                row = future.result()
                print(f"Evaluated {row['id']}...", flush=True)
                rows.append(row)
        rows.sort(key=lambda item: item["id"])

    timings = [item["wall_time_s"] for item in rows]
    success = sum(item["http_status"] == 200 for item in rows)
    retrieval_hits = sum(item["retrieval_hit"] for item in rows)
    valid_citations = sum(item["valid_citation"] for item in rows)
    expected_sources_cited = sum(item["expected_source_cited"] for item in rows)
    total = len(rows)
    result = {
        "schema_version": "medvision_rag_evaluation_result_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "endpoint": args.endpoint,
        "case_library": str(args.cases),
        "retrieval_mode": args.retrieval_mode,
        "top_k": args.top_k,
        "retrieve_k": args.retrieve_k,
        "cases": rows,
        "summary": {
            "total": total,
            "success": success,
            "success_rate": success / total if total else 0,
            "retrieval_hits": retrieval_hits,
            "retrieval_hit_rate": retrieval_hits / total if total else 0,
            "valid_citations": valid_citations,
            "valid_citation_rate": valid_citations / total if total else 0,
            "expected_sources_cited": expected_sources_cited,
            "expected_source_cited_rate": expected_sources_cited / total if total else 0,
            "average_wall_time_s": round(statistics.mean(timings), 3) if timings else 0,
            "p95_wall_time_s": round(percentile(timings, 0.95), 3),
        },
    }
    for output in [args.output_json, args.output_markdown]:
        output.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_markdown.write_text(markdown_report(result), encoding="utf-8")
    print(f"JSON: {args.output_json}")
    print(f"Markdown: {args.output_markdown}")


if __name__ == "__main__":
    main()
