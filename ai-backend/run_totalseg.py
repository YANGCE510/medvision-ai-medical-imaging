#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parent
TOTALSEG_PIPELINE = BACKEND_DIR / "run_totalseg_pipeline.py"


def normalize_case_id(path: Path) -> str:
    name = path.name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return path.stem


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def resolve_device(device: str) -> tuple[str, str]:
    value = str(device).strip().lower()
    if value == "cpu":
        return "cpu", "cpu"
    if value in {"cuda", "gpu"}:
        return "cuda:0", "gpu:0"
    if value.startswith("cuda:"):
        return value, "gpu:" + value.split(":", 1)[1]
    return value, "gpu:0"


def subprocess_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env_prefix = Path(sys.executable).resolve().parent.parent
    env_bin = env_prefix / "bin"
    env_lib = env_prefix / "lib"
    env["PATH"] = str(env_bin) + os.pathsep + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = str(env_lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return env


def tumor_label_from_label_map(label_map: dict[str, Any]) -> int | None:
    labels = label_map.get("label_map", label_map)
    if not isinstance(labels, dict):
        return None
    for key, value in labels.items():
        if str(value).startswith("tumor:"):
            return int(key)
    return None


def normalize_slice(slice_2d: np.ndarray) -> np.ndarray:
    arr = np.asarray(slice_2d, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, [1, 99])
    if hi <= lo:
        lo, hi = float(finite.min()), float(finite.max())
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    arr = np.clip((arr - lo) / (hi - lo), 0, 1)
    return np.round(arr * 255).astype(np.uint8)


def create_overlay_png(image_path: Path, mask_path: Path, label_map_path: Path, output_path: Path) -> None:
    image = np.asarray(nib.load(str(image_path)).dataobj)
    mask = np.rint(np.asarray(nib.load(str(mask_path)).dataobj)).astype(np.int32, copy=False)
    label_map = load_json(label_map_path)
    tumor_label = tumor_label_from_label_map(label_map)

    image = image[..., 0] if image.ndim == 4 else image
    if image.shape[:3] != mask.shape[:3]:
        raise ValueError(f"Image and mask shape mismatch: {image.shape[:3]} vs {mask.shape[:3]}")

    tumor = mask == tumor_label if tumor_label is not None else np.zeros(mask.shape, dtype=bool)
    if tumor.any():
        z = int(np.argmax(tumor.sum(axis=(0, 1))))
    else:
        z = int(mask.shape[2] // 2)

    base = normalize_slice(image[:, :, z])
    rgb = np.stack([base, base, base], axis=-1).astype(np.float32)
    organ = (mask[:, :, z] > 0) & ~tumor[:, :, z]
    tumor_slice = tumor[:, :, z]

    rgb[organ] = rgb[organ] * 0.55 + np.array([30, 144, 255], dtype=np.float32) * 0.45
    rgb[tumor_slice] = rgb[tumor_slice] * 0.35 + np.array([255, 64, 64], dtype=np.float32) * 0.65
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    # Rotate for a more conventional preview orientation.
    rgb = np.rot90(rgb)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(output_path)


def run_totalseg(args: argparse.Namespace, case_id: str, output_dir: Path) -> Path:
    if not TOTALSEG_PIPELINE.exists():
        raise FileNotFoundError(f"TotalSegmentator pipeline not found: {TOTALSEG_PIPELINE}")

    _device, totalseg_device = resolve_device(args.device)
    run_root = output_dir
    run_name = "totalseg"
    cmd = [
        sys.executable,
        str(TOTALSEG_PIPELINE),
        "--case-id",
        case_id,
        "--image",
        str(args.input),
        "--output-root",
        str(run_root),
        "--run-name",
        run_name,
        "--mode",
        str(args.mode),
        "--totalseg-device",
        totalseg_device,
    ]

    if args.force:
        cmd.append("--force")
    if args.totalseg_fast:
        cmd.append("--totalseg-fast")
    if args.totalseg_fastest:
        cmd.append("--totalseg-fastest")
    if str(args.totalseg_existing_dir).strip():
        cmd.extend(["--totalseg-existing-dir", str(args.totalseg_existing_dir)])

    completed = subprocess.run(
        cmd,
        cwd=str(BACKEND_DIR),
        env=subprocess_runtime_env(),
        text=True,
        capture_output=True,
    )
    log_path = output_dir / "run_totalseg_subprocess.log"
    log_path.write_text(
        "COMMAND:\n"
        + " ".join(cmd)
        + "\n\nSTDOUT:\n"
        + completed.stdout
        + "\n\nSTDERR:\n"
        + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"TotalSegmentator pipeline failed. See log: {log_path}")
    return run_root / run_name


def collect_outputs(case_id: str, input_path: Path, output_dir: Path, run_dir: Path) -> dict[str, Any]:
    final_seg = run_dir / "fusion" / f"{case_id}_final_seg.nii.gz"
    label_map_path = run_dir / "fusion" / "label_map.json"
    metrics_path = run_dir / "analysis" / "clinical_metrics.json"
    report_path = run_dir / "analysis" / "report.md"
    timing_path = run_dir / "timing.json"

    for path in [final_seg, label_map_path, metrics_path]:
        if not path.exists():
            raise FileNotFoundError(f"Expected pipeline output missing: {path}")

    mask_path = output_dir / "mask.nii.gz"
    result_path = output_dir / "result.json"
    overlay_path = output_dir / "overlay.png"
    shutil.copy2(final_seg, mask_path)
    create_overlay_png(input_path, mask_path, label_map_path, overlay_path)

    label_payload = load_json(label_map_path)
    metrics = load_json(metrics_path)
    timing = load_json(timing_path) if timing_path.exists() else {}

    labels = label_payload.get("label_map", {})
    result = {
        "case_id": case_id,
        "status": "completed",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input_image": str(input_path),
        "outputs": {
            "mask_path": str(mask_path),
            "overlay_path": str(overlay_path),
            "result_path": str(result_path),
            "totalseg_run_dir": str(run_dir),
            "label_map_path": str(label_map_path),
            "clinical_metrics_path": str(metrics_path),
            "report_path": str(report_path) if report_path.exists() else "",
        },
        "segmentation": {
            "label_count": len(labels),
            "label_map": labels,
            "tumor_priority": False,
        },
        "clinical_metrics": metrics,
        "summary": {
            "pipeline": metrics.get("pipeline"),
            "task": metrics.get("task"),
            "organ_count": metrics.get("organ_count"),
            "voxel_volume_mm3": metrics.get("voxel_volume_mm3"),
            "organs": metrics.get("organs", {}),
        },
        "timing": timing,
    }
    write_json(result_path, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Frontend entrypoint for TotalSegmentator inference.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-id", default="")
    parser.add_argument("--mode", choices=["jetson_fast", "abdomen", "full_total"], default="full_total")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--totalseg-existing-dir", default="")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--totalseg-fast", action="store_true")
    parser.add_argument("--totalseg-fastest", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.input = args.input.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    if str(args.totalseg_existing_dir).strip():
        args.totalseg_existing_dir = Path(str(args.totalseg_existing_dir)).expanduser().resolve()
    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    args.output.mkdir(parents=True, exist_ok=True)
    case_id = args.case_id.strip() or normalize_case_id(args.input)
    run_dir = run_totalseg(args, case_id, args.output)
    result = collect_outputs(case_id, args.input, args.output, run_dir)
    print(json.dumps({"status": "completed", "result_path": result["outputs"]["result_path"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
