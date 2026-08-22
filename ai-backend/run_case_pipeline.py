#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import torch
from nibabel.processing import resample_from_to
from monai.data import DataLoader, Dataset
from monai.inferers import sliding_window_inference
from monai.transforms import (
    Compose,
    CropForegroundd,
    EnsureChannelFirstd,
    EnsureTyped,
    LoadImaged,
    Orientationd,
    ScaleIntensityRanged,
    Spacingd,
    SpatialPadd,
    ToTensord,
)


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_PACKAGE_DIR = Path("/path/to/PPGL/otafv2_inference_package_20260524")
DEFAULT_RAW_GCP_DIR = DEFAULT_PACKAGE_DIR / "raw_gcp"
DEFAULT_TOTALSEG_ROOT = Path("/path/to/TotalSegmentator")
DEFAULT_CHECKPOINT = PROJECT_DIR / "ckpt/model_best_160.pth"
DEFAULT_IMAGE = Path("/path/to/PPGL/dataset/images/PPGL_Tr_0029.nii.gz")
DEFAULT_OUTPUT_ROOT = PROJECT_DIR / "runs"

GCP_TUMOR_LABEL = 10

OTAFV2_LABEL_IDS = {
    "background": 0,
    "aorta": 1,
    "left_kidney": 2,
    "right_kidney": 3,
    "ivc": 4,
    "left_adrenal": 5,
    "right_adrenal": 6,
    "left_psoas": 7,
    "right_psoas": 8,
    "vertebrae": 9,
    "tumor": 10,
}

TOTAL_TO_OTAFV2 = {
    "aorta": "aorta",
    "kidney_left": "left_kidney",
    "kidney_right": "right_kidney",
    "inferior_vena_cava": "ivc",
    "adrenal_gland_left": "left_adrenal",
    "adrenal_gland_right": "right_adrenal",
    "iliopsoas_left": "left_psoas",
    "iliopsoas_right": "right_psoas",
}

JETSON_FAST_ROIS = ("kidney_left", "kidney_right", "aorta")
DEFAULT_APR_ANCHOR_ROIS = ("aorta", "kidney_left", "kidney_right")
FAST_ANALYSIS_ANCHORS = ("aorta", "kidney_left", "kidney_right")
FULL_ANALYSIS_ANCHORS = (
    "aorta",
    "kidney_left",
    "kidney_right",
    "inferior_vena_cava",
    "adrenal_gland_left",
    "adrenal_gland_right",
)

MAJOR_VESSEL_ROIS = {
    "aorta",
    "inferior_vena_cava",
    "portal_vein_and_splenic_vein",
    "iliac_artery_left",
    "iliac_artery_right",
    "iliac_vena_left",
    "iliac_vena_right",
}
ADRENAL_ROIS = {"adrenal_gland_left", "adrenal_gland_right"}
KIDNEY_ROIS = {"kidney_left", "kidney_right"}
BOWEL_ROIS = {"duodenum", "small_bowel", "colon", "stomach"}
SOLID_ORGAN_ROIS = {"liver", "spleen", "pancreas"}
MUSCULOSKELETAL_ROIS = {"iliopsoas_left", "iliopsoas_right"}

MISSING_CLINICAL_DATA_FOR_PPGL_RISK = [
    "plasma_or_urine_metanephrines",
    "plasma_or_urine_3_methoxytyramine",
    "catecholamine_secretion_pattern",
    "SDHB_or_SDHx_status",
    "germline_genetic_testing",
    "Ki67_or_PASS_or_GAPP_score",
    "symptoms_and_blood_pressure",
    "known_metastasis_or_recurrence_history",
]

ABDOMEN_ROIS = (
    "liver",
    "spleen",
    "pancreas",
    "stomach",
    "duodenum",
    "small_bowel",
    "colon",
    "kidney_left",
    "kidney_right",
    "adrenal_gland_left",
    "adrenal_gland_right",
    "aorta",
    "inferior_vena_cava",
    "portal_vein_and_splenic_vein",
    "iliac_artery_left",
    "iliac_artery_right",
    "iliac_vena_left",
    "iliac_vena_right",
    "iliopsoas_left",
    "iliopsoas_right",
    "vertebrae_T12",
    "vertebrae_L1",
    "vertebrae_L2",
    "vertebrae_L3",
    "vertebrae_L4",
    "vertebrae_L5",
)


def now_token() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_case_id(value: str | Path) -> str:
    name = Path(str(value)).name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return name


def ensure_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_name_list(value: str) -> list[str] | None:
    cleaned = str(value).strip()
    if not cleaned or cleaned.lower() == "all":
        return None
    names = [part.strip() for part in cleaned.split(",") if part.strip()]
    return names or None


def append_log(log_path: Path, message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(message, flush=True)


def format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m{sec:04.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h{int(minutes):02d}m{sec:04.1f}s"


@contextmanager
def timed_stage(log_path: Path, timings: dict[str, float], stage_key: str, label: str):
    start = time.perf_counter()
    append_log(log_path, f"[START] {label}")
    try:
        yield
    except Exception:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - start
        timings[stage_key] = elapsed
        append_log(log_path, f"[FAILED] {label} after {format_elapsed(elapsed)}")
        raise
    else:
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        elapsed = time.perf_counter() - start
        timings[stage_key] = elapsed
        append_log(log_path, f"[DONE] {label} in {format_elapsed(elapsed)}")


def prepend_env_path(env: dict[str, str], key: str, values: list[Path]) -> None:
    existing = [part for part in env.get(key, "").split(os.pathsep) if part]
    additions = [str(path) for path in values if path and path.exists()]
    merged: list[str] = []
    for part in additions + existing:
        if part not in merged:
            merged.append(part)
    if merged:
        env[key] = os.pathsep.join(merged)


def runtime_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    prepend_env_path(
        env,
        "LD_LIBRARY_PATH",
        [
            Path(sys.executable).resolve().parent.parent / "lib",
            Path("/usr/local/cuda-11.4/lib64"),
        ],
    )
    prepend_env_path(env, "PYTHONPATH", [Path(args.raw_gcp_dir), Path(args.package_dir), Path(args.totalseg_root)])
    return env


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
    extra = sorted(k for k in state_dict.keys() if k not in model_keys)
    bad_extra = [k for k in extra if not k.startswith("adrenal_aux_head.")]
    if bad_extra:
        raise RuntimeError(f"checkpoint has unsupported extra keys: {bad_extra[:10]}")
    filtered = {k: v for k, v in state_dict.items() if k in model_keys}
    missing = sorted(k for k in model_keys if k not in filtered)
    if missing:
        raise RuntimeError(f"checkpoint misses model keys: {missing[:10]}")
    model.load_state_dict(filtered, strict=True)


def cuda_oom(exc: BaseException) -> bool:
    text = str(exc).lower()
    return isinstance(exc, torch.cuda.OutOfMemoryError) or "cuda out of memory" in text or "nvmapmemalloc" in text


def gcp_retry_roi_sizes(args: argparse.Namespace) -> list[int]:
    requested = int(args.gcp_roi_size)
    candidates = [requested]
    if not bool(args.no_gcp_auto_lowmem):
        candidates.extend([224, 192, 160, 128])
    seen: set[int] = set()
    return [roi for roi in candidates if roi > 0 and roi <= requested and not (roi in seen or seen.add(roi))]


def default_gcp_engine_path(args: argparse.Namespace) -> Path:
    precision = "fp16" if bool(args.gcp_amp) else "fp32"
    return PROJECT_DIR / "engines" / "gcpv5" / f"gcpv5_roi{int(args.gcp_roi_size)}_{precision}.engine"


def should_use_gcp_local_roi(args: argparse.Namespace) -> bool:
    explicit = getattr(args, "gcp_local_roi", None)
    if explicit is not None:
        return bool(explicit)
    if str(getattr(args, "reuse_gcp_path", "")).strip():
        return False
    return str(args.mode) == "jetson_fast" and str(args.gcp_backend) == "trt"


def build_image_only_transforms(roi_size: int, fg_margin: int, crop_foreground: bool = True) -> Compose:
    transforms: list[Any] = [
        LoadImaged(keys=["image"]),
        EnsureChannelFirstd(keys=["image"]),
        Orientationd(keys=["image"], axcodes="RAS"),
        Spacingd(keys=["image"], pixdim=(1.0, 1.0, 1.0), mode=("bilinear",)),
        EnsureTyped(keys=["image"], track_meta=True),
        ScaleIntensityRanged(keys=["image"], a_min=0, a_max=255, b_min=0, b_max=1, clip=True),
    ]
    if crop_foreground:
        transforms.append(CropForegroundd(keys=["image"], source_key="image", margin=int(fg_margin)))
    transforms.extend(
        [
            SpatialPadd(keys=["image"], spatial_size=(int(roi_size), int(roi_size), int(roi_size)), method="symmetric"),
            ToTensord(keys=["image"]),
        ]
    )
    return Compose(transforms)


def unwrap_meta_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)) and value:
        return unwrap_meta_value(value[0])
    if isinstance(value, np.ndarray):
        if value.shape == ():
            return value.item()
        if value.size:
            return unwrap_meta_value(value.reshape(-1)[0])
    return value


def first_affine(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    arr = np.asarray(value, dtype=np.float64)
    while arr.ndim > 2:
        arr = arr[0]
    return arr if arr.shape == (4, 4) else None


def image_filename_from_batch(batch: dict[str, Any]) -> str:
    image = batch.get("image")
    if hasattr(image, "meta") and isinstance(image.meta, dict):
        filename = unwrap_meta_value(image.meta.get("filename_or_obj"))
        if filename:
            return str(filename)
    meta = batch.get("image_meta_dict", {})
    if isinstance(meta, dict):
        filename = unwrap_meta_value(meta.get("filename_or_obj"))
        if filename:
            return str(filename)
    raise ValueError("Cannot read image filename from MONAI metadata.")


def image_current_affine(batch: dict[str, Any]) -> np.ndarray:
    image = batch.get("image")
    if hasattr(image, "meta") and isinstance(image.meta, dict):
        affine = first_affine(image.meta.get("affine"))
        if affine is not None:
            return affine
    meta = batch.get("image_meta_dict", {})
    if isinstance(meta, dict):
        affine = first_affine(meta.get("affine"))
        if affine is not None:
            return affine
    raise ValueError("Cannot read current affine from MONAI metadata.")


def save_prediction_label_nifti(batch: dict[str, Any], pred_cls: torch.Tensor, output_path: Path) -> None:
    pred_np = pred_cls.detach().cpu().numpy() if torch.is_tensor(pred_cls) else np.asarray(pred_cls)
    while pred_np.ndim > 3 and pred_np.shape[0] == 1:
        pred_np = pred_np[0]
    if pred_np.ndim != 3:
        raise ValueError(f"Invalid prediction shape: {pred_np.shape}")
    pred_np = np.rint(pred_np).astype(np.uint8, copy=False)

    reference_path = image_filename_from_batch(batch)
    reference_img = nib.load(reference_path)
    current_affine = image_current_affine(batch)
    out_np = fast_axis_aligned_label_backproject(pred_np, current_affine, reference_img)
    if out_np is None:
        pred_img = nib.Nifti1Image(pred_np, current_affine)
        pred_img = resample_from_to(pred_img, (reference_img.shape[:3], reference_img.affine), order=0)
        out_np = np.rint(np.asarray(pred_img.dataobj)).astype(np.uint8, copy=False)

    header = reference_img.header.copy()
    header.set_data_dtype(np.uint8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(out_np, reference_img.affine, header=header), str(output_path))


def fast_axis_aligned_label_backproject(
    pred_np: np.ndarray,
    current_affine: np.ndarray,
    reference_img: nib.Nifti1Image,
) -> np.ndarray | None:
    ref_affine = np.asarray(reference_img.affine, dtype=np.float64)
    cur_affine = np.asarray(current_affine, dtype=np.float64)
    if not np.allclose(cur_affine[:3, :3], ref_affine[:3, :3], atol=1e-4):
        return None
    try:
        start_f = (np.linalg.inv(ref_affine) @ cur_affine @ np.asarray([0.0, 0.0, 0.0, 1.0]))[:3]
    except np.linalg.LinAlgError:
        return None
    start = np.rint(start_f).astype(int)
    if not np.allclose(start_f, start.astype(np.float64), atol=1e-3):
        return None

    ref_shape = tuple(int(x) for x in reference_img.shape[:3])
    pred_shape = tuple(int(x) for x in pred_np.shape[:3])
    end = start + np.asarray(pred_shape, dtype=int)
    dst_start = np.maximum(start, 0)
    dst_end = np.minimum(end, np.asarray(ref_shape, dtype=int))
    if np.any(dst_end <= dst_start):
        return None
    src_start = dst_start - start
    src_end = src_start + (dst_end - dst_start)

    out = np.zeros(ref_shape, dtype=np.uint8)
    out[
        dst_start[0] : dst_end[0],
        dst_start[1] : dst_end[1],
        dst_start[2] : dst_end[2],
    ] = pred_np[
        src_start[0] : src_end[0],
        src_start[1] : src_end[1],
        src_start[2] : src_end[2],
    ]
    return out


def mask_bbox(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    try:
        from scipy import ndimage
    except Exception:
        ndimage = None

    mask_bool = np.asarray(mask, dtype=bool)
    if ndimage is not None:
        objects = ndimage.find_objects(mask_bool)
        if not objects or objects[0] is None:
            return None
        bbox = objects[0]
        lo = np.asarray([axis_slice.start for axis_slice in bbox], dtype=int)
        hi = np.asarray([axis_slice.stop for axis_slice in bbox], dtype=int)
        return lo, hi
    pts = np.argwhere(mask_bool)
    if pts.size == 0:
        return None
    return pts.min(axis=0), pts.max(axis=0) + 1


def shifted_crop_affine(reference_affine: np.ndarray, start_voxel: np.ndarray) -> np.ndarray:
    affine = np.asarray(reference_affine, dtype=np.float64).copy()
    affine[:3, 3] = (np.asarray(reference_affine, dtype=np.float64) @ np.r_[start_voxel.astype(np.float64), 1.0])[:3]
    return affine


def gcp_foreground_bbox(reference_img: nib.Nifti1Image, fg_margin: int) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asanyarray(reference_img.dataobj)
    if arr.ndim > 3:
        arr = arr[..., 0]
    foreground = np.clip(arr, 0, 255) > 0
    bbox = mask_bbox(foreground)
    shape = np.asarray(reference_img.shape[:3], dtype=int)
    if bbox is None:
        return np.zeros(3, dtype=int), shape
    lo, hi = bbox
    margin = np.asarray([int(fg_margin)] * 3, dtype=int)
    return np.maximum(lo - margin, 0), np.minimum(hi + margin, shape)


def sliding_window_starts(size: int, roi_size: int) -> list[int]:
    size = int(size)
    roi_size = int(roi_size)
    if size <= roi_size:
        return [0]
    starts = list(range(0, max(size - roi_size + 1, 1), roi_size))
    last = size - roi_size
    if starts[-1] != last:
        starts.append(last)
    return starts


def align_bbox_to_sliding_windows(
    bbox_lo: np.ndarray,
    bbox_hi: np.ndarray,
    full_lo: np.ndarray,
    full_hi: np.ndarray,
    roi_size: int,
) -> tuple[np.ndarray, np.ndarray] | None:
    aligned_lo: list[int] = []
    aligned_hi: list[int] = []
    for axis in range(3):
        axis_full_lo = int(full_lo[axis])
        axis_full_hi = int(full_hi[axis])
        axis_bbox_lo = int(max(bbox_lo[axis], axis_full_lo))
        axis_bbox_hi = int(min(bbox_hi[axis], axis_full_hi))
        if axis_bbox_hi <= axis_bbox_lo:
            return None
        starts = [axis_full_lo + start for start in sliding_window_starts(axis_full_hi - axis_full_lo, roi_size)]
        selected = [
            start
            for start in starts
            if start < axis_bbox_hi and min(start + int(roi_size), axis_full_hi) > axis_bbox_lo
        ]
        if not selected:
            return None
        aligned_lo.append(min(selected))
        aligned_hi.append(min(max(selected) + int(roi_size), axis_full_hi))
    return np.asarray(aligned_lo, dtype=int), np.asarray(aligned_hi, dtype=int)


def prepare_gcp_local_roi_input(
    args: argparse.Namespace,
    case_dir: Path,
    total_dir: Path | None,
    log_path: Path,
) -> dict[str, Any] | None:
    if total_dir is None:
        append_log(log_path, "GCPV5 local ROI requested but TotalSegmentator masks are unavailable; using full image.")
        return None

    reference_img = nib.load(str(args.image))
    reference_shape = np.asarray(reference_img.shape[:3], dtype=int)
    localizer_rois = parse_name_list(str(args.gcp_local_roi_rois)) or list(FULL_ANALYSIS_ANCHORS)
    bbox_los: list[np.ndarray] = []
    bbox_his: list[np.ndarray] = []
    used_masks: list[str] = []

    for name in localizer_rois:
        mask_path = total_dir / f"{name}.nii.gz"
        if not mask_path.exists():
            continue
        mask = load_mask_on_reference(mask_path, reference_img)
        bbox = mask_bbox(mask)
        if bbox is None:
            continue
        lo, hi = bbox
        bbox_los.append(lo)
        bbox_his.append(hi)
        used_masks.append(name)

    if not bbox_los:
        append_log(log_path, "GCPV5 local ROI found no usable anatomy masks; using full image.")
        return None

    lo = np.min(np.stack(bbox_los, axis=0), axis=0)
    hi = np.max(np.stack(bbox_his, axis=0), axis=0)
    spacing = np.asarray(reference_img.header.get_zooms()[:3], dtype=np.float64)
    spacing = np.maximum(spacing, 1e-6)
    margin_vox = np.ceil(float(args.gcp_local_roi_margin_mm) / spacing).astype(int)
    lo = np.maximum(lo - margin_vox, 0)
    hi = np.minimum(hi + margin_vox, reference_shape)

    if np.any(hi <= lo):
        append_log(log_path, "GCPV5 local ROI bbox is empty after clipping; using full image.")
        return None

    full_fg_lo, full_fg_hi = gcp_foreground_bbox(reference_img, int(args.gcp_fg_margin))
    aligned = align_bbox_to_sliding_windows(lo, hi, full_fg_lo, full_fg_hi, int(args.gcp_roi_size))
    if aligned is None:
        append_log(log_path, "GCPV5 local ROI could not align to full-image sliding-window grid; using full image.")
        return None
    anatomy_lo = lo.copy()
    anatomy_hi = hi.copy()
    lo, hi = aligned

    local_dir = ensure_dir(case_dir / "gcpv5" / "local_roi")
    crop_path = local_dir / f"{args.case_id}_gcpv5_input_roi.nii.gz"
    source = np.asanyarray(reference_img.dataobj)
    slices = tuple(slice(int(lo[i]), int(hi[i])) for i in range(3))
    crop = np.asarray(source[slices])
    crop_affine = shifted_crop_affine(reference_img.affine, lo)
    header = reference_img.header.copy()
    nib.save(nib.Nifti1Image(crop, crop_affine, header=header), str(crop_path))

    roi_summary = {
        "enabled": True,
        "source": "totalseg_bbox",
        "input_path": str(crop_path),
        "reference_path": str(args.image),
        "used_masks": used_masks,
        "margin_mm": float(args.gcp_local_roi_margin_mm),
        "anatomy_bbox_start": [int(x) for x in anatomy_lo.tolist()],
        "anatomy_bbox_end": [int(x) for x in anatomy_hi.tolist()],
        "full_foreground_bbox_start": [int(x) for x in full_fg_lo.tolist()],
        "full_foreground_bbox_end": [int(x) for x in full_fg_hi.tolist()],
        "grid_aligned": True,
        "bbox_start": [int(x) for x in lo.tolist()],
        "bbox_end": [int(x) for x in hi.tolist()],
        "bbox_shape": [int(x) for x in (hi - lo).tolist()],
        "reference_shape": [int(x) for x in reference_shape.tolist()],
    }
    append_log(
        log_path,
        "GCPV5 local ROI enabled: "
        f"masks={','.join(used_masks)}, anatomy_bbox={roi_summary['anatomy_bbox_start']}->{roi_summary['anatomy_bbox_end']}, "
        f"grid_bbox={roi_summary['bbox_start']}->{roi_summary['bbox_end']} "
        f"shape={roi_summary['bbox_shape']}, margin={float(args.gcp_local_roi_margin_mm):.1f}mm.",
    )
    return {
        "image_path": crop_path,
        "bbox_start": lo,
        "bbox_end": hi,
        "summary": roi_summary,
    }


def paste_local_prediction_to_reference(
    crop_prediction_path: Path,
    output_path: Path,
    reference_path: Path,
    bbox_start: np.ndarray,
    bbox_end: np.ndarray,
) -> None:
    reference_img = nib.load(str(reference_path))
    crop_img = nib.load(str(crop_prediction_path))
    crop_label = np.rint(np.asarray(crop_img.dataobj)).astype(np.uint8, copy=False)
    expected_shape = tuple(int(x) for x in (bbox_end - bbox_start).tolist())
    if tuple(crop_label.shape[:3]) != expected_shape:
        target_affine = shifted_crop_affine(reference_img.affine, bbox_start)
        crop_img = resample_from_to(crop_img, (expected_shape, target_affine), order=0)
        crop_label = np.rint(np.asarray(crop_img.dataobj)).astype(np.uint8, copy=False)

    out = np.zeros(reference_img.shape[:3], dtype=np.uint8)
    slices = tuple(slice(int(bbox_start[i]), int(bbox_end[i])) for i in range(3))
    out[slices] = crop_label
    header = reference_img.header.copy()
    header.set_data_dtype(np.uint8)
    nib.save(nib.Nifti1Image(out, reference_img.affine, header=header), str(output_path))


def run_gcpv5(args: argparse.Namespace, case_dir: Path, log_path: Path, total_dir: Path | None = None) -> Path:
    output_dir = ensure_dir(case_dir / "gcpv5" / "prediction_labels_nii")
    output_path = output_dir / f"{args.case_id}_gcpv5_raw.nii.gz"
    summary_path = case_dir / "gcpv5" / "summary.json"
    if output_path.exists() and not args.force:
        append_log(log_path, f"GCPV5 raw label exists, skipping: {output_path}")
        return output_path

    reuse_gcp_path = Path(str(args.reuse_gcp_path)).expanduser() if str(args.reuse_gcp_path).strip() else None
    if reuse_gcp_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if reuse_gcp_path.resolve() != output_path.resolve():
            shutil.copy2(reuse_gcp_path, output_path)
        pred = np.asarray(nib.load(str(output_path)).dataobj)
        write_json(
            summary_path,
            {
                "case_id": args.case_id,
                "source": "reuse_gcp_path",
                "reused_from": str(reuse_gcp_path),
                "output_path": str(output_path),
                "unique_labels": [int(x) for x in np.unique(pred).tolist()],
                "tumor_label": int(args.gcp_tumor_label),
                "tumor_voxels": int((pred == int(args.gcp_tumor_label)).sum()),
            },
        )
        append_log(log_path, f"Reused GCPV5 raw label: {reuse_gcp_path} -> {output_path}")
        return output_path

    if str(args.device).startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError(f"Requested {args.device}, but torch.cuda.is_available() is false.")

    append_log(log_path, f"Running GCPV5 tumor inference with backend={args.gcp_backend}.")
    torch.manual_seed(int(args.seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(args.seed))

    device = str(args.device)
    predictor = None
    gcp_engine_path = ""
    if args.gcp_backend == "torch":
        if str(args.raw_gcp_dir) not in sys.path:
            sys.path.insert(0, str(args.raw_gcp_dir))
        from gcp_unet import build_unet_model

        append_log(log_path, f"Loading GCPV5 model and checkpoint: {args.gcp_checkpoint}")
        model = build_unet_model(use_gcp=False, out_channels=int(args.gcp_num_classes)).to(device)
        checkpoint_obj = load_checkpoint_object(Path(args.gcp_checkpoint), device)
        load_state_dict_allow_adrenal_aux(model, resolve_state_dict(checkpoint_obj))
        model.eval()
        predictor = model
    elif args.gcp_backend == "trt":
        from gcp_trt_runtime import TensorRTPredictor

        gcp_engine_path = str(args.gcp_engine).strip() or str(default_gcp_engine_path(args))
        append_log(log_path, f"Loading GCPV5 TensorRT engine: {gcp_engine_path}")
        predictor = TensorRTPredictor(gcp_engine_path)
    else:
        raise ValueError(f"Unsupported GCPV5 backend: {args.gcp_backend}")

    local_roi = (
        prepare_gcp_local_roi_input(args, case_dir, total_dir, log_path)
        if should_use_gcp_local_roi(args)
        else None
    )
    inference_image = Path(local_roi["image_path"]) if local_roi is not None else Path(args.image)

    append_log(log_path, f"Loading and preprocessing image: {inference_image}")
    blend_mode = "constant" if float(args.gcp_overlap) <= 0.0 else "gaussian"
    amp_enabled = bool(args.gcp_amp) and str(device).startswith("cuda") and args.gcp_backend == "torch"
    stitch_device = str(args.gcp_stitch_device)

    def autocast_context():
        return (
            torch.autocast(device_type="cuda", dtype=torch.float16, enabled=True)
            if amp_enabled
            else nullcontext()
        )

    def infer_image_to_label(
        image_path: Path,
        target_path: Path,
        label: str,
        crop_foreground: bool = True,
    ) -> tuple[int, tuple[int, ...]]:
        dataset = Dataset(
            data=[{"image": str(image_path), "name": args.case_id}],
            transform=build_image_only_transforms(
                int(args.gcp_roi_size),
                int(args.gcp_fg_margin),
                crop_foreground=bool(crop_foreground),
            ),
        )
        loader = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0, pin_memory=True)
        batch = next(iter(loader))
        images = batch["image"].to(device)
        input_shape = tuple(int(x) for x in images.shape)
        append_log(log_path, f"GCPV5 {label} input tensor shape: {input_shape}")
        append_log(
            log_path,
            "Starting MONAI sliding-window inference "
            f"(roi={int(args.gcp_roi_size)}, sw_batch={int(args.gcp_sw_batch_size)}, "
            f"overlap={float(args.gcp_overlap)}, mode={blend_mode}, amp={amp_enabled}, "
            f"stitch_device={stitch_device}, pass={label}).",
        )
        logits = None
        actual_roi_size = int(args.gcp_roi_size)
        last_oom: BaseException | None = None
        for roi_size in gcp_retry_roi_sizes(args):
            actual_roi_size = int(roi_size)
            try:
                append_log(log_path, f"GCPV5 sliding-window attempt ({label}): roi={roi_size}")
                with autocast_context():
                    logits = sliding_window_inference(
                        inputs=images,
                        roi_size=(roi_size, roi_size, roi_size),
                        sw_batch_size=int(args.gcp_sw_batch_size),
                        predictor=predictor,
                        overlap=float(args.gcp_overlap),
                        mode=blend_mode,
                        sw_device=device,
                        device=stitch_device,
                        progress=not bool(args.no_progress),
                    )
                break
            except Exception as exc:
                if not cuda_oom(exc):
                    raise
                last_oom = exc
                append_log(log_path, f"GCPV5 OOM at roi={roi_size}; clearing CUDA cache and retrying smaller ROI.")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
        if logits is None:
            raise RuntimeError("GCPV5 inference failed after low-memory ROI retries.") from last_oom
        append_log(log_path, f"Saving GCPV5 raw label ({label}).")
        pred_cls = torch.argmax(logits, dim=1).long()
        save_prediction_label_nifti(batch, pred_cls, target_path)
        return actual_roi_size, input_shape

    actual_roi_size = int(args.gcp_roi_size)
    input_shape: tuple[int, ...] = ()
    inference_pass = "full"
    fallback_triggered = False
    with torch.inference_mode():
        if local_roi is not None:
            crop_output_path = output_dir / f"{args.case_id}_gcpv5_raw_local_crop.nii.gz"
            actual_roi_size, input_shape = infer_image_to_label(
                inference_image,
                crop_output_path,
                "local_roi",
                crop_foreground=False,
            )
            paste_local_prediction_to_reference(
                crop_output_path,
                output_path,
                Path(args.image),
                np.asarray(local_roi["bbox_start"], dtype=int),
                np.asarray(local_roi["bbox_end"], dtype=int),
            )
            pred_local = np.asarray(nib.load(str(output_path)).dataobj)
            local_tumor_voxels = int((pred_local == int(args.gcp_tumor_label)).sum())
            if local_tumor_voxels < int(args.gcp_local_roi_fallback_min_voxels):
                append_log(
                    log_path,
                    "GCPV5 local ROI predicted too few tumor voxels "
                    f"({local_tumor_voxels} < {int(args.gcp_local_roi_fallback_min_voxels)}); falling back to full image.",
                )
                fallback_triggered = True
                inference_pass = "full_fallback"
                actual_roi_size, input_shape = infer_image_to_label(Path(args.image), output_path, "full_fallback")
            else:
                inference_pass = "local_roi"
                append_log(log_path, f"GCPV5 local ROI tumor voxels before APR: {local_tumor_voxels}")
        else:
            actual_roi_size, input_shape = infer_image_to_label(Path(args.image), output_path, "full")

    pred = np.asarray(nib.load(str(output_path)).dataobj)
    summary = {
        "case_id": args.case_id,
        "checkpoint": str(args.gcp_checkpoint),
        "device": device,
        "requested_roi_size": int(args.gcp_roi_size),
        "actual_roi_size": int(actual_roi_size),
        "stitch_device": stitch_device,
        "overlap": float(args.gcp_overlap),
        "input_shape": [int(x) for x in input_shape],
        "output_path": str(output_path),
        "unique_labels": [int(x) for x in np.unique(pred).tolist()],
        "tumor_label": int(args.gcp_tumor_label),
        "tumor_voxels": int((pred == int(args.gcp_tumor_label)).sum()),
        "backend": str(args.gcp_backend),
        "engine": gcp_engine_path,
        "local_roi": local_roi["summary"] if local_roi is not None else {"enabled": False},
        "inference_pass": inference_pass,
        "fallback_triggered": bool(fallback_triggered),
    }
    write_json(summary_path, summary)
    append_log(log_path, f"GCPV5 raw label saved: {output_path}")
    return output_path


def rois_for_mode(mode: str) -> list[str] | None:
    if mode == "jetson_fast":
        return list(JETSON_FAST_ROIS)
    if mode == "abdomen":
        return list(ABDOMEN_ROIS)
    if mode == "full_total":
        return None
    raise ValueError(f"Unknown mode: {mode}")


def run_totalseg(args: argparse.Namespace, case_dir: Path, log_path: Path) -> Path:
    raw_dir = ensure_dir(case_dir / "total" / "raw_masks")
    stats_path = case_dir / "total" / "totalseg_summary.json"
    source_dir = Path(str(args.totalseg_existing_dir)).expanduser() if str(args.totalseg_existing_dir).strip() else None

    if args.force and raw_dir.exists():
        shutil.rmtree(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)

    if source_dir is not None:
        if not source_dir.exists():
            raise FileNotFoundError(f"--totalseg-existing-dir not found: {source_dir}")
        roi_subset = rois_for_mode(args.mode)
        source_masks = sorted(source_dir.glob("*.nii.gz"))
        selected = set(roi_subset or [p.name[:-7] for p in source_masks if p.name.endswith(".nii.gz")])
        copied: list[str] = []
        for src in source_masks:
            organ_name = src.name[:-7] if src.name.endswith(".nii.gz") else src.stem
            if organ_name not in selected:
                continue
            shutil.copy2(src, raw_dir / src.name)
            copied.append(src.name)
        if not copied:
            raise FileNotFoundError(f"No matching TotalSegmentator masks copied from: {source_dir}")
        write_json(
            stats_path,
            {
                "case_id": args.case_id,
                "mode": args.mode,
                "source": str(source_dir),
                "copied_mask_count": len(copied),
                "raw_dir": str(raw_dir),
                "masks": sorted(copied),
            },
        )
        append_log(log_path, f"Copied TotalSegmentator masks from existing dir: {source_dir} -> {raw_dir}")
        return raw_dir

    existing = sorted(raw_dir.glob("*.nii.gz"))
    if existing and not args.force:
        append_log(log_path, f"TotalSegmentator masks exist, skipping: {raw_dir}")
        return raw_dir

    cmd = [
        "TotalSegmentator",
        "-i",
        str(args.image),
        "-o",
        str(raw_dir),
        "-ta",
        "total",
        "-d",
        str(args.totalseg_device),
    ]
    if args.totalseg_quiet:
        cmd.append("-q")
    roi_subset = rois_for_mode(args.mode)
    if roi_subset:
        cmd.extend(["-rs", *roi_subset])
        weights_root = Path(os.environ.get("TOTALSEG_WEIGHTS_PATH", Path.home() / ".totalsegmentator/nnunet/results")).expanduser()
        crop_6mm = weights_root / "Dataset298_TotalSegmentator_total_6mm_1559subj"
        crop_3mm = weights_root / "Dataset297_TotalSegmentator_total_3mm_1559subj"
        if args.totalseg_robust_crop or (not crop_6mm.exists() and crop_3mm.exists()):
            cmd.append("-rc")
            append_log(
                log_path,
                "Using TotalSegmentator robust crop (-rc) to avoid missing/slow Dataset298 6mm crop model.",
            )
    if args.totalseg_fast:
        cmd.append("-f")
    if args.totalseg_fastest:
        cmd.append("-ff")

    env = runtime_env(args)
    append_log(log_path, "Running TotalSegmentator: " + " ".join(cmd))
    with log_path.open("a", encoding="utf-8") as log_f:
        subprocess.run(cmd, cwd=str(PROJECT_DIR), env=env, stdout=log_f, stderr=subprocess.STDOUT, check=True)

    masks = sorted(path.name for path in raw_dir.glob("*.nii.gz"))
    write_json(
        stats_path,
        {
            "case_id": args.case_id,
            "mode": args.mode,
            "roi_subset": roi_subset or "all",
            "mask_count": len(masks),
            "raw_dir": str(raw_dir),
            "masks": masks,
        },
    )
    append_log(log_path, f"TotalSegmentator masks saved: {raw_dir} ({len(masks)} files)")
    return raw_dir


def load_label(path: Path, dtype: np.dtype = np.uint16) -> tuple[np.ndarray, nib.Nifti1Image]:
    img = nib.load(str(path))
    arr = np.rint(np.asarray(img.dataobj)).astype(dtype, copy=False)
    return arr, img


def load_mask_on_reference(mask_path: Path, reference_img: nib.Nifti1Image) -> np.ndarray:
    img = nib.load(str(mask_path))
    if tuple(img.shape[:3]) != tuple(reference_img.shape[:3]) or not np.allclose(img.affine, reference_img.affine):
        img = resample_from_to(img, (reference_img.shape[:3], reference_img.affine), order=0)
    arr = np.asarray(img.dataobj)
    return arr > 0


def build_anatomy_for_apr(
    total_dir: Path,
    reference_img: nib.Nifti1Image,
    output_path: Path,
    anchor_rois: list[str] | None,
) -> np.ndarray:
    anatomy = np.zeros(reference_img.shape[:3], dtype=np.uint8)
    allowed = set(anchor_rois) if anchor_rois is not None else None
    for total_name, apr_name in TOTAL_TO_OTAFV2.items():
        if allowed is not None and total_name not in allowed:
            continue
        mask_path = total_dir / f"{total_name}.nii.gz"
        if not mask_path.exists():
            continue
        mask = load_mask_on_reference(mask_path, reference_img)
        anatomy[mask] = int(OTAFV2_LABEL_IDS[apr_name])

    vertebrae_paths = sorted(total_dir.glob("vertebrae_*.nii.gz")) if allowed is None or "vertebrae" in allowed else []
    if vertebrae_paths:
        vertebrae = np.zeros(reference_img.shape[:3], dtype=bool)
        for path in vertebrae_paths:
            vertebrae |= load_mask_on_reference(path, reference_img)
        anatomy[vertebrae] = int(OTAFV2_LABEL_IDS["vertebrae"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = reference_img.header.copy()
    header.set_data_dtype(np.uint8)
    nib.save(nib.Nifti1Image(anatomy, reference_img.affine, header), str(output_path))
    return anatomy


def spacing_mm(img: nib.Nifti1Image) -> tuple[float, float, float]:
    return tuple(float(x) for x in img.header.get_zooms()[:3])


def connected_components(mask: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    try:
        from scipy import ndimage
    except Exception as exc:
        raise RuntimeError("scipy is required for connected component analysis.") from exc

    mask_bool = np.asarray(mask, dtype=bool)
    objects = ndimage.find_objects(mask_bool)
    labels = np.zeros(mask_bool.shape, dtype=np.int32)
    if not objects or objects[0] is None:
        return labels, []
    bbox = objects[0]
    bbox_lo = np.asarray([axis_slice.start for axis_slice in bbox], dtype=int)
    crop = mask_bool[bbox]
    crop_labels, n_comp = ndimage.label(crop, structure=np.ones((3, 3, 3), dtype=np.uint8))
    labels[bbox] = crop_labels.astype(np.int32, copy=False)
    rows: list[dict[str, Any]] = []
    for comp_id in range(1, int(n_comp) + 1):
        pts = np.argwhere(crop_labels == comp_id)
        if pts.size == 0:
            continue
        pts += bbox_lo.reshape(1, 3)
        rows.append(
            {
                "component_id": int(comp_id),
                "voxel_count": int(pts.shape[0]),
                "centroid_voxel": [float(x) for x in pts.mean(axis=0)],
                "bbox_min_voxel": [int(x) for x in pts.min(axis=0)],
                "bbox_max_voxel": [int(x) for x in pts.max(axis=0)],
            }
        )
    rows.sort(key=lambda x: int(x["voxel_count"]), reverse=True)
    return labels, rows


def keep_largest_connected_component(mask: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]], int]:
    mask_bool = np.asarray(mask, dtype=bool)
    labels, components = connected_components(mask_bool)
    if not components:
        return np.zeros(mask_bool.shape, dtype=bool), components, 0
    largest_component_id = int(components[0]["component_id"])
    largest = labels == largest_component_id
    removed_voxels = int(mask_bool.sum() - largest.sum())
    return largest, components, removed_voxels


def run_apr(args: argparse.Namespace, case_dir: Path, gcp_path: Path, total_dir: Path, log_path: Path) -> tuple[Path, dict[str, Any]]:
    if str(args.package_dir) not in sys.path:
        sys.path.insert(0, str(args.package_dir))
    from fusion.otafv2_apr import apply_apr_to_tumor
    from fusion.otafv2_config import OTAFV2Config

    apr_dir = ensure_dir(case_dir / "apr")
    refined_path = apr_dir / f"{args.case_id}_tumor_apr_label10.nii.gz"
    binary_path = apr_dir / f"{args.case_id}_tumor_apr_mask.nii.gz"
    anatomy_path = case_dir / "total" / "anatomy_for_apr.nii.gz"
    component_csv = apr_dir / "apr_component_metrics.csv"
    summary_path = apr_dir / "summary_apr.json"

    raw_label, pred_img = load_label(gcp_path, dtype=np.uint8)
    raw_tumor = raw_label == int(args.gcp_tumor_label)
    apr_anchor_rois = parse_name_list(str(args.apr_anchor_rois))
    anatomy = build_anatomy_for_apr(total_dir, pred_img, anatomy_path, apr_anchor_rois)

    cfg = OTAFV2Config()
    cfg.apr_enabled = True
    cfg.apr_tau = float(args.apr_tau)
    cfg.apr_min_component_voxels = int(args.apr_min_component_voxels)
    cfg.apr_good_distance_mm = float(args.apr_good_distance_mm)
    cfg.apr_bad_distance_mm = float(args.apr_bad_distance_mm)
    cfg.apr_volume_ref_mm3 = float(args.apr_volume_ref_mm3)
    cfg.apr_weight_anatomy = float(args.apr_weight_anatomy)
    cfg.apr_weight_geometry = float(args.apr_weight_geometry)
    cfg.apr_weight_adrenal = 0.0
    cfg.apr_adrenal_bonus_weight = 0.0

    anchor_text = "all available anchors" if apr_anchor_rois is None else ", ".join(apr_anchor_rois)
    append_log(log_path, f"Running APR with TotalSegmentator anatomy anchors: {anchor_text}.")
    result = apply_apr_to_tumor(anatomy, raw_tumor, spacing_mm(pred_img), cfg, args.case_id)
    refined_before_lcc = np.asarray(result["refined_tumor_mask"], dtype=bool)
    refined, refined_components_before_lcc, lcc_removed_voxels = keep_largest_connected_component(refined_before_lcc)
    final_kept_component_count = 1 if refined.any() else 0
    if len(refined_components_before_lcc) > 1:
        append_log(
            log_path,
            "Largest tumor connected component retained: "
            f"{int(refined.sum())}/{int(refined_before_lcc.sum())} voxels, "
            f"removed {lcc_removed_voxels} voxels across "
            f"{len(refined_components_before_lcc) - 1} smaller components.",
        )

    header = pred_img.header.copy()
    header.set_data_dtype(np.uint8)
    nib.save(nib.Nifti1Image(refined.astype(np.uint8), pred_img.affine, header), str(binary_path))
    label10 = np.zeros(refined.shape, dtype=np.uint8)
    label10[refined] = int(args.gcp_tumor_label)
    nib.save(nib.Nifti1Image(label10, pred_img.affine, header), str(refined_path))

    component_rows = list(result.get("component_records", []))
    write_csv(component_csv, component_rows)
    apr_removed_voxels = int(result.get("removed_voxel_count", 0))
    apr_removed_components = int(result.get("removed_component_count", 0))
    summary = {
        "case_id": args.case_id,
        "raw_tumor_voxels": int(raw_tumor.sum()),
        "apr_refined_tumor_voxels_before_largest_component_filter": int(refined_before_lcc.sum()),
        "refined_tumor_voxels": int(refined.sum()),
        "removed_voxel_count": int(raw_tumor.sum() - refined.sum()),
        "apr_removed_voxel_count": apr_removed_voxels,
        "largest_component_removed_voxel_count": int(lcc_removed_voxels),
        "raw_component_count": int(result.get("raw_component_count", 0)),
        "apr_kept_component_count_before_largest_filter": int(result.get("kept_component_count", 0)),
        "component_count_before_largest_filter": int(len(refined_components_before_lcc)),
        "kept_component_count": int(final_kept_component_count),
        "removed_component_count": int(
            apr_removed_components + max(0, len(refined_components_before_lcc) - final_kept_component_count)
        ),
        "largest_component_filter_applied": bool(len(refined_components_before_lcc) > 1),
        "largest_component_voxels": int(refined.sum()),
        "apr_applied": bool(result.get("apr_applied", False)),
        "skip_reason": str(result.get("skip_reason", "")),
        "apr_anchor_rois": apr_anchor_rois or "all",
        "anatomy_for_apr": str(anatomy_path),
        "tumor_apr_label10": str(refined_path),
        "tumor_apr_mask": str(binary_path),
        "component_csv": str(component_csv),
        "apr_config": {
            "apr_tau": float(cfg.apr_tau),
            "apr_min_component_voxels": int(cfg.apr_min_component_voxels),
            "apr_good_distance_mm": float(cfg.apr_good_distance_mm),
            "apr_bad_distance_mm": float(cfg.apr_bad_distance_mm),
            "apr_weight_anatomy": float(cfg.apr_weight_anatomy),
            "apr_weight_geometry": float(cfg.apr_weight_geometry),
            "apr_weight_adrenal": float(cfg.apr_weight_adrenal),
        },
    }
    write_json(summary_path, summary)
    append_log(log_path, f"APR tumor label saved: {refined_path}")
    return refined_path, summary


def compose_final_label(
    args: argparse.Namespace,
    case_dir: Path,
    total_dir: Path,
    tumor_apr_path: Path,
    log_path: Path,
) -> tuple[Path, dict[int, str]]:
    fusion_dir = ensure_dir(case_dir / "fusion")
    final_path = fusion_dir / f"{args.case_id}_final_seg.nii.gz"
    label_map_path = fusion_dir / "label_map.json"

    tumor_label, tumor_img = load_label(tumor_apr_path, dtype=np.uint8)
    final = np.zeros(tumor_label.shape, dtype=np.uint16)
    label_map: dict[int, str] = {0: "background"}

    next_label = 1
    for mask_path in sorted(total_dir.glob("*.nii.gz")):
        organ_name = mask_path.name[:-7] if mask_path.name.endswith(".nii.gz") else mask_path.stem
        mask = load_mask_on_reference(mask_path, tumor_img)
        if not mask.any():
            continue
        final[mask] = next_label
        label_map[next_label] = f"totalseg:{organ_name}"
        next_label += 1

    tumor_fusion_label = next_label
    final[tumor_label == int(args.gcp_tumor_label)] = tumor_fusion_label
    label_map[tumor_fusion_label] = "tumor:gcpv5_apr"

    header = tumor_img.header.copy()
    header.set_data_dtype(np.uint16)
    nib.save(nib.Nifti1Image(final, tumor_img.affine, header), str(final_path))
    write_json(
        label_map_path,
        {
            "case_id": args.case_id,
            "final_seg": str(final_path),
            "tumor_priority": True,
            "label_map": {str(k): v for k, v in label_map.items()},
        },
    )
    append_log(log_path, f"Final fused label saved: {final_path}")
    return final_path, label_map


def surface_points(mask: np.ndarray, spacing: tuple[float, float, float]) -> np.ndarray:
    try:
        from scipy import ndimage
    except Exception:
        ndimage = None

    mask = np.asarray(mask, dtype=bool)
    if ndimage is not None:
        objects = ndimage.find_objects(mask)
        if not objects or objects[0] is None:
            return np.empty((0, 3), dtype=np.float64)
        bbox = objects[0]
        bbox_lo = np.asarray([axis_slice.start for axis_slice in bbox], dtype=int)
        bbox_hi = np.asarray([axis_slice.stop for axis_slice in bbox], dtype=int)
    else:
        pts_all = np.argwhere(mask)
        if pts_all.size == 0:
            return np.empty((0, 3), dtype=np.float64)
        bbox_lo = pts_all.min(axis=0)
        bbox_hi = pts_all.max(axis=0) + 1
    lo = np.maximum(bbox_lo - 1, 0)
    hi = np.minimum(bbox_hi + 1, np.asarray(mask.shape, dtype=int))
    crop = mask[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]]
    if ndimage is not None:
        eroded = ndimage.binary_erosion(crop, structure=np.ones((3, 3, 3), dtype=bool), border_value=0)
    else:
        eroded = np.zeros_like(crop)
    surface = crop & ~eroded
    pts = np.argwhere(surface if surface.any() else crop)
    pts += lo.reshape(1, 3)
    return pts.astype(np.float64) * np.asarray(spacing, dtype=np.float64).reshape(1, 3)


def min_surface_distance(mask_a: np.ndarray, mask_b: np.ndarray, spacing: tuple[float, float, float]) -> float:
    try:
        from scipy.spatial import cKDTree
    except Exception:
        return float("nan")
    pts_a = surface_points(mask_a, spacing)
    pts_b = surface_points(mask_b, spacing)
    if pts_a.size == 0 or pts_b.size == 0:
        return float("nan")
    tree = cKDTree(pts_b)
    try:
        distances, _ = tree.query(pts_a, k=1, workers=-1)
    except TypeError:
        distances, _ = tree.query(pts_a, k=1)
    return float(np.min(distances)) if distances.size else float("nan")


def json_number(value: float | int | None, digits: int | None = 3) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    value_f = float(value)
    if not np.isfinite(value_f):
        return None
    return round(value_f, digits) if digits is not None else value_f


def distance_category(distance_mm: float | None, overlap_voxels: int = 0) -> str:
    if overlap_voxels > 0:
        return "overlap"
    if distance_mm is None or not np.isfinite(float(distance_mm)):
        return "unavailable"
    distance = float(distance_mm)
    if distance <= 1.5:
        return "abutment"
    if distance <= 5.0:
        return "close_5mm"
    if distance <= 10.0:
        return "near_10mm"
    return "separate"


def roi_group(name: str) -> str:
    if name in MAJOR_VESSEL_ROIS:
        return "major_vessel"
    if name in ADRENAL_ROIS:
        return "adrenal"
    if name in KIDNEY_ROIS:
        return "kidney"
    if name in BOWEL_ROIS:
        return "bowel"
    if name in SOLID_ORGAN_ROIS:
        return "solid_organ"
    if name in MUSCULOSKELETAL_ROIS:
        return "musculoskeletal"
    if name.startswith("vertebrae_"):
        return "vertebra"
    return "other"


def load_image_data_on_reference(image_path: Path, reference_img: nib.Nifti1Image) -> np.ndarray:
    img = nib.load(str(image_path))
    if tuple(img.shape[:3]) != tuple(reference_img.shape[:3]) or not np.allclose(img.affine, reference_img.affine):
        img = resample_from_to(img, (reference_img.shape[:3], reference_img.affine), order=1)
    arr = np.asarray(img.dataobj, dtype=np.float32)
    return arr[..., 0] if arr.ndim == 4 else arr


def ct_intensity_stats(image_path: Path, tumor: np.ndarray, reference_img: nib.Nifti1Image) -> dict[str, Any]:
    if not tumor.any():
        return {"available": False, "reason": "empty_tumor_mask"}
    try:
        image = load_image_data_on_reference(image_path, reference_img)
    except Exception as exc:
        return {"available": False, "reason": f"image_load_failed: {exc}"}
    values = np.asarray(image[tumor], dtype=np.float32)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"available": False, "reason": "no_finite_voxels"}
    percentiles = np.percentile(values, [1, 5, 25, 50, 75, 95, 99])
    return {
        "available": True,
        "voxel_count": int(values.size),
        "mean_hu": json_number(float(np.mean(values)), 2),
        "median_hu": json_number(float(percentiles[3]), 2),
        "std_hu": json_number(float(np.std(values)), 2),
        "min_hu": json_number(float(np.min(values)), 2),
        "max_hu": json_number(float(np.max(values)), 2),
        "percentiles_hu": {
            "p01": json_number(float(percentiles[0]), 2),
            "p05": json_number(float(percentiles[1]), 2),
            "p25": json_number(float(percentiles[2]), 2),
            "p50": json_number(float(percentiles[3]), 2),
            "p75": json_number(float(percentiles[4]), 2),
            "p95": json_number(float(percentiles[5]), 2),
            "p99": json_number(float(percentiles[6]), 2),
        },
        "low_density_fraction_lt_10hu": json_number(float(np.mean(values < 10.0)), 4),
        "fat_density_fraction_lt_minus_10hu": json_number(float(np.mean(values < -10.0)), 4),
        "high_density_fraction_gt_150hu": json_number(float(np.mean(values > 150.0)), 4),
        "very_high_density_fraction_gt_200hu": json_number(float(np.mean(values > 200.0)), 4),
        "note": "HU statistics are descriptive and depend on CT phase/acquisition.",
    }


def organ_relation_metrics(
    total_dir: Path,
    tumor: np.ndarray,
    reference_img: nib.Nifti1Image,
    spacing: tuple[float, float, float],
    voxel_volume: float,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    try:
        from scipy.spatial import cKDTree
    except Exception:
        cKDTree = None

    relations: dict[str, dict[str, Any]] = {}
    nearest: list[dict[str, Any]] = []
    tumor_surface = surface_points(tumor, spacing) if tumor.any() else np.empty((0, 3), dtype=np.float64)
    tumor_tree = cKDTree(tumor_surface) if cKDTree is not None and tumor_surface.size else None
    for mask_path in sorted(total_dir.glob("*.nii.gz")):
        organ_name = mask_path.name[:-7] if mask_path.name.endswith(".nii.gz") else mask_path.stem
        mask = load_mask_on_reference(mask_path, reference_img)
        organ_voxels = int(mask.sum())
        if organ_voxels == 0:
            continue
        overlap_voxels = int((tumor & mask).sum())
        if tumor_tree is not None:
            organ_surface = surface_points(mask, spacing)
            if organ_surface.size:
                try:
                    distances, _ = tumor_tree.query(organ_surface, k=1, workers=-1)
                except TypeError:
                    distances, _ = tumor_tree.query(organ_surface, k=1)
                distance = float(np.min(distances)) if distances.size else float("nan")
            else:
                distance = float("nan")
        else:
            distance = min_surface_distance(tumor, mask, spacing) if tumor.any() else float("nan")
        distance_value = json_number(distance, 3)
        category = distance_category(distance, overlap_voxels)
        row = {
            "name": organ_name,
            "group": roi_group(organ_name),
            "organ_voxels": organ_voxels,
            "organ_volume_ml": json_number(organ_voxels * voxel_volume / 1000.0, 3),
            "min_surface_distance_mm": distance_value,
            "distance_category": category,
            "overlap_voxels": overlap_voxels,
            "overlap_volume_ml": json_number(overlap_voxels * voxel_volume / 1000.0, 3),
            "contact_or_overlap": bool(overlap_voxels > 0 or category == "abutment"),
            "close_within_5mm": bool(distance_value is not None and float(distance_value) <= 5.0),
            "near_within_10mm": bool(distance_value is not None and float(distance_value) <= 10.0),
        }
        relations[organ_name] = row
        if distance_value is not None:
            nearest.append(
                {
                    "name": organ_name,
                    "group": row["group"],
                    "min_surface_distance_mm": distance_value,
                    "distance_category": category,
                    "overlap_voxels": overlap_voxels,
                }
            )
    nearest.sort(key=lambda item: float(item["min_surface_distance_mm"]))
    return relations, nearest


def relation_min(relations: dict[str, dict[str, Any]], names: set[str]) -> dict[str, Any] | None:
    rows = [
        row for name, row in relations.items()
        if name in names and row.get("min_surface_distance_mm") is not None
    ]
    if not rows:
        return None
    return min(rows, key=lambda row: float(row["min_surface_distance_mm"]))


def assess_origin(relations: dict[str, dict[str, Any]], side: str) -> dict[str, Any]:
    left_adrenal = relations.get("adrenal_gland_left")
    right_adrenal = relations.get("adrenal_gland_right")
    adrenal_rows = [row for row in [left_adrenal, right_adrenal] if row and row.get("min_surface_distance_mm") is not None]
    nearest_adrenal = min(adrenal_rows, key=lambda row: float(row["min_surface_distance_mm"])) if adrenal_rows else None
    nearest_kidney = relation_min(relations, KIDNEY_ROIS)
    nearest_vessel = relation_min(relations, MAJOR_VESSEL_ROIS)

    if nearest_adrenal and float(nearest_adrenal["min_surface_distance_mm"]) <= 2.0:
        side_text = "left" if nearest_adrenal["name"].endswith("_left") else "right"
        return {
            "suspected_origin": f"{side_text}_adrenal_region",
            "confidence": "moderate",
            "basis": [
                f"tumor is {nearest_adrenal['min_surface_distance_mm']} mm from {nearest_adrenal['name']}",
                f"nearest kidney side is {side}",
            ],
        }
    if nearest_adrenal and float(nearest_adrenal["min_surface_distance_mm"]) <= 5.0:
        return {
            "suspected_origin": "para_adrenal_or_adrenal_region",
            "confidence": "low_to_moderate",
            "basis": [f"tumor is close to {nearest_adrenal['name']} ({nearest_adrenal['min_surface_distance_mm']} mm)"],
        }
    if nearest_vessel and float(nearest_vessel["min_surface_distance_mm"]) <= 20.0:
        return {
            "suspected_origin": "retroperitoneal_extra_adrenal_region_possible",
            "confidence": "low",
            "basis": [f"tumor is near {nearest_vessel['name']} ({nearest_vessel['min_surface_distance_mm']} mm) without clear adrenal contact"],
        }
    basis = []
    if nearest_kidney:
        basis.append(f"nearest kidney-related side is {side}")
    return {"suspected_origin": "uncertain", "confidence": "low", "basis": basis}


def assess_segmentation_quality(raw_tumor_voxels: int, apr_tumor_voxels: int, apr_summary: dict[str, Any]) -> dict[str, Any]:
    removed = int(apr_summary.get("removed_voxel_count", max(raw_tumor_voxels - apr_tumor_voxels, 0)))
    removed_ratio = (removed / raw_tumor_voxels) if raw_tumor_voxels > 0 else None
    raw_components = int(apr_summary.get("raw_component_count", 0))
    kept_components = int(apr_summary.get("kept_component_count", 0))
    flags: list[str] = []
    confidence = "high"
    if apr_tumor_voxels == 0:
        confidence = "low"
        flags.append("APR 后肿瘤体素为 0，需人工复核。")
    if removed_ratio is not None and removed_ratio > 0.70:
        confidence = "low"
        flags.append(f"APR 删除比例较高（{removed_ratio:.1%}），原始预测假阳性成分可能较多。")
    elif removed_ratio is not None and removed_ratio > 0.30:
        confidence = "moderate"
        flags.append(f"APR 删除比例为 {removed_ratio:.1%}，建议结合图像复核。")
    if raw_components > 10:
        confidence = "moderate" if confidence == "high" else confidence
        flags.append(f"原始肿瘤组件数较多（{raw_components} 个），提示原始预测较碎片化。")
    if kept_components == 0 and raw_tumor_voxels > 0:
        confidence = "low"
        flags.append("APR 未保留肿瘤组件。")
    return {
        "confidence": confidence,
        "raw_tumor_voxels": int(raw_tumor_voxels),
        "apr_tumor_voxels": int(apr_tumor_voxels),
        "removed_voxel_count": removed,
        "removed_ratio": json_number(removed_ratio, 4),
        "raw_component_count": raw_components,
        "kept_component_count": kept_components,
        "flags": flags,
    }


def assess_risk(
    tumor_burden: dict[str, Any],
    origin: dict[str, Any],
    relations: dict[str, dict[str, Any]],
    nearest_organs: list[dict[str, Any]],
    segmentation_quality: dict[str, Any],
) -> dict[str, Any]:
    factors: list[dict[str, Any]] = []
    protective: list[str] = []
    imaging_points = 0
    surgical_points = 0

    max_diameter = tumor_burden.get("max_diameter_mm")
    component_count = int(tumor_burden.get("component_count") or 0)
    suspected_origin = str(origin.get("suspected_origin", "uncertain"))

    if max_diameter is not None and float(max_diameter) >= 50.0:
        imaging_points += 2
        surgical_points += 1
        factors.append({"code": "large_tumor_ge_50mm", "severity": "high", "reason": f"最大径 {max_diameter} mm，达到大肿瘤阈值。"})
    elif max_diameter is not None and float(max_diameter) >= 30.0:
        imaging_points += 1
        factors.append({"code": "tumor_ge_30mm", "severity": "moderate", "reason": f"最大径 {max_diameter} mm，肿瘤体积负荷增加。"})
    elif max_diameter is not None:
        protective.append(f"最大径 {max_diameter} mm，影像体积负荷较低。")

    if component_count > 1:
        imaging_points += 2
        factors.append({"code": "multifocal_after_apr", "severity": "high", "reason": f"APR 后仍有 {component_count} 个肿瘤组件，提示多灶可能。"})
    elif component_count == 1:
        protective.append("APR 后为单一肿瘤组件。")

    if "extra_adrenal" in suspected_origin:
        imaging_points += 1
        factors.append({"code": "possible_extra_adrenal_location", "severity": "moderate", "reason": "影像定位提示可能为肾上腺外腹膜后区域，PPGL 随访风险需更谨慎。"})

    major_vessel_rows = [
        row for name, row in relations.items()
        if name in MAJOR_VESSEL_ROIS and row.get("min_surface_distance_mm") is not None
    ]
    closest_vessel = min(major_vessel_rows, key=lambda row: float(row["min_surface_distance_mm"])) if major_vessel_rows else None
    if closest_vessel:
        vessel_distance = float(closest_vessel["min_surface_distance_mm"])
        if closest_vessel["overlap_voxels"] > 0 or vessel_distance <= 2.0:
            surgical_points += 2
            factors.append({"code": "major_vessel_abutment", "severity": "high", "reason": f"肿瘤与 {closest_vessel['name']} 距离 {vessel_distance:.2f} mm，存在大血管邻近风险。"})
        elif vessel_distance <= 5.0:
            surgical_points += 1
            factors.append({"code": "major_vessel_close_5mm", "severity": "moderate", "reason": f"肿瘤距 {closest_vessel['name']} {vessel_distance:.2f} mm。"})
        else:
            protective.append(f"最近大血管为 {closest_vessel['name']}，距离 {vessel_distance:.2f} mm。")

    critical_close = [
        row for row in relations.values()
        if row.get("group") in {"bowel", "solid_organ", "kidney", "adrenal"}
        and row.get("min_surface_distance_mm") is not None
        and float(row["min_surface_distance_mm"]) <= 2.0
    ]
    if critical_close:
        surgical_points += 1
        names = ", ".join(row["name"] for row in critical_close[:5])
        factors.append({"code": "critical_organ_abutment", "severity": "moderate", "reason": f"肿瘤贴近或重叠关键器官：{names}。"})

    if segmentation_quality.get("confidence") == "low":
        factors.append({"code": "low_segmentation_confidence", "severity": "quality", "reason": "分割质量置信度偏低，风险结论需人工复核。"})
    elif segmentation_quality.get("confidence") == "moderate":
        factors.append({"code": "moderate_segmentation_confidence", "severity": "quality", "reason": "分割质量中等，建议结合原始 CT 和分割叠加图复核。"})

    imaging_level = "high" if imaging_points >= 3 else "intermediate" if imaging_points >= 1 else "low"
    surgical_level = "high" if surgical_points >= 2 else "intermediate" if surgical_points >= 1 else "low"
    overall_level = "high" if "high" in {imaging_level, surgical_level} else "intermediate" if "intermediate" in {imaging_level, surgical_level} else "low"

    reasons = [item["reason"] for item in factors if item.get("severity") != "quality"]
    if not reasons:
        reasons = ["影像测量未触发高危阈值，但仍需结合生化、遗传和病理信息完成 PPGL 风险评估。"]
    return {
        "schema_version": "ppgl_imaging_risk_v1",
        "overall_level": overall_level,
        "imaging_followup_risk_level": imaging_level,
        "surgical_complexity_level": surgical_level,
        "segmentation_confidence": segmentation_quality.get("confidence"),
        "reasons": reasons,
        "risk_factors": factors,
        "protective_factors": protective,
        "nearest_structures": nearest_organs[:8],
        "missing_required_clinical_data": list(MISSING_CLINICAL_DATA_FOR_PPGL_RISK),
        "limitations": [
            "该风险分层基于自动分割和 CT 影像指标，不等同于病理诊断或转移风险最终判断。",
            "PPGL 风险需要结合生化、遗传、病理和既往病史；缺少这些信息时只能给出影像辅助风险。",
        ],
    }


def build_llm_context(
    args: argparse.Namespace,
    tumor_burden: dict[str, Any],
    origin: dict[str, Any],
    risk: dict[str, Any],
    segmentation_quality: dict[str, Any],
    nearest_organs: list[dict[str, Any]],
    ct_stats: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "ppgl_llm_context_v1",
        "case_id": args.case_id,
        "purpose": "Generate a clinician-facing PPGL imaging analysis report from structured segmentation metrics.",
        "tumor_burden": tumor_burden,
        "origin_assessment": origin,
        "risk_assessment": risk,
        "segmentation_quality": segmentation_quality,
        "nearest_anatomic_structures": nearest_organs[:10],
        "ct_intensity_descriptive_stats": ct_stats,
        "report_guidance": [
            "Use cautious language: suspected, imaging-based, automated segmentation.",
            "Do not claim definitive diagnosis, malignancy, metastasis, or treatment plan from segmentation alone.",
            "Explicitly list missing clinical, biochemical, genetic, and pathological data before final PPGL risk stratification.",
            "Explain risk reasons using measured distances, size, multifocality, and segmentation quality.",
        ],
    }


def analyze_case(
    args: argparse.Namespace,
    case_dir: Path,
    total_dir: Path,
    gcp_path: Path,
    apr_path: Path,
    final_path: Path,
    apr_summary: dict[str, Any],
    log_path: Path,
) -> None:
    analysis_dir = ensure_dir(case_dir / "analysis")
    metrics_path = analysis_dir / "clinical_metrics.json"
    llm_context_path = analysis_dir / "llm_context.json"
    report_path = analysis_dir / "report.md"

    tumor_label, tumor_img = load_label(apr_path, dtype=np.uint8)
    raw_label, _ = load_label(gcp_path, dtype=np.uint8)
    tumor = tumor_label == int(args.gcp_tumor_label)
    raw_tumor = raw_label == int(args.gcp_tumor_label)
    spacing = spacing_mm(tumor_img)
    voxel_volume = float(np.prod(np.asarray(spacing, dtype=np.float64)))

    _labels, comps = connected_components(tumor)
    component_payload = []
    for comp in comps:
        centroid = np.asarray(comp["centroid_voxel"], dtype=np.float64)
        bbox_min = np.asarray(comp["bbox_min_voxel"], dtype=np.float64)
        bbox_max = np.asarray(comp["bbox_max_voxel"], dtype=np.float64)
        component_payload.append(
            {
                **comp,
                "volume_mm3": float(int(comp["voxel_count"]) * voxel_volume),
                "centroid_mm_from_origin": [float(x) for x in (tumor_img.affine @ np.r_[centroid, 1.0])[:3]],
                "bbox_size_mm": [float(x) for x in ((bbox_max - bbox_min + 1.0) * np.asarray(spacing))],
            }
        )

    tumor_volume_mm3 = float(tumor.sum() * voxel_volume)
    raw_tumor_volume_mm3 = float(raw_tumor.sum() * voxel_volume)
    max_diameter_mm = None
    if component_payload:
        max_diameter_mm = max(float(max(row.get("bbox_size_mm", [0.0]))) for row in component_payload)
    equivalent_diameter_mm = None
    if tumor_volume_mm3 > 0:
        equivalent_diameter_mm = float((6.0 * tumor_volume_mm3 / math.pi) ** (1.0 / 3.0))
    largest_component_fraction = None
    if component_payload and int(tumor.sum()) > 0:
        largest_component_fraction = float(component_payload[0]["voxel_count"] / int(tumor.sum()))

    tumor_burden = {
        "apr_tumor_voxels": int(tumor.sum()),
        "apr_tumor_volume_mm3": json_number(tumor_volume_mm3, 3),
        "apr_tumor_volume_ml": json_number(tumor_volume_mm3 / 1000.0, 3),
        "raw_tumor_voxels": int(raw_tumor.sum()),
        "raw_tumor_volume_mm3": json_number(raw_tumor_volume_mm3, 3),
        "raw_tumor_volume_ml": json_number(raw_tumor_volume_mm3 / 1000.0, 3),
        "max_diameter_mm": json_number(max_diameter_mm, 3),
        "equivalent_sphere_diameter_mm": json_number(equivalent_diameter_mm, 3),
        "component_count": int(len(comps)),
        "largest_component_fraction": json_number(largest_component_fraction, 4),
        "multifocal_after_apr": bool(len(comps) > 1),
    }

    organ_relations, nearest_organs = organ_relation_metrics(total_dir, tumor, tumor_img, spacing, voxel_volume)

    analysis_anchor_names = FAST_ANALYSIS_ANCHORS if bool(args.analysis_fast) else FULL_ANALYSIS_ANCHORS
    anchor_distances: dict[str, float] = {
        name: float(organ_relations[name]["min_surface_distance_mm"])
        for name in analysis_anchor_names
        if name in organ_relations and organ_relations[name].get("min_surface_distance_mm") is not None
    }

    left_d = anchor_distances.get("kidney_left", float("nan"))
    right_d = anchor_distances.get("kidney_right", float("nan"))
    side = "uncertain"
    if np.isfinite(left_d) and np.isfinite(right_d):
        side = "left" if left_d < right_d else "right"
    elif np.isfinite(left_d):
        side = "left"
    elif np.isfinite(right_d):
        side = "right"

    origin_assessment = assess_origin(organ_relations, side)
    segmentation_quality = assess_segmentation_quality(int(raw_tumor.sum()), int(tumor.sum()), apr_summary)
    ct_stats = ct_intensity_stats(Path(args.image), tumor, tumor_img)
    risk_assessment = assess_risk(
        tumor_burden,
        origin_assessment,
        organ_relations,
        nearest_organs,
        segmentation_quality,
    )
    llm_context = build_llm_context(
        args,
        tumor_burden,
        origin_assessment,
        risk_assessment,
        segmentation_quality,
        nearest_organs,
        ct_stats,
    )

    metrics = {
        "case_id": args.case_id,
        "mode": args.mode,
        "analysis_fast": bool(args.analysis_fast),
        "analysis_anchor_names": list(analysis_anchor_names),
        "image": str(args.image),
        "spacing_mm": list(spacing),
        "tumor_burden": tumor_burden,
        "raw_tumor_voxels": int(raw_tumor.sum()),
        "raw_tumor_volume_mm3": raw_tumor_volume_mm3,
        "apr_tumor_voxels": int(tumor.sum()),
        "apr_tumor_volume_mm3": tumor_volume_mm3,
        "apr_tumor_volume_ml": float(tumor_volume_mm3 / 1000.0),
        "tumor_component_count": int(len(comps)),
        "tumor_side_by_nearest_kidney": side,
        "origin_assessment": origin_assessment,
        "anchor_distances_mm": anchor_distances,
        "nearest_anatomic_structures": nearest_organs[:10],
        "organ_relations": organ_relations,
        "ct_intensity": ct_stats,
        "segmentation_quality": segmentation_quality,
        "risk_assessment": risk_assessment,
        "components": component_payload,
        "apr_summary": apr_summary,
        "outputs": {
            "gcpv5_raw": str(gcp_path),
            "tumor_apr": str(apr_path),
            "final_seg": str(final_path),
            "totalseg_dir": str(total_dir),
            "llm_context": str(llm_context_path),
            "report": str(report_path),
        },
    }
    write_json(metrics_path, metrics)
    write_json(llm_context_path, llm_context)

    lines = [
        f"# Case {args.case_id}",
        "",
        f"- Mode: `{args.mode}`",
        f"- Final fused label: `{final_path}`",
        f"- Overall imaging-assisted risk level: `{risk_assessment['overall_level']}`",
        f"- PPGL imaging follow-up risk level: `{risk_assessment['imaging_followup_risk_level']}`",
        f"- Surgical/anatomic complexity level: `{risk_assessment['surgical_complexity_level']}`",
        f"- Segmentation confidence: `{risk_assessment['segmentation_confidence']}`",
        f"- APR tumor volume: `{metrics['apr_tumor_volume_ml']:.3f} ml`",
        f"- Max diameter: `{tumor_burden['max_diameter_mm']} mm`",
        f"- Tumor components: `{metrics['tumor_component_count']}`",
        f"- Side by nearest kidney: `{side}`",
        f"- Suspected origin: `{origin_assessment['suspected_origin']}` ({origin_assessment['confidence']})",
        f"- Raw tumor voxels: `{metrics['raw_tumor_voxels']}`",
        f"- APR tumor voxels: `{metrics['apr_tumor_voxels']}`",
        f"- APR removed voxels: `{apr_summary.get('removed_voxel_count', 0)}`",
        "",
        "## Risk Reasons",
    ]
    for reason in risk_assessment["reasons"]:
        lines.append(f"- {reason}")

    lines.extend(["", "## Nearest Anatomy"])
    for item in nearest_organs[:8]:
        lines.append(
            f"- {item['name']} ({item['group']}): {item['min_surface_distance_mm']} mm, {item['distance_category']}"
        )

    lines.extend([
        "",
        "## Segmentation Quality",
        f"- Confidence: `{segmentation_quality['confidence']}`",
        f"- APR removed ratio: `{segmentation_quality['removed_ratio']}`",
    ])
    for flag in segmentation_quality["flags"]:
        lines.append(f"- {flag}")

    lines.extend([
        "",
        "## Missing Clinical Data For Complete PPGL Risk Stratification",
    ])
    for item in risk_assessment["missing_required_clinical_data"]:
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Anchor Distances",
    ]
    )
    for name, distance in sorted(anchor_distances.items()):
        text = "nan" if not np.isfinite(float(distance)) else f"{float(distance):.2f} mm"
        lines.append(f"- {name}: {text}")
    lines.extend(
        [
            "",
            "## Notes",
            "- This report is generated locally from segmentation masks and is not a diagnosis.",
            "- Risk levels are imaging-based support signals and require clinical, biochemical, genetic, and pathological correlation.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    append_log(log_path, f"Analysis saved: {metrics_path}")


def prepare_case_dir(args: argparse.Namespace) -> tuple[Path, Path]:
    run_name = args.run_name.strip() if args.run_name.strip() else f"{now_token()}__{args.case_id}__{args.mode}"
    case_dir = ensure_dir(Path(args.output_root) / run_name)
    logs_dir = ensure_dir(case_dir / "logs")
    log_path = logs_dir / "pipeline.log"
    input_dir = ensure_dir(case_dir / "input")
    image_link = input_dir / Path(args.image).name
    if not image_link.exists():
        try:
            image_link.symlink_to(Path(args.image))
        except OSError:
            shutil.copy2(Path(args.image), image_link)
    write_json(
        case_dir / "run_config.json",
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "argv": sys.argv,
            "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
            "case_dir": str(case_dir),
        },
    )
    return case_dir, log_path


def validate_args(args: argparse.Namespace) -> None:
    args.image = Path(args.image).expanduser().resolve()
    args.output_root = Path(args.output_root).expanduser().resolve()
    args.package_dir = Path(args.package_dir).expanduser().resolve()
    args.raw_gcp_dir = Path(args.raw_gcp_dir).expanduser().resolve()
    args.totalseg_root = Path(args.totalseg_root).expanduser().resolve()
    if str(args.totalseg_existing_dir).strip():
        args.totalseg_existing_dir = str(Path(args.totalseg_existing_dir).expanduser().resolve())
    if str(args.reuse_gcp_path).strip():
        args.reuse_gcp_path = str(Path(args.reuse_gcp_path).expanduser().resolve())
    args.gcp_checkpoint = Path(args.gcp_checkpoint).expanduser().resolve()
    if not args.case_id:
        args.case_id = normalize_case_id(args.image)
    for path, name in [
        (args.image, "image"),
        (args.package_dir, "package-dir"),
        (args.raw_gcp_dir, "raw-gcp-dir"),
        (args.totalseg_root, "totalseg-root"),
        (args.gcp_checkpoint, "gcp-checkpoint"),
    ]:
        if not Path(path).exists():
            raise FileNotFoundError(f"{name} not found: {path}")
    if str(args.reuse_gcp_path).strip() and not Path(args.reuse_gcp_path).exists():
        raise FileNotFoundError(f"reuse-gcp-path not found: {args.reuse_gcp_path}")
    if shutil.which("TotalSegmentator") is None:
        raise FileNotFoundError("TotalSegmentator command not found. Activate ppgl-gpu38 first.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified PPGL case pipeline for Jetson deployment.")
    parser.add_argument("--case-id", default="")
    parser.add_argument("--image", default=str(DEFAULT_IMAGE))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--run-name", default="")
    parser.add_argument("--mode", choices=["jetson_fast", "abdomen", "full_total"], default="jetson_fast")
    parser.add_argument("--force", action="store_true")

    parser.add_argument("--package-dir", default=str(DEFAULT_PACKAGE_DIR))
    parser.add_argument("--raw-gcp-dir", default=str(DEFAULT_RAW_GCP_DIR))
    parser.add_argument("--totalseg-root", default=str(DEFAULT_TOTALSEG_ROOT))
    parser.add_argument("--totalseg-existing-dir", default="")
    parser.add_argument("--gcp-checkpoint", default=str(DEFAULT_CHECKPOINT))
    parser.add_argument("--reuse-gcp-path", default="")

    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--totalseg-device", default="gpu:0")
    parser.add_argument("--seed", type=int, default=1123)

    parser.add_argument("--gcp-num-classes", type=int, default=11)
    parser.add_argument("--gcp-tumor-label", type=int, default=GCP_TUMOR_LABEL)
    parser.add_argument("--gcp-backend", choices=["torch", "trt"], default="torch")
    parser.add_argument("--gcp-engine", default="")
    parser.add_argument("--gcp-roi-size", type=int, default=160)
    parser.add_argument("--gcp-sw-batch-size", type=int, default=1)
    parser.add_argument("--gcp-overlap", type=float, default=0.0)
    parser.add_argument("--gcp-fg-margin", type=int, default=10)
    parser.add_argument("--gcp-stitch-device", default="cpu", choices=["cpu", "cuda", "cuda:0"])
    parser.add_argument("--no-gcp-auto-lowmem", action="store_true")
    parser.add_argument("--gcp-local-roi", dest="gcp_local_roi", action="store_true", default=None)
    parser.add_argument("--no-gcp-local-roi", dest="gcp_local_roi", action="store_false")
    parser.add_argument("--gcp-local-roi-rois", default=",".join(FULL_ANALYSIS_ANCHORS))
    parser.add_argument("--gcp-local-roi-margin-mm", type=float, default=80.0)
    parser.add_argument("--gcp-local-roi-fallback-min-voxels", type=int, default=1)
    parser.add_argument("--gcp-amp", dest="gcp_amp", action="store_true", default=True)
    parser.add_argument("--no-gcp-amp", dest="gcp_amp", action="store_false")
    parser.add_argument("--allow-tf32", dest="allow_tf32", action="store_true", default=True)
    parser.add_argument("--no-allow-tf32", dest="allow_tf32", action="store_false")
    parser.add_argument("--no-cudnn-benchmark", action="store_true")
    parser.add_argument("--no-progress", action="store_true")

    parser.add_argument("--totalseg-fast", action="store_true")
    parser.add_argument("--totalseg-fastest", action="store_true")
    parser.add_argument("--totalseg-quiet", action="store_true")
    parser.add_argument("--totalseg-robust-crop", action="store_true")

    parser.add_argument("--apr-anchor-rois", default=",".join(DEFAULT_APR_ANCHOR_ROIS))
    parser.add_argument("--apr-tau", type=float, default=0.50)
    parser.add_argument("--apr-min-component-voxels", type=int, default=0)
    parser.add_argument("--apr-good-distance-mm", type=float, default=8.0)
    parser.add_argument("--apr-bad-distance-mm", type=float, default=80.0)
    parser.add_argument("--apr-volume-ref-mm3", type=float, default=2222.0)
    parser.add_argument("--apr-weight-anatomy", type=float, default=0.75)
    parser.add_argument("--apr-weight-geometry", type=float, default=0.25)
    parser.add_argument("--analysis-fast", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)
    case_dir, log_path = prepare_case_dir(args)
    timings: dict[str, float] = {}
    pipeline_start = time.perf_counter()

    append_log(log_path, f"Case directory: {case_dir}")
    append_log(log_path, f"Python: {sys.executable}")
    append_log(log_path, f"Torch: {torch.__version__}, cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        torch.backends.cudnn.benchmark = not bool(args.no_cudnn_benchmark)
        if hasattr(torch.backends, "cuda") and hasattr(torch.backends.cuda, "matmul"):
            torch.backends.cuda.matmul.allow_tf32 = bool(args.allow_tf32)
        append_log(
            log_path,
            "CUDA performance settings: "
            f"cudnn_benchmark={torch.backends.cudnn.benchmark}, "
            f"allow_tf32={bool(args.allow_tf32)}, gcp_amp={bool(args.gcp_amp)}, "
            f"gcp_stitch_device={args.gcp_stitch_device}, "
            f"gcp_auto_lowmem={not bool(args.no_gcp_auto_lowmem)}",
        )

    total_dir: Path | None = None
    if should_use_gcp_local_roi(args):
        append_log(log_path, "GCPV5 local ROI mode is active; running TotalSegmentator before GCPV5.")
        with timed_stage(log_path, timings, "totalseg", "1/5 TotalSegmentator anatomy"):
            total_dir = run_totalseg(args, case_dir, log_path)
        with timed_stage(log_path, timings, "gcpv5", "2/5 GCPV5 tumor inference"):
            gcp_path = run_gcpv5(args, case_dir, log_path, total_dir)
    else:
        with timed_stage(log_path, timings, "gcpv5", "1/5 GCPV5 tumor inference"):
            gcp_path = run_gcpv5(args, case_dir, log_path)
        with timed_stage(log_path, timings, "totalseg", "2/5 TotalSegmentator anatomy"):
            total_dir = run_totalseg(args, case_dir, log_path)
    if total_dir is None:
        raise RuntimeError("TotalSegmentator stage did not produce a mask directory.")
    with timed_stage(log_path, timings, "apr", "3/5 APR filtering"):
        tumor_apr_path, apr_summary = run_apr(args, case_dir, gcp_path, total_dir, log_path)
    with timed_stage(log_path, timings, "fusion", "4/5 Tumor-priority fusion"):
        final_path, _label_map = compose_final_label(args, case_dir, total_dir, tumor_apr_path, log_path)
    with timed_stage(log_path, timings, "analysis", "5/5 Clinical metrics"):
        analyze_case(args, case_dir, total_dir, gcp_path, tumor_apr_path, final_path, apr_summary, log_path)

    timings["total"] = time.perf_counter() - pipeline_start
    timing_path = case_dir / "timing.json"
    write_json(
        timing_path,
        {
            "case_id": args.case_id,
            "timings_seconds": {key: round(value, 3) for key, value in timings.items()},
            "timings_human": {key: format_elapsed(value) for key, value in timings.items()},
        },
    )
    append_log(log_path, f"Timing saved: {timing_path}")

    print(f"Pipeline finished: {case_dir}")
    print(f"Final label: {case_dir / 'fusion' / (args.case_id + '_final_seg.nii.gz')}")
    print(f"Report: {case_dir / 'analysis' / 'report.md'}")
    print(f"Timing: {timing_path}")


if __name__ == "__main__":
    main()
