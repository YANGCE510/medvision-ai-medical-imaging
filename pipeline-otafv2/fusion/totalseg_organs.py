from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from fusion.otafv2_config import LABEL_IDS


VERTEBRAE_ROIS = (
    "vertebrae_S1",
    "vertebrae_L5",
    "vertebrae_L4",
    "vertebrae_L3",
    "vertebrae_L2",
    "vertebrae_L1",
    "vertebrae_T12",
    "vertebrae_T11",
    "vertebrae_T10",
    "vertebrae_T9",
    "vertebrae_T8",
    "vertebrae_T7",
    "vertebrae_T6",
    "vertebrae_T5",
    "vertebrae_T4",
    "vertebrae_T3",
    "vertebrae_T2",
    "vertebrae_T1",
    "vertebrae_C7",
    "vertebrae_C6",
    "vertebrae_C5",
    "vertebrae_C4",
    "vertebrae_C3",
    "vertebrae_C2",
    "vertebrae_C1",
)

BASE_TOTALSEG_ROIS = (
    "aorta",
    "inferior_vena_cava",
    "kidney_left",
    "kidney_right",
    "adrenal_gland_left",
    "adrenal_gland_right",
    "iliopsoas_left",
    "iliopsoas_right",
)

TOTAL_TO_OTAFV2_NAMES = {
    "aorta": "aorta",
    "inferior_vena_cava": "ivc",
    "kidney_left": "left_kidney",
    "kidney_right": "right_kidney",
    "adrenal_gland_left": "left_adrenal",
    "adrenal_gland_right": "right_adrenal",
    "iliopsoas_left": "left_psoas",
    "iliopsoas_right": "right_psoas",
}


def default_totalseg_rois(_task: str = "total") -> list[str]:
    return list(BASE_TOTALSEG_ROIS + VERTEBRAE_ROIS)


def normalize_totalseg_device(device: str) -> str:
    value = str(device or "").strip()
    if not value:
        return "gpu"
    if value == "cuda":
        return "gpu"
    if value.startswith("cuda:"):
        return "gpu:" + value.split(":", 1)[1]
    return value


def _add_totalseg_root(totalseg_root: str | Path) -> None:
    root_text = str(totalseg_root or "").strip()
    if not root_text:
        return
    root = Path(root_text).expanduser()
    if not root.is_absolute():
        root = (PROJECT_DIR / root).resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _load_totalseg_class_map(task: str, totalseg_root: str | Path) -> dict[int, str]:
    _add_totalseg_root(totalseg_root)
    from totalsegmentator.map_to_binary import class_map

    if task not in class_map:
        raise ValueError(f"TotalSegmentator class map does not contain task={task!r}.")
    return {int(k): str(v) for k, v in class_map[task].items()}


def convert_totalseg_to_otafv2(
    total_label: np.ndarray,
    task: str = "total",
    totalseg_root: str | Path = "",
) -> np.ndarray:
    class_map = _load_totalseg_class_map(task, totalseg_root)
    name_to_id = {name: label_id for label_id, name in class_map.items()}
    total_arr = np.asarray(total_label)
    out = np.zeros(total_arr.shape, dtype=np.uint8)

    for total_name, otafv2_name in TOTAL_TO_OTAFV2_NAMES.items():
        total_id = name_to_id.get(total_name)
        if total_id is not None:
            out[total_arr == int(total_id)] = int(LABEL_IDS[otafv2_name])

    vertebrae_ids = [
        int(label_id)
        for label_id, name in class_map.items()
        if name == "vertebrae" or name.startswith("vertebrae_")
    ]
    if vertebrae_ids:
        out[np.isin(total_arr, vertebrae_ids)] = int(LABEL_IDS["vertebrae"])

    return out


def convert_totalseg_image_to_otafv2(
    total_img: nib.Nifti1Image,
    task: str = "total",
    totalseg_root: str | Path = "",
) -> nib.Nifti1Image:
    out = convert_totalseg_to_otafv2(np.asanyarray(total_img.dataobj), task=task, totalseg_root=totalseg_root)
    header = total_img.header.copy()
    header.set_data_dtype(np.uint8)
    return nib.Nifti1Image(out, total_img.affine, header)


def _label_counts(label: np.ndarray) -> dict[str, int]:
    arr = np.asarray(label)
    return {
        name: int((arr == int(label_id)).sum())
        for name, label_id in LABEL_IDS.items()
        if name != "background"
    }


def generate_otafv2_organs_from_totalseg(
    image_path: str | Path,
    output_path: str | Path,
    *,
    totalseg_root: str | Path = "",
    task: str = "total",
    device: str = "gpu",
    fast: bool = False,
    fastest: bool = False,
    roi_subset: list[str] | None = None,
    nr_thr_resamp: int = 1,
    nr_thr_saving: int = 1,
    quiet: bool = True,
    test: int = 0,
    remove_small_blobs_mm3: float = 0.0,
    raw_output_path: str | Path | None = None,
) -> dict[str, Any]:
    _add_totalseg_root(totalseg_root)
    from totalsegmentator.python_api import totalsegmentator

    image_path = Path(image_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rois = list(roi_subset) if roi_subset else None
    remove_small_blobs: bool | float = False
    if float(remove_small_blobs_mm3) > 0:
        remove_small_blobs = float(remove_small_blobs_mm3)

    seg_img = totalsegmentator(
        image_path,
        output=None,
        ml=True,
        nr_thr_resamp=int(nr_thr_resamp),
        nr_thr_saving=int(nr_thr_saving),
        fast=bool(fast),
        fastest=bool(fastest),
        task=str(task),
        roi_subset=rois,
        quiet=bool(quiet),
        test=int(test),
        skip_saving=True,
        device=normalize_totalseg_device(device),
        remove_small_blobs=remove_small_blobs,
    )

    if raw_output_path is not None and str(raw_output_path).strip():
        raw_path = Path(raw_output_path)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        nib.save(seg_img, raw_path)

    out_img = convert_totalseg_image_to_otafv2(seg_img, task=task, totalseg_root=totalseg_root)
    nib.save(out_img, output_path)
    out_label = np.asanyarray(out_img.dataobj)
    return {
        "image_path": str(image_path),
        "output_path": str(output_path),
        "raw_output_path": str(raw_output_path or ""),
        "task": str(task),
        "device": normalize_totalseg_device(device),
        "fast": bool(fast),
        "fastest": bool(fastest),
        "roi_subset": rois or [],
        "label_counts": _label_counts(out_label),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OTAFV2 anatomy labels with TotalSegmentator.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--totalseg-root", default="")
    parser.add_argument("--task", default="total")
    parser.add_argument("--device", default="gpu")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--fastest", action="store_true")
    parser.add_argument("--roi-subset", nargs="*", default=None)
    parser.add_argument("--nr-thr-resamp", type=int, default=1)
    parser.add_argument("--nr-thr-saving", type=int, default=1)
    parser.add_argument("--remove-small-blobs-mm3", type=float, default=0.0)
    parser.add_argument("--raw-output", default="")
    parser.add_argument("--stats-json", default="")
    parser.add_argument("--test", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    stats = generate_otafv2_organs_from_totalseg(
        args.image,
        args.output,
        totalseg_root=args.totalseg_root,
        task=args.task,
        device=args.device,
        fast=args.fast,
        fastest=args.fastest,
        roi_subset=args.roi_subset,
        nr_thr_resamp=args.nr_thr_resamp,
        nr_thr_saving=args.nr_thr_saving,
        quiet=args.quiet,
        test=args.test,
        remove_small_blobs_mm3=args.remove_small_blobs_mm3,
        raw_output_path=args.raw_output or None,
    )
    if args.stats_json:
        stats_path = Path(args.stats_json)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        with stats_path.open("w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
