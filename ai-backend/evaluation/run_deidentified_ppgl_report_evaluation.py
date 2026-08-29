#!/usr/bin/env python3
"""Evaluate PPGL segmentation-backed AI reports without copying images into Git.

All image paths, labels, inference outputs, raw LLM responses and scores are
written below --evaluation-root, which must be outside the repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import nibabel as nib
import numpy as np
from nibabel.processing import resample_from_to


AI_BACKEND_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = AI_BACKEND_DIR / "backend"
INFERENCE_SCRIPT = AI_BACKEND_DIR / "progress_patch_v5" / "infer_single_case.py"
DEFAULT_CHECKPOINT = AI_BACKEND_DIR / "progress_patch_v5" / "weights" / "model_best.pth"
DEFAULT_MODEL_CONFIG = AI_BACKEND_DIR / "progress_patch_v5" / "model_config.json"
sys.path.insert(0, str(BACKEND_DIR))

from report_agent import call_openai_report, compact_case_context, normalize_generated_report, render_report_markdown  # noqa: E402


ORGAN_LABELS = {
    "aorta": "主动脉",
    "kidney_left": "左肾",
    "kidney_right": "右肾",
    "inferior_vena_cava": "下腔静脉",
    "adrenal_gland_left": "左肾上腺",
    "adrenal_gland_right": "右肾上腺",
    "iliopsoas_left": "左髂腰肌",
    "iliopsoas_right": "右髂腰肌",
    "vertebrae": "椎体",
}
REPORT_FIELDS = {
    "case_id",
    "overall_risk",
    "risk_summary",
    "key_findings",
    "risk_reasons",
    "anatomic_relationships",
    "surgical_considerations",
    "follow_up_suggestions",
    "missing_information",
    "limitations",
}


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_number(value: Any, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def dice_metrics(prediction_path: Path, reference_path: Path) -> dict[str, float]:
    prediction_image = nib.load(str(prediction_path))
    reference_image = nib.load(str(reference_path))
    if prediction_image.shape[:3] != reference_image.shape[:3] or not np.allclose(prediction_image.affine, reference_image.affine):
        reference_image = resample_from_to(reference_image, (prediction_image.shape[:3], prediction_image.affine), order=0)
    prediction = np.asarray(prediction_image.dataobj) > 0
    reference = np.asarray(reference_image.dataobj) > 0
    true_positive = int(np.count_nonzero(prediction & reference))
    predicted_count = int(np.count_nonzero(prediction))
    reference_count = int(np.count_nonzero(reference))
    denominator = predicted_count + reference_count
    dice = 1.0 if denominator == 0 else 2.0 * true_positive / denominator
    precision = 1.0 if predicted_count == 0 and reference_count == 0 else true_positive / max(1, predicted_count)
    recall = 1.0 if reference_count == 0 and predicted_count == 0 else true_positive / max(1, reference_count)
    voxel_volume_ml = float(np.prod(prediction_image.header.get_zooms()[:3])) / 1000.0
    predicted_volume_ml = predicted_count * voxel_volume_ml
    reference_volume_ml = reference_count * voxel_volume_ml
    relative_volume_error = abs(predicted_volume_ml - reference_volume_ml) / max(reference_volume_ml, 1e-6)
    return {
        "dice": round(dice, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "predicted_volume_ml": round(predicted_volume_ml, 3),
        "reference_volume_ml": round(reference_volume_ml, 3),
        "relative_volume_error": round(relative_volume_error, 4),
    }


def run_inference(case_id: str, image_path: Path, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    result_path = output_dir / "result.json"
    if result_path.is_file() and args.reuse_existing:
        return json.loads(result_path.read_text(encoding="utf-8"))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"Existing inference output found for {case_id}; use --reuse-existing or a new evaluation root")
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(INFERENCE_SCRIPT),
        "--image", str(image_path),
        "--output-dir", str(output_dir),
        "--case-id", case_id,
        "--checkpoint", str(args.checkpoint),
        "--model-config", str(args.model_config),
        "--device", args.device,
    ]
    completed = subprocess.run(
        command,
        cwd=str(INFERENCE_SCRIPT.parent),
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )
    (output_dir / "inference.log").write_text(
        "COMMAND:\n" + " ".join(command) + "\n\nSTDOUT:\n" + completed.stdout + "\n\nSTDERR:\n" + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"PPGL inference failed for {case_id}; see {output_dir / 'inference.log'}")
    if not result_path.is_file():
        raise RuntimeError(f"PPGL inference did not produce {result_path}")
    return json.loads(result_path.read_text(encoding="utf-8"))


def flatten_report(report: dict[str, Any]) -> str:
    return json.dumps({key: value for key, value in report.items() if key != "_metadata"}, ensure_ascii=False)


def score_raw_report(raw_report: dict[str, Any], case_id: str, segmentation_result: dict[str, Any]) -> dict[str, Any]:
    metrics = segmentation_result.get("metrics", {}) if isinstance(segmentation_result.get("metrics"), dict) else {}
    text = flatten_report(raw_report)
    components = [item for item in metrics.get("components", []) if isinstance(item, dict)]
    maximum_diameter = max((float(item.get("max_diameter_mm", 0) or 0) for item in components), default=0.0)
    side = str(metrics.get("tumor_side_by_nearest_kidney") or "").lower()
    side_label = {"left": "左侧", "right": "右侧"}.get(side, "")
    relations = metrics.get("organ_relations", {}) if isinstance(metrics.get("organ_relations"), dict) else {}
    contact_labels = [
        ORGAN_LABELS.get(str(item.get("name") or key), str(item.get("name") or key))
        for key, item in relations.items()
        if isinstance(item, dict) and bool(item.get("contact_or_overlap"))
    ][:3]
    details = []
    details.append({"id": "schema", "label": "包含固定报告字段", "passed": REPORT_FIELDS.issubset(raw_report)})
    details.append({"id": "case_id", "label": "病例编号与输入一致", "passed": str(raw_report.get("case_id", "")) == case_id})
    volume = metrics.get("tumor_volume_ml")
    details.append(
        {
            "id": "volume", "label": "包含分割肿瘤体积", "expected": format_number(volume),
            "passed": format_number(volume) in text if volume is not None else True,
        }
    )
    if maximum_diameter > 0:
        details.append(
            {
                "id": "diameter", "label": "包含分割最大径", "expected": format_number(maximum_diameter),
                "passed": format_number(maximum_diameter) in text,
            }
        )
    if side_label:
        details.append({"id": "side", "label": "包含分割侧别", "expected": side_label, "passed": side_label in text})
    if contact_labels:
        details.append(
            {
                "id": "contact_relations", "label": "包含接触或重叠的关键结构", "expected": contact_labels,
                "passed": all(label in text for label in contact_labels),
            }
        )
    details.append(
        {
            "id": "cautious_language", "label": "包含医生复核或自动分割局限性提示",
            "passed": any(token in text for token in ["复核", "医生", "自动分割"]),
        }
    )
    unsafe_patterns = ["具体化疗", "药物剂量", "处方剂量", "mg/kg", "毫克/公斤"]
    details.append(
        {
            "id": "no_unsafe_treatment", "label": "未给出具体治疗或剂量",
            "passed": not any(token.lower() in text.lower() for token in unsafe_patterns),
        }
    )
    passed = sum(item["passed"] for item in details)
    total = len(details)
    return {
        "criteria": details,
        "passed_criteria": passed,
        "total_criteria": total,
        "quality_score_10": round(10.0 * passed / total, 2) if total else 0,
        "score_type": "rule_assisted_proxy_not_clinician_review",
    }


def configure_local_report_model(model: str, args: argparse.Namespace) -> None:
    os.environ["REPORT_LLM_PROVIDER"] = "openai_compat"
    os.environ["REPORT_OPENAI_BASE_URL"] = args.ollama_url.rstrip("/") + "/v1"
    os.environ["REPORT_OPENAI_MODEL"] = model
    os.environ.setdefault("REPORT_OPENAI_API_KEY", "ollama")
    os.environ["REPORT_OPENAI_TIMEOUT_SECONDS"] = str(args.report_timeout)
    os.environ["OPENAI_REPORT_MAX_OUTPUT_TOKENS"] = str(args.report_max_tokens)


def create_report(case_dir: Path, model: str, report_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    raw_path = report_dir / "raw_report.json"
    normalized_path = report_dir / "normalized_report.json"
    if raw_path.is_file() and normalized_path.is_file() and args.reuse_existing:
        return {
            "raw": json.loads(raw_path.read_text(encoding="utf-8")),
            "normalized": json.loads(normalized_path.read_text(encoding="utf-8")),
        }
    configure_local_report_model(model, args)
    context = compact_case_context(case_dir)
    raw = call_openai_report(context)
    normalized = normalize_generated_report(raw, context)
    normalized["report_markdown"] = render_report_markdown(normalized)
    write_json(raw_path, raw)
    write_json(normalized_path, normalized)
    (report_dir / "report.md").write_text(normalized["report_markdown"], encoding="utf-8")
    return {"raw": raw, "normalized": normalized}


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# 脱敏病例 PPGL 分割与报告评测记录",
        "",
        "> 影像、标签、预测掩膜、原始 LLM 回答和包含本地路径的清单均保存在仓库外的评测目录。本文件只应在该外部目录中保存，不应提交 Git。报告评分为规则辅助代理评分，不能替代临床专家人工复核。",
        "",
        f"- 生成时间：{result['generated_at']}",
        f"- 评测病例数：{len(result['cases'])}",
        f"- PPGL 推理设备：`{result['device']}`",
        "",
        "## 分割结果",
        "",
        "| 评测病例 | Dice | Precision | Recall | 预测体积 mL | 真值体积 mL | 相对体积误差 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in result["cases"]:
        metric = case.get("segmentation_metrics", {})
        lines.append(
            f"| {case['eval_case_id']} | {metric.get('dice', 0):.4f} | {metric.get('precision', 0):.4f} | "
            f"{metric.get('recall', 0):.4f} | {metric.get('predicted_volume_ml', 0):.3f} | "
            f"{metric.get('reference_volume_ml', 0):.3f} | {metric.get('relative_volume_error', 0):.2%} |"
        )
    lines.extend(["", "## 原始 AI 报告规则评分", ""])
    for model in result["models"]:
        scores = [item["report_scores"].get(model, {}).get("quality_score_10", 0) for item in result["cases"]]
        lines.append(f"### {model}")
        lines.append("")
        lines.append(f"平均规则代理评分：{sum(scores) / len(scores):.2f}/10" if scores else "没有可用报告评分。")
        lines.append("")
    lines.extend([
        "## 评分解释",
        "",
        "- 分割指标使用 `labels_ablation_tumor_only` 作为肿瘤真值，仅用于离线研究评测。",
        "- 报告评分检查原始模型输出是否复述分割得到的体积、最大径、侧别、接触关系和安全提示；不会把固定模板的回填内容误当作模型能力。",
        "- 临床专家仍应独立审阅报告的医学准确性、表达是否恰当及是否存在遗漏。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deidentified PPGL segmentation and raw AI report evaluation.")
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--labels-dir", type=Path, required=True)
    parser.add_argument("--evaluation-root", type=Path, required=True)
    parser.add_argument("--case-ids", nargs="+", required=True, help="Image stems such as PPGL_Tr_0088")
    parser.add_argument("--models", nargs="+", default=["ppgl-qwen3-32b-q4:latest"])
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--model-config", type=Path, default=DEFAULT_MODEL_CONFIG)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--report-timeout", type=float, default=180)
    parser.add_argument("--report-max-tokens", type=int, default=2000)
    parser.add_argument("--reuse-existing", action="store_true")
    args = parser.parse_args()

    args.images_dir = args.images_dir.expanduser().resolve()
    args.labels_dir = args.labels_dir.expanduser().resolve()
    args.evaluation_root = args.evaluation_root.expanduser().resolve()
    args.checkpoint = args.checkpoint.expanduser().resolve()
    args.model_config = args.model_config.expanduser().resolve()
    if not args.images_dir.is_dir() or not args.labels_dir.is_dir():
        raise FileNotFoundError("images-dir and labels-dir must exist")
    if not args.checkpoint.is_file() or not args.model_config.is_file():
        raise FileNotFoundError("PPGL checkpoint or model config is missing")
    args.evaluation_root.mkdir(parents=True, exist_ok=True)

    previous_result_path = args.evaluation_root / "results.json"
    previous_result = {}
    if args.reuse_existing and previous_result_path.is_file():
        previous_result = json.loads(previous_result_path.read_text(encoding="utf-8"))
    previous_cases = {
        str(item.get("eval_case_id")): item
        for item in previous_result.get("cases", [])
        if isinstance(item, dict) and item.get("eval_case_id")
    }
    previous_models = [str(model) for model in previous_result.get("models", []) if str(model).strip()]
    all_models = list(dict.fromkeys(previous_models + args.models))
    result: dict[str, Any] = {
        "schema_version": "medvision_deidentified_ppgl_report_evaluation_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "device": args.device,
        "models": all_models,
        "cases": [],
    }
    manifest_cases = []
    for index, source_case_id in enumerate(args.case_ids, start=1):
        source_name = source_case_id if source_case_id.endswith(".nii.gz") else source_case_id + ".nii.gz"
        image_path = args.images_dir / source_name
        label_path = args.labels_dir / source_name
        if not image_path.is_file() or not label_path.is_file():
            raise FileNotFoundError(f"Image or label is missing for {source_case_id}")
        eval_case_id = f"eval-{index:03d}"
        case_dir = args.evaluation_root / "cases" / eval_case_id
        output_dir = case_dir / "output" / "ppgl"
        print(f"Running PPGL inference for {eval_case_id}...", flush=True)
        inference_result = run_inference(eval_case_id, image_path, output_dir, args)
        segmentation_metrics = dice_metrics(Path(inference_result["outputs"]["tumor_mask_path"]), label_path)
        previous_case = previous_cases.get(eval_case_id, {})
        case_result: dict[str, Any] = {
            "eval_case_id": eval_case_id,
            "segmentation_metrics": segmentation_metrics,
            "inference_timing_seconds": inference_result.get("timing_seconds"),
            "report_scores": dict(previous_case.get("report_scores", {})),
        }
        manifest_cases.append({"eval_case_id": eval_case_id, "image_path": str(image_path), "label_path": str(label_path)})
        for model in args.models:
            model_key = model.replace("/", "_").replace(":", "_")
            print(f"Generating raw report for {eval_case_id} with {model}...", flush=True)
            try:
                reports = create_report(case_dir, model, args.evaluation_root / "reports" / model_key / eval_case_id, args)
                score = score_raw_report(reports["raw"], eval_case_id, inference_result)
            except Exception as exc:
                score = {"error": str(exc), "quality_score_10": 0, "criteria": [], "passed_criteria": 0, "total_criteria": 0}
            case_result["report_scores"][model] = score
        result["cases"].append(case_result)

    write_json(args.evaluation_root / "case_manifest.json", {"schema_version": "medvision_private_case_manifest_v1", "cases": manifest_cases})
    write_json(args.evaluation_root / "results.json", result)
    (args.evaluation_root / "report.md").write_text(markdown_report(result), encoding="utf-8")
    print(f"Results: {args.evaluation_root / 'results.json'}")
    print(f"Report: {args.evaluation_root / 'report.md'}")


if __name__ == "__main__":
    main()
