#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import torch


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_RAW_GCP_DIR = Path("/path/to/PPGL/otafv2_inference_package_20260524/raw_gcp")
DEFAULT_CHECKPOINT = PROJECT_DIR / "ckpt" / "model_best_160.pth"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "engines" / "gcpv5"
DEFAULT_TRTEXEC = Path("/usr/src/tensorrt/bin/trtexec")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_checkpoint_object(path: Path, device: str) -> Any:
    try:
        return torch.load(str(path), map_location=device, weights_only=True)
    except TypeError:
        return torch.load(str(path), map_location=device)


def resolve_state_dict(checkpoint_obj: Any) -> dict[str, torch.Tensor]:
    if isinstance(checkpoint_obj, dict):
        for key in ("state_dict", "model_state_dict"):
            value = checkpoint_obj.get(key)
            if isinstance(value, dict):
                return value
        return checkpoint_obj
    raise ValueError("Unsupported checkpoint format.")


def load_state_dict_allow_adrenal_aux(model: torch.nn.Module, state_dict: dict[str, torch.Tensor]) -> None:
    model_keys = set(model.state_dict().keys())
    filtered = {k: v for k, v in state_dict.items() if k in model_keys}
    missing = sorted(k for k in model_keys if k not in filtered)
    bad_extra = sorted(k for k in state_dict.keys() if k not in model_keys and not k.startswith("adrenal_aux_head."))
    if missing:
        raise RuntimeError(f"checkpoint misses model keys: {missing[:10]}")
    if bad_extra:
        raise RuntimeError(f"checkpoint has unsupported extra keys: {bad_extra[:10]}")
    model.load_state_dict(filtered, strict=True)


def ensure_onnx_available() -> None:
    try:
        import onnx  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Python package 'onnx' is required by torch.onnx.export but is not installed in ppgl-gpu38. "
            "Install a local wheel, for example: "
            "/path/to/anaconda3/envs/ppgl-gpu38/bin/python -m pip install --only-binary=:all: onnx"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export GCPV5 PyTorch checkpoint to ONNX and TensorRT engine.")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--raw-gcp-dir", type=Path, default=DEFAULT_RAW_GCP_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--num-classes", type=int, default=11)
    parser.add_argument("--roi-size", type=int, default=160)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--opset", type=int, default=17)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--onnx-only", action="store_true")
    parser.add_argument("--no-fp16", dest="fp16", action="store_false", default=True)
    parser.add_argument("--trtexec", type=Path, default=DEFAULT_TRTEXEC)
    parser.add_argument("--workspace-mb", type=int, default=2048)
    parser.add_argument("--trtexec-runs", type=int, default=100)
    return parser


def export_onnx(args: argparse.Namespace, onnx_path: Path) -> None:
    if onnx_path.exists() and not args.force:
        print(f"ONNX exists, skipping export: {onnx_path}")
        return
    ensure_onnx_available()
    if str(args.raw_gcp_dir) not in sys.path:
        sys.path.insert(0, str(args.raw_gcp_dir))
    from gcp_unet import build_unet_model

    device = str(args.device)
    if device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError(f"Requested {device}, but CUDA is not available.")
    model = build_unet_model(use_gcp=False, out_channels=int(args.num_classes)).to(device)
    checkpoint_obj = load_checkpoint_object(args.checkpoint.expanduser(), device)
    load_state_dict_allow_adrenal_aux(model, resolve_state_dict(checkpoint_obj))
    model.eval()

    roi = int(args.roi_size)
    dummy = torch.randn(1, 1, roi, roi, roi, device=device, dtype=torch.float32)
    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    with torch.inference_mode():
        torch.onnx.export(
            model,
            dummy,
            str(onnx_path),
            input_names=["input"],
            output_names=["logits"],
            opset_version=int(args.opset),
            do_constant_folding=True,
        )
    print(f"Exported ONNX: {onnx_path}")


def build_engine(args: argparse.Namespace, onnx_path: Path, engine_path: Path, log_path: Path) -> None:
    if engine_path.exists() and not args.force:
        print(f"TensorRT engine exists, skipping build: {engine_path}")
        return
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX file not found: {onnx_path}")
    trtexec = args.trtexec.expanduser()
    if not trtexec.exists():
        raise FileNotFoundError(f"trtexec not found: {trtexec}")

    cmd = [
        str(trtexec),
        f"--onnx={onnx_path}",
        f"--saveEngine={engine_path}",
        f"--workspace={int(args.workspace_mb)}",
        f"--iterations={int(args.trtexec_runs)}",
        "--separateProfileRun",
    ]
    if bool(args.fp16):
        cmd.append("--fp16")

    engine_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    completed = subprocess.run(cmd, cwd=str(PROJECT_DIR), text=True, capture_output=True)
    elapsed = time.perf_counter() - start
    log_path.write_text(
        "COMMAND:\n"
        + " ".join(cmd)
        + f"\n\nELAPSED_SECONDS: {elapsed:.3f}\n\nSTDOUT:\n"
        + completed.stdout
        + "\n\nSTDERR:\n"
        + completed.stderr,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"trtexec failed. See log: {log_path}")
    print(f"Built TensorRT engine: {engine_path}")
    print(f"trtexec log: {log_path}")


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir = args.output_dir.expanduser()
    args.checkpoint = args.checkpoint.expanduser()
    args.raw_gcp_dir = args.raw_gcp_dir.expanduser()

    precision = "fp16" if bool(args.fp16) else "fp32"
    stem = f"gcpv5_roi{int(args.roi_size)}_{precision}"
    onnx_path = args.output_dir / f"{stem}.onnx"
    engine_path = args.output_dir / f"{stem}.engine"
    manifest_path = args.output_dir / f"{stem}.json"
    log_path = args.output_dir / f"{stem}_trtexec.log"

    export_onnx(args, onnx_path)
    if not args.onnx_only:
        build_engine(args, onnx_path, engine_path, log_path)

    write_json(
        manifest_path,
        {
            "checkpoint": str(args.checkpoint),
            "raw_gcp_dir": str(args.raw_gcp_dir),
            "roi_size": int(args.roi_size),
            "num_classes": int(args.num_classes),
            "opset": int(args.opset),
            "fp16": bool(args.fp16),
            "onnx_path": str(onnx_path),
            "engine_path": str(engine_path),
            "trtexec_log": str(log_path),
        },
    )
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
