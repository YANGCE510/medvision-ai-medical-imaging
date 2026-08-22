from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - tqdm is expected in the ppgl env.
    def tqdm(iterable, **_kwargs):
        return iterable

from fusion.otafv2_apr import apply_apr_to_tumor
from fusion.otafv2_config import (
    LABEL_IDS,
    PROJECT_DIR,
    SIDE_TO_ADRENAL_LABEL,
    SIDES,
    OTAFV2Config,
    gt_adrenal_label_id,
    load_case_ids,
    load_config,
    resolve_path,
)
from fusion.otafv2_roi_proposal import proposal_from_sources
from fusion.totalseg_organs import normalize_totalseg_device
from fusion.otafv2_utils import (
    backproject_roi_mask,
    binary_metrics,
    clean_specialist_mask,
    compute_surface_metrics_np,
    connected_components_3d,
    crop_with_padding,
    ensure_dir,
    load_image,
    load_label,
    prefix_metrics,
    save_image,
    save_label,
    translate_affine,
    write_csv,
    write_json,
)


ORGAN_TUNE_LABELS = {
    LABEL_IDS["aorta"],
    LABEL_IDS["left_kidney"],
    LABEL_IDS["right_kidney"],
    LABEL_IDS["ivc"],
    LABEL_IDS["left_psoas"],
    LABEL_IDS["right_psoas"],
    LABEL_IDS["vertebrae"],
}
FORBIDDEN_ORGAN_TUNE_LABELS = {
    LABEL_IDS["left_adrenal"],
    LABEL_IDS["right_adrenal"],
    LABEL_IDS["tumor"],
}
EVAL_CLASS_NAMES = (
    "aorta",
    "left_kidney",
    "right_kidney",
    "ivc",
    "left_adrenal",
    "right_adrenal",
    "left_psoas",
    "right_psoas",
    "vertebrae",
    "tumor",
)


def _prepend_env_paths(env: dict[str, str], name: str, paths: list[Path]) -> None:
    existing = [part for part in env.get(name, "").split(os.pathsep) if part]
    additions = [str(path) for path in paths if path.exists()]
    merged: list[str] = []
    for part in additions + existing:
        if part not in merged:
            merged.append(part)
    if merged:
        env[name] = os.pathsep.join(merged)


def _runtime_env(python_exe: str = "", conda_env: str = "") -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    lib_paths: list[Path] = []

    if str(python_exe).strip():
        python_path = Path(str(python_exe)).expanduser()
        if python_path.name.startswith("python") and python_path.parent.name == "bin":
            lib_paths.append(python_path.parent.parent / "lib")

    if str(conda_env).strip():
        lib_paths.append(Path.home() / "anaconda3" / "envs" / str(conda_env) / "lib")

    lib_paths.append(Path("/usr/local/cuda-11.4/lib64"))
    _prepend_env_paths(env, "LD_LIBRARY_PATH", lib_paths)
    return env


def _resolve_executable(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return sys.executable
    path = Path(text).expanduser()
    if path.is_absolute() or len(path.parts) > 1:
        return str(path if path.is_absolute() else (PROJECT_DIR / path).resolve())
    return text


def _anatomy_source_display(cfg: OTAFV2Config) -> str:
    if cfg.anatomy_source == "totalsegmentator_organs":
        return "TotalSegmentator anatomy"
    return "GCPV5-1 organ-tune anatomy"


def _uses_specialist_adrenals(cfg: OTAFV2Config) -> bool:
    return str(cfg.adrenal_source) == "specialist"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _stage(message: str) -> None:
    print(f"\n[OTAFV2] {message}", flush=True)


def _case_image_path(cfg: OTAFV2Config, case_id: str) -> Path:
    image_dir = resolve_path(cfg.image_dir, PROJECT_DIR)
    candidates = [
        image_dir / f"{case_id}.nii.gz",
        image_dir / f"{case_id}_0000.nii.gz",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Image not found for case {case_id}: tried {candidates}")


def _case_label_path(cfg: OTAFV2Config, case_id: str) -> Path | None:
    if not str(cfg.label_dir).strip():
        return None
    label_dir = resolve_path(cfg.label_dir, PROJECT_DIR)
    candidates = [
        label_dir / f"{case_id}.nii.gz",
        label_dir / f"{case_id}_0000.nii.gz",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _old_gcp_path(cfg: OTAFV2Config, case_id: str) -> Path:
    path = _old_gcp_path_no_raise(cfg, case_id)
    if not path.exists():
        raise FileNotFoundError(f"Old GCPV5 prediction missing for {case_id}: {path}")
    return path


def _old_gcp_path_no_raise(cfg: OTAFV2Config, case_id: str) -> Path:
    old_dir = resolve_path(cfg.old_gcp_label_dir, PROJECT_DIR)
    return old_dir / f"{case_id}{cfg.old_gcp_suffix}"


def _missing_old_gcp_cases(cfg: OTAFV2Config, cases: list[str]) -> list[str]:
    return [case_id for case_id in cases if not _old_gcp_path_no_raise(cfg, case_id).exists()]


def _run_old_gcp_generation(cfg: OTAFV2Config, cases: list[str], force: bool = False) -> None:
    missing_before = _missing_old_gcp_cases(cfg, cases)
    if not force and not missing_before:
        _stage(f"Stage 0/4 old GCP labels already present: {len(cases)}/{len(cases)}; skipping old GCP inference.")
        return

    if force:
        _stage("Stage 0/4 running old GCP inference because --force-old-gcp was set.")
    else:
        _stage(
            f"Stage 0/4 missing old GCP labels: {len(missing_before)}/{len(cases)}; "
            "running configured old GCP inference."
        )

    gcp_root = resolve_path(cfg.old_gcp_root, PROJECT_DIR)
    python_exe = str(resolve_path(cfg.old_gcp_python, PROJECT_DIR)) if str(cfg.old_gcp_python).strip() else sys.executable
    script_path = gcp_root / "test_v4.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Old GCP test script missing: {script_path}")
    if not resolve_path(cfg.old_gcp_checkpoint, PROJECT_DIR).exists():
        raise FileNotFoundError(f"Old GCP checkpoint missing: {cfg.old_gcp_checkpoint}")

    cmd = [
        python_exe,
        str(script_path),
        "--center",
        str(cfg.old_gcp_center),
        "--split",
        str(cfg.old_gcp_split),
        "--exp-name",
        str(cfg.old_gcp_exp_name),
        "--data-root",
        str(resolve_path(cfg.old_gcp_data_root, PROJECT_DIR)),
        "--data-list-root",
        str(resolve_path(cfg.old_gcp_data_list_root, PROJECT_DIR)),
        "--image-folder",
        str(cfg.old_gcp_image_folder),
        "--label-folder",
        str(cfg.old_gcp_label_folder),
        "--checkpoint",
        str(resolve_path(cfg.old_gcp_checkpoint, PROJECT_DIR)),
        "--num-classes",
        str(int(cfg.old_gcp_num_classes)),
        "--tumor-label",
        str(int(cfg.old_gcp_tumor_label)),
        "--roi-size",
        str(int(cfg.old_gcp_roi_size)),
        "--sw-batch-size",
        str(int(cfg.old_gcp_sw_batch_size)),
        "--overlap",
        str(float(cfg.old_gcp_overlap)),
        "--fg-margin",
        str(int(cfg.old_gcp_fg_margin)),
        "--cache-rate",
        str(float(cfg.old_gcp_cache_rate)),
        "--num-workers",
        str(int(cfg.old_gcp_num_workers)),
        "--device",
        str(cfg.old_gcp_device),
        "--output-root",
        str(resolve_path(cfg.old_gcp_output_root, PROJECT_DIR)),
        "--run-name",
        str(cfg.old_gcp_run_name),
        "--tag",
        str(cfg.old_gcp_tag),
        "--save-nifti-labels",
        "--nifti-postfix",
        str(cfg.old_gcp_nifti_postfix),
    ]
    env = _runtime_env(python_exe=python_exe)
    if str(cfg.old_gcp_pytorch_cuda_alloc_conf).strip():
        env["PYTORCH_CUDA_ALLOC_CONF"] = str(cfg.old_gcp_pytorch_cuda_alloc_conf)
    subprocess.run(cmd, cwd=str(gcp_root), env=env, check=True)

    missing_after = _missing_old_gcp_cases(cfg, cases)
    if missing_after:
        raise FileNotFoundError(
            f"Old GCP inference finished but {len(missing_after)} labels are still missing. "
            f"First missing case: {missing_after[0]}"
        )


def _organ_tune_path(cfg: OTAFV2Config, case_id: str) -> Path:
    organ_dir = resolve_path(cfg.organ_tune_label_dir, PROJECT_DIR)
    path = organ_dir / f"{case_id}{cfg.organ_tune_suffix}"
    if not path.exists():
        raise FileNotFoundError(f"{_anatomy_source_display(cfg)} prediction missing for {case_id}: {path}")
    return path


def _missing_organ_tune_cases(cfg: OTAFV2Config, cases: list[str]) -> list[str]:
    return [case_id for case_id in cases if not _organ_tune_path_no_raise(cfg, case_id).exists()]


def _organ_tune_path_no_raise(cfg: OTAFV2Config, case_id: str) -> Path:
    organ_dir = resolve_path(cfg.organ_tune_label_dir, PROJECT_DIR)
    return organ_dir / f"{case_id}{cfg.organ_tune_suffix}"


def _run_totalseg_organ_generation(cfg: OTAFV2Config, cases: list[str], force: bool = False) -> None:
    missing_before = _missing_organ_tune_cases(cfg, cases)
    if not force and not missing_before:
        _stage(f"Stage 1/4 TotalSegmentator anatomy labels already present: {len(cases)}/{len(cases)}; skipping.")
        return

    target_cases = list(cases) if force else list(missing_before)
    if force:
        _stage("Stage 1/4 running TotalSegmentator anatomy inference because --force-organ-tune was set.")
    else:
        _stage(
            f"Stage 1/4 missing TotalSegmentator anatomy labels: {len(missing_before)}/{len(cases)}; "
            "running TotalSegmentator."
        )

    python_exe = _resolve_executable(cfg.totalseg_python)
    script_path = PROJECT_DIR / "fusion" / "totalseg_organs.py"
    if not script_path.exists():
        raise FileNotFoundError(f"TotalSegmentator adapter missing: {script_path}")

    env = _runtime_env(python_exe=python_exe)
    python_paths = [PROJECT_DIR]
    if str(cfg.totalseg_root).strip():
        python_paths.append(resolve_path(cfg.totalseg_root, PROJECT_DIR))
    _prepend_env_paths(env, "PYTHONPATH", python_paths)

    roi_subset = list(cfg.totalseg_roi_subset) if cfg.totalseg_roi_subset else []
    label_dir = resolve_path(cfg.organ_tune_label_dir, PROJECT_DIR)
    label_dir.mkdir(parents=True, exist_ok=True)
    stats_dir = ensure_dir(resolve_path(cfg.organ_tune_output_root, PROJECT_DIR) / str(cfg.organ_tune_run_name) / "totalseg_stats")
    raw_dir = ensure_dir(resolve_path(cfg.organ_tune_output_root, PROJECT_DIR) / str(cfg.organ_tune_run_name) / "raw_totalseg")

    for case_id in tqdm(target_cases, desc="Stage 1/4 TotalSegmentator organs", unit="case", ncols=120):
        output_path = _organ_tune_path_no_raise(cfg, case_id)
        image_path = _case_image_path(cfg, case_id)
        cmd = [
            python_exe,
            str(script_path),
            "--image",
            str(image_path),
            "--output",
            str(output_path),
            "--totalseg-root",
            str(resolve_path(cfg.totalseg_root, PROJECT_DIR)) if str(cfg.totalseg_root).strip() else "",
            "--task",
            str(cfg.totalseg_task),
            "--device",
            normalize_totalseg_device(str(cfg.totalseg_device).strip() or str(cfg.organ_tune_device)),
            "--nr-thr-resamp",
            str(int(cfg.totalseg_nr_thr_resamp)),
            "--nr-thr-saving",
            str(int(cfg.totalseg_nr_thr_saving)),
            "--remove-small-blobs-mm3",
            str(float(cfg.totalseg_remove_small_blobs_mm3)),
            "--stats-json",
            str(stats_dir / f"{case_id}_totalseg_organs.json"),
        ]
        if roi_subset:
            cmd.extend(["--roi-subset", *roi_subset])
        if bool(cfg.totalseg_fast):
            cmd.append("--fast")
        if bool(cfg.totalseg_fastest):
            cmd.append("--fastest")
        if bool(cfg.totalseg_quiet):
            cmd.append("--quiet")
        if bool(cfg.totalseg_save_raw_total):
            cmd.extend(["--raw-output", str(raw_dir / f"{case_id}_totalseg_raw.nii.gz")])
        subprocess.run(cmd, cwd=str(PROJECT_DIR), env=env, check=True)

    missing_after = _missing_organ_tune_cases(cfg, cases)
    if missing_after:
        raise FileNotFoundError(
            f"TotalSegmentator anatomy inference finished but {len(missing_after)} labels are still missing. "
            f"First missing case: {missing_after[0]}"
        )


def _run_organ_tune_generation(cfg: OTAFV2Config, cases: list[str], force: bool = False) -> None:
    if cfg.anatomy_source == "totalsegmentator_organs":
        _run_totalseg_organ_generation(cfg, cases, force=force)
        return

    missing_before = _missing_organ_tune_cases(cfg, cases)
    if not force and not missing_before:
        _stage(f"Stage 1/4 organ-tune labels already present: {len(cases)}/{len(cases)}; skipping GCPV5-1 inference.")
        return

    if force:
        _stage("Stage 1/4 running GCPV5-1 organ-tune inference because --force-organ-tune was set.")
    else:
        _stage(
            f"Stage 1/4 missing GCPV5-1 organ-tune labels: {len(missing_before)}/{len(cases)}; "
            "running GCPV5-1 inference."
        )

    gcp_root = resolve_path(cfg.organ_tune_gcpv5_1_root, PROJECT_DIR)
    python_exe = str(resolve_path(cfg.organ_tune_python, PROJECT_DIR)) if str(cfg.organ_tune_python).strip() else sys.executable
    script_path = gcp_root / "test_v4.py"
    if not script_path.exists():
        raise FileNotFoundError(f"GCPV5-1 test script missing: {script_path}")
    if not resolve_path(cfg.organ_tune_checkpoint, PROJECT_DIR).exists():
        raise FileNotFoundError(f"GCPV5-1 organ-tune checkpoint missing: {cfg.organ_tune_checkpoint}")

    cmd = [
        python_exe,
        str(script_path),
        "--center",
        str(cfg.organ_tune_center),
        "--split",
        str(cfg.organ_tune_split),
        "--exp-name",
        str(cfg.organ_tune_exp_name),
        "--data-root",
        str(resolve_path(cfg.organ_tune_data_root, PROJECT_DIR)),
        "--data-list-root",
        str(resolve_path(cfg.organ_tune_data_list_root, PROJECT_DIR)),
        "--image-folder",
        str(cfg.organ_tune_image_folder),
        "--label-folder",
        str(cfg.organ_tune_label_folder),
        "--checkpoint",
        str(resolve_path(cfg.organ_tune_checkpoint, PROJECT_DIR)),
        "--num-classes",
        str(int(cfg.organ_tune_num_classes)),
        "--class-names",
        str(cfg.organ_tune_class_names),
        "--roi-size",
        str(int(cfg.organ_tune_roi_size)),
        "--sw-batch-size",
        str(int(cfg.organ_tune_sw_batch_size)),
        "--overlap",
        str(float(cfg.organ_tune_overlap)),
        "--cache-rate",
        str(float(cfg.organ_tune_cache_rate)),
        "--num-workers",
        str(int(cfg.organ_tune_num_workers)),
        "--device",
        str(cfg.organ_tune_device),
        "--sigmoid-multilabel",
        "--prob-threshold",
        str(float(cfg.organ_tune_prob_threshold)),
        "--output-root",
        str(resolve_path(cfg.organ_tune_output_root, PROJECT_DIR)),
        "--run-name",
        str(cfg.organ_tune_run_name),
        "--tag",
        str(cfg.organ_tune_tag),
        "--save-nifti-labels",
        "--nifti-postfix",
        str(cfg.organ_tune_nifti_postfix),
    ]
    if bool(cfg.organ_tune_export_only):
        cmd.append("--export-only")
    subprocess.run(cmd, cwd=str(gcp_root), env=_runtime_env(python_exe=python_exe), check=True)

    missing_after = _missing_organ_tune_cases(cfg, cases)
    if missing_after:
        raise FileNotFoundError(
            f"GCPV5-1 organ-tune inference finished but {len(missing_after)} labels are still missing. "
            f"First missing case: {missing_after[0]}"
        )


def _prepare_dirs(output_dir: Path) -> dict[str, Path]:
    return {
        "old_gcp": ensure_dir(output_dir / "old_gcp_labels"),
        "organ_tune": ensure_dir(output_dir / "gcpv5_1_organ_labels"),
        "roi_images": ensure_dir(output_dir / "roi_images"),
        "roi_predictions": ensure_dir(output_dir / "roi_predictions"),
        "specialist": ensure_dir(output_dir / "specialist_adrenal_labels"),
        "anatomy": ensure_dir(output_dir / "anatomy_for_apr_labels"),
        "apr_tumor": ensure_dir(output_dir / "apr_tumor_labels"),
        "final": ensure_dir(output_dir / "final_fused_labels"),
    }


def _cleanup_intermediate_dirs(output_dir: Path, dirs: dict[str, Path]) -> None:
    removable_keys = (
        "old_gcp",
        "organ_tune",
        "roi_images",
        "roi_predictions",
        "specialist",
        "anatomy",
        "apr_tumor",
    )
    for key in removable_keys:
        path = dirs.get(key, output_dir / key)
        if path.exists():
            shutil.rmtree(path)


def _write_run_config(output_dir: Path, cfg_path: Path, cfg: OTAFV2Config, args: argparse.Namespace) -> None:
    anatomy_method = (
        "TotalSegmentator anatomy"
        if cfg.anatomy_source == "totalsegmentator_organs"
        else "organ-tuned GCPV5-1 anatomy"
    )
    adrenal_method = "AdrenalSpecialistV5 adrenal fusion" if _uses_specialist_adrenals(cfg) else "anatomy-source adrenal labels"
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "config_path": str(cfg_path),
        "args": vars(args),
        "config": cfg.__dict__,
        "method": (
            f"OTAFV2: {anatomy_method}, old GCPV5 tumor candidate, "
            f"and {adrenal_method} with APR tumor refinement."
        ),
    }
    write_json(output_dir / "run_config.json", payload)


def _assert_same_grid(case_id: str, reference_img: nib.Nifti1Image, other_img: nib.Nifti1Image, name: str) -> None:
    if tuple(reference_img.shape[:3]) != tuple(other_img.shape[:3]):
        raise ValueError(f"{case_id}: {name} shape mismatch {other_img.shape[:3]} vs {reference_img.shape[:3]}")
    if not np.allclose(reference_img.affine, other_img.affine, atol=1e-4, rtol=1e-4):
        raise ValueError(f"{case_id}: {name} affine mismatch vs reference image")


def _spacing_mm(img: nib.Nifti1Image) -> tuple[float, float, float]:
    return tuple(float(x) for x in img.header.get_zooms()[:3])


def _gt_label_id_for_class(cfg: OTAFV2Config, class_name: str) -> int:
    if class_name in cfg.gt_label_map:
        return int(cfg.gt_label_map[class_name])
    if class_name == "left_adrenal":
        return int(cfg.gt_left_adrenal_label)
    if class_name == "right_adrenal":
        return int(cfg.gt_right_adrenal_label)
    if class_name == "tumor":
        return int(cfg.gt_tumor_label)
    return int(LABEL_IDS[class_name])


def prepare_rois(cfg: OTAFV2Config, cases: list[str], output_dir: Path, dirs: dict[str, Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    roi_size = tuple(int(x) for x in cfg.roi_size)
    for case_id in tqdm(cases, desc="Stage 2/4 prepare ROIs", unit="case", ncols=120):
        image_path = _case_image_path(cfg, case_id)
        old_path = _old_gcp_path(cfg, case_id)
        organ_path = _organ_tune_path(cfg, case_id)
        image_arr, image_img = load_image(image_path)
        old_label, old_img = load_label(old_path)
        organ_label, organ_img = load_label(organ_path)
        _assert_same_grid(case_id, image_img, old_img, "old_gcp_label")
        _assert_same_grid(case_id, image_img, organ_img, "organ_tune_label")
        if tuple(image_arr.shape[:3]) != tuple(old_label.shape):
            raise ValueError(f"{case_id}: image/old GCP shape mismatch {image_arr.shape[:3]} vs {old_label.shape}")
        if tuple(old_label.shape) != tuple(organ_label.shape):
            raise ValueError(f"{case_id}: old GCP/organ-tune shape mismatch {old_label.shape} vs {organ_label.shape}")

        old_out = dirs["old_gcp"] / f"{case_id}_old_gcpv5.nii.gz"
        organ_out = dirs["organ_tune"] / f"{case_id}_gcpv5_1_organs.nii.gz"
        if bool(cfg.save_intermediate_nii):
            save_label(old_out, old_label, old_img)
            save_label(organ_out, organ_label, organ_img)

        label_path = _case_label_path(cfg, case_id)
        for side in SIDES:
            sample_id = f"OTAFV2_{case_id}_{side}"
            proposal = proposal_from_sources(case_id, side, old_label, organ_label, cfg)
            base_row: dict[str, Any] = {
                "case_id": case_id,
                "side": side,
                "sample_id": sample_id,
                "anatomy_source": cfg.anatomy_source,
                "proposal_source": proposal.source,
                "proposal_reason": proposal.reason,
                "old_gcp_adrenal_voxels": proposal.old_gcp_adrenal_voxels,
                "old_gcp_adrenal_largest_component_voxels": proposal.old_gcp_adrenal_largest_component_voxels,
                "organ_tune_kidney_voxels": proposal.organ_tune_kidney_voxels,
                "midline_source": proposal.midline_source,
                "anatomy_center_x": proposal.anatomy_center_x,
                "anatomy_center_y": proposal.anatomy_center_y,
                "anatomy_center_z": proposal.anatomy_center_z,
                "old_gcp_path": str(old_path),
                "old_gcp_output_path": str(old_out) if bool(cfg.save_intermediate_nii) else "",
                "organ_tune_path": str(organ_path),
                "organ_tune_output_path": str(organ_out) if bool(cfg.save_intermediate_nii) else "",
                "source_image_path": str(image_path),
                "source_label_path": str(label_path or ""),
            }
            if not proposal.accepted:
                base_row["proposal_accepted"] = 0
                rows.append(base_row)
                continue

            crop, crop_meta = crop_with_padding(image_arr, proposal.center_xyz, roi_size, float(cfg.roi_pad_value))
            roi_affine = translate_affine(
                image_img.affine,
                (
                    int(crop_meta["crop_start_x"]),
                    int(crop_meta["crop_start_y"]),
                    int(crop_meta["crop_start_z"]),
                ),
            )
            roi_image_path = dirs["roi_images"] / f"{sample_id}_0000.nii.gz"
            save_image(roi_image_path, crop, roi_affine, image_img)
            base_row.update(
                {
                    "proposal_accepted": 1,
                    "center_x": proposal.center_xyz[0],
                    "center_y": proposal.center_xyz[1],
                    "center_z": proposal.center_xyz[2],
                    "source_shape": ",".join(str(int(x)) for x in old_label.shape),
                    "roi_shape": ",".join(str(int(x)) for x in roi_size),
                    "roi_image_path": str(roi_image_path),
                }
            )
            base_row.update(crop_meta)
            rows.append(base_row)

    manifest_path = output_dir / "otafv2_roi_manifest.csv"
    write_csv(manifest_path, rows)
    return rows


def run_specialist_prediction(cfg: OTAFV2Config, dirs: dict[str, Path]) -> None:
    _stage("Stage 3/4 running AdrenalSpecialistV5 ROI inference. nnU-Net will show per-ROI progress.")
    specialist_root = resolve_path(cfg.adrenal_specialist_root, PROJECT_DIR)
    env = _runtime_env(conda_env=str(cfg.conda_env))
    env["nnUNet_raw"] = str(specialist_root / "nnUNet_raw")
    env["nnUNet_preprocessed"] = str(specialist_root / "nnUNet_preprocessed")
    env["nnUNet_results"] = str(specialist_root / "nnUNet_results")

    if bool(cfg.overwrite_specialist_predictions) and dirs["roi_predictions"].exists():
        shutil.rmtree(dirs["roi_predictions"])
        dirs["roi_predictions"].mkdir(parents=True, exist_ok=True)

    cmd: list[str] = []
    if str(cfg.conda_env).strip():
        cmd.extend(["conda", "run", "--no-capture-output", "-n", str(cfg.conda_env)])
    cmd.extend(
        [
            "nnUNetv2_predict",
            "-i",
            str(dirs["roi_images"]),
            "-o",
            str(dirs["roi_predictions"]),
            "-d",
            str(int(cfg.nnunet_dataset_id)),
            "-c",
            str(cfg.nnunet_configuration),
            "-f",
            str(cfg.nnunet_fold),
            "-chk",
            str(cfg.nnunet_checkpoint),
            "-npp",
            str(int(cfg.num_processes_preprocessing)),
            "-nps",
            str(int(cfg.num_processes_export)),
            "-device",
            str(cfg.nnunet_device),
        ]
    )
    subprocess.run(cmd, env=env, check=True)


def _manifest_by_case(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        case_id = str(row["case_id"])
        side = str(row["side"])
        out.setdefault(case_id, {})[side] = row
    return out


def _load_specialist_side(
    cfg: OTAFV2Config,
    row: dict[str, Any],
    original_shape: tuple[int, int, int],
    pred_dir: Path,
) -> dict[str, Any]:
    side = str(row["side"])
    sample_id = str(row["sample_id"])
    if int(float(row.get("proposal_accepted", 0))) != 1:
        return {
            "side": side,
            "sample_id": sample_id,
            "accepted": False,
            "reject_reason": "proposal_rejected:" + str(row.get("proposal_reason", "")),
            "full_mask": np.zeros(original_shape, dtype=bool),
            "raw_voxels": 0,
            "cleaned_voxels": 0,
            "cc_count": 0,
            "largest_cc_ratio": 0.0,
            "prediction_path": "",
        }

    pred_path = pred_dir / f"{sample_id}.nii.gz"
    if not pred_path.exists():
        return {
            "side": side,
            "sample_id": sample_id,
            "accepted": False,
            "reject_reason": "specialist_prediction_missing",
            "full_mask": np.zeros(original_shape, dtype=bool),
            "raw_voxels": 0,
            "cleaned_voxels": 0,
            "cc_count": 0,
            "largest_cc_ratio": 0.0,
            "prediction_path": str(pred_path),
        }

    pred_label, _pred_img = load_label(pred_path)
    accepted, reason, cleaned, stats = clean_specialist_mask(
        pred_label > 0,
        min_component_voxels=int(cfg.min_specialist_component_voxels),
        min_largest_component_voxels=int(cfg.min_specialist_largest_component_voxels),
    )
    full_mask = backproject_roi_mask(cleaned, original_shape, row)
    if accepted and int(full_mask.sum()) == 0:
        accepted = False
        reason = "empty_after_backprojection"
    return {
        "side": side,
        "sample_id": sample_id,
        "accepted": bool(accepted),
        "reject_reason": reason,
        "full_mask": full_mask if accepted else np.zeros(original_shape, dtype=bool),
        "raw_voxels": int(stats["raw_voxels"]),
        "cleaned_voxels": int(stats["cleaned_voxels"]),
        "cc_count": int(stats["cc_count"]),
        "largest_cc_ratio": float(stats["largest_cc_ratio"]),
        "prediction_path": str(pred_path),
    }


def _specialist_label_from_results(shape: tuple[int, int, int], side_results: dict[str, dict[str, Any]]) -> tuple[np.ndarray, int]:
    label = np.zeros(shape, dtype=np.uint8)
    masks = {side: np.asarray(side_results[side]["full_mask"], dtype=bool) for side in SIDES}
    overlap_lr = int((masks["left"] & masks["right"]).sum())
    if overlap_lr > 0:
        masks["right"] = masks["right"] & ~masks["left"]
    for side in SIDES:
        label[masks[side]] = SIDE_TO_ADRENAL_LABEL[side]
    return label, overlap_lr


def _adrenal_label_from_anatomy(organ_label: np.ndarray) -> tuple[np.ndarray, int]:
    label = np.zeros_like(organ_label, dtype=np.uint8)
    left_mask = organ_label == SIDE_TO_ADRENAL_LABEL["left"]
    right_mask = organ_label == SIDE_TO_ADRENAL_LABEL["right"]
    overlap_lr = int((left_mask & right_mask).sum())
    if overlap_lr > 0:
        right_mask = right_mask & ~left_mask
    label[left_mask] = SIDE_TO_ADRENAL_LABEL["left"]
    label[right_mask] = SIDE_TO_ADRENAL_LABEL["right"]
    return label, overlap_lr


def _build_anatomy_for_apr(organ_tune_label: np.ndarray, adrenal_label: np.ndarray) -> np.ndarray:
    anatomy = np.zeros_like(organ_tune_label, dtype=np.uint8)
    organ_mask = np.isin(organ_tune_label, list(ORGAN_TUNE_LABELS))
    anatomy[organ_mask] = organ_tune_label[organ_mask]
    adrenal_mask = np.isin(adrenal_label, [SIDE_TO_ADRENAL_LABEL["left"], SIDE_TO_ADRENAL_LABEL["right"]])
    anatomy[adrenal_mask] = adrenal_label[adrenal_mask]
    anatomy[anatomy == LABEL_IDS["tumor"]] = 0
    return anatomy


def _compose_final_label(anatomy_label: np.ndarray, refined_tumor_mask: np.ndarray) -> np.ndarray:
    final = np.asarray(anatomy_label, dtype=np.uint8).copy()
    final[np.asarray(refined_tumor_mask, dtype=bool)] = LABEL_IDS["tumor"]
    return final


def _object_counts_at_iou(pred: np.ndarray, gt: np.ndarray, threshold: float = 0.5) -> dict[str, int]:
    pred_labels, pred_comps = connected_components_3d(pred)
    gt_labels, gt_comps = connected_components_3d(gt)
    matched_gt: set[int] = set()
    tp = 0
    for pred_comp in pred_comps:
        pred_mask = pred_labels == int(pred_comp["component_id"])
        best_iou = 0.0
        best_gt = -1
        for gt_comp in gt_comps:
            gt_id = int(gt_comp["component_id"])
            if gt_id in matched_gt:
                continue
            gt_mask = gt_labels == gt_id
            inter = int((pred_mask & gt_mask).sum())
            union = int((pred_mask | gt_mask).sum())
            iou = float(inter / union) if union else 0.0
            if iou > best_iou:
                best_iou = iou
                best_gt = gt_id
        if best_iou >= float(threshold) and best_gt > 0:
            tp += 1
            matched_gt.add(best_gt)
    fp = int(max(len(pred_comps) - tp, 0))
    fn = int(max(len(gt_comps) - tp, 0))
    return {"object_tp_at_0.5": tp, "object_fp_at_0.5": fp, "object_fn_at_0.5": fn}


def _metrics_with_surface(
    pred: np.ndarray,
    gt: np.ndarray,
    spacing: tuple[float, float, float],
) -> dict[str, Any]:
    metrics = binary_metrics(pred, gt)
    metrics.update(compute_surface_metrics_np(pred, gt, spacing, tolerance_mm=1.0))
    return metrics


def _safe_mean(values: list[float]) -> float:
    vals = [float(v) for v in values if np.isfinite(float(v))]
    return float(np.mean(vals)) if vals else float("nan")


def _safe_median(values: list[float]) -> float:
    vals = [float(v) for v in values if np.isfinite(float(v))]
    return float(np.median(vals)) if vals else float("nan")


def _build_class_summary(cfg: OTAFV2Config, final_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for class_name in EVAL_CLASS_NAMES:
        gt_label_id = _gt_label_id_for_class(cfg, class_name)
        pred_label_id = int(LABEL_IDS[class_name])
        row: dict[str, Any] = {
            "class_name": class_name,
            "pred_label_id": pred_label_id,
            "gt_label_id": gt_label_id,
            "num_valid_cases": 0,
            "mean_dice": float("nan"),
            "median_dice": float("nan"),
            "mean_iou": float("nan"),
            "mean_nsd_1mm": float("nan"),
            "mean_hd95_mm": float("nan"),
            "note": "",
        }
        if gt_label_id < 0:
            row["note"] = "gt_unavailable"
            rows.append(row)
            continue

        dice_values = [float(r[f"{class_name}_dice"]) for r in final_rows if f"{class_name}_dice" in r]
        iou_values = [float(r[f"{class_name}_iou"]) for r in final_rows if f"{class_name}_iou" in r]
        nsd_values = [float(r[f"{class_name}_nsd_1mm"]) for r in final_rows if f"{class_name}_nsd_1mm" in r]
        hd95_values = [float(r[f"{class_name}_hd95_mm"]) for r in final_rows if f"{class_name}_hd95_mm" in r]
        row.update(
            {
                "num_valid_cases": len(dice_values),
                "mean_dice": _safe_mean(dice_values),
                "median_dice": _safe_median(dice_values),
                "mean_iou": _safe_mean(iou_values),
                "mean_nsd_1mm": _safe_mean(nsd_values),
                "mean_hd95_mm": _safe_mean(hd95_values),
            }
        )
        rows.append(row)
    return rows


def fuse_and_evaluate(
    cfg: OTAFV2Config,
    cases: list[str],
    output_dir: Path,
    dirs: dict[str, Path],
    manifest_rows: list[dict[str, Any]],
) -> None:
    rows_by_case = _manifest_by_case(manifest_rows)
    adrenal_qc_rows: list[dict[str, Any]] = []
    fusion_qc_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    apr_component_rows: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []

    for case_id in tqdm(cases, desc="Stage 4/4 fuse/APR/evaluate", unit="case", ncols=120):
        try:
            old_label, old_img = load_label(_old_gcp_path(cfg, case_id))
            organ_label, organ_img = load_label(_organ_tune_path(cfg, case_id))
            _assert_same_grid(case_id, old_img, organ_img, "organ_tune_label")
            spacing = _spacing_mm(old_img)
            side_rows = rows_by_case.get(case_id, {})
            if _uses_specialist_adrenals(cfg):
                side_results: dict[str, dict[str, Any]] = {}
                for side in SIDES:
                    row = side_rows.get(side)
                    if row is None:
                        side_results[side] = {
                            "side": side,
                            "sample_id": "",
                            "accepted": False,
                            "reject_reason": "manifest_row_missing",
                            "full_mask": np.zeros(old_label.shape, dtype=bool),
                            "raw_voxels": 0,
                            "cleaned_voxels": 0,
                            "cc_count": 0,
                            "largest_cc_ratio": 0.0,
                            "prediction_path": "",
                        }
                    else:
                        side_results[side] = _load_specialist_side(cfg, row, tuple(old_label.shape), dirs["roi_predictions"])
                    result = side_results[side]
                    adrenal_qc_rows.append(
                        {
                            "case_id": case_id,
                            "side": side,
                            "adrenal_source": cfg.adrenal_source,
                            "sample_id": result["sample_id"],
                            "proposal_source": side_rows.get(side, {}).get("proposal_source", ""),
                            "proposal_reason": side_rows.get(side, {}).get("proposal_reason", ""),
                            "accepted": int(bool(result["accepted"])),
                            "reject_reason": result["reject_reason"],
                            "specialist_raw_voxels": result["raw_voxels"],
                            "specialist_cleaned_voxels": result["cleaned_voxels"],
                            "specialist_full_voxels": int(np.asarray(result["full_mask"], dtype=bool).sum()),
                            "cc_count": result["cc_count"],
                            "largest_cc_ratio": result["largest_cc_ratio"],
                            "prediction_path": result["prediction_path"],
                        }
                    )
                adrenal_label, adrenal_overlap_lr = _specialist_label_from_results(tuple(old_label.shape), side_results)
                adrenal_method = "adrenal_specialist_auto_roi"
            else:
                adrenal_label, adrenal_overlap_lr = _adrenal_label_from_anatomy(organ_label)
                for side in SIDES:
                    side_mask = adrenal_label == SIDE_TO_ADRENAL_LABEL[side]
                    side_voxels = int(side_mask.sum())
                    adrenal_qc_rows.append(
                        {
                            "case_id": case_id,
                            "side": side,
                            "adrenal_source": cfg.adrenal_source,
                            "sample_id": f"OTAFV2_{case_id}_{side}",
                            "proposal_source": "anatomy_label",
                            "proposal_reason": "adrenal_source=anatomy",
                            "accepted": int(side_voxels > 0),
                            "reject_reason": "" if side_voxels > 0 else "empty_anatomy_adrenal",
                            "specialist_raw_voxels": 0,
                            "specialist_cleaned_voxels": 0,
                            "specialist_full_voxels": side_voxels,
                            "cc_count": 0,
                            "largest_cc_ratio": 0.0,
                            "prediction_path": "",
                        }
                    )
                adrenal_method = "adrenal_anatomy_source"

            anatomy_label = _build_anatomy_for_apr(organ_label, adrenal_label)
            tumor_candidate = old_label == LABEL_IDS["tumor"]
            apr_result = apply_apr_to_tumor(anatomy_label, tumor_candidate, spacing, cfg, case_id)
            refined_tumor = np.asarray(apr_result["refined_tumor_mask"], dtype=bool)
            final_label = _compose_final_label(anatomy_label, refined_tumor)
            apr_component_rows.extend(apr_result.get("component_records", []))

            specialist_path = dirs["specialist"] / f"{case_id}_adrenal_specialist.nii.gz"
            anatomy_path = dirs["anatomy"] / f"{case_id}_anatomy_for_apr.nii.gz"
            apr_tumor_path = dirs["apr_tumor"] / f"{case_id}_apr_tumor.nii.gz"
            final_path = dirs["final"] / f"{case_id}_otafv2_fused.nii.gz"
            if bool(cfg.save_intermediate_nii):
                apr_tumor_label = np.zeros_like(old_label, dtype=np.uint8)
                apr_tumor_label[refined_tumor] = LABEL_IDS["tumor"]
                save_label(specialist_path, adrenal_label, old_img)
                save_label(anatomy_path, anatomy_label, old_img)
                save_label(apr_tumor_path, apr_tumor_label, old_img)
            save_label(final_path, final_label, old_img)

            forbidden_counts = {
                label_id: int((organ_label == label_id).sum())
                for label_id in sorted(FORBIDDEN_ORGAN_TUNE_LABELS)
            }
            fusion_qc_rows.append(
                {
                    "case_id": case_id,
                    "anatomy_source": cfg.anatomy_source,
                    "adrenal_source": cfg.adrenal_source,
                    "adrenal_left_right_overlap_voxels": adrenal_overlap_lr,
                    "specialist_left_right_overlap_voxels": adrenal_overlap_lr if _uses_specialist_adrenals(cfg) else 0,
                    "anatomy_left_adrenal_voxels": int((organ_label == LABEL_IDS["left_adrenal"]).sum()),
                    "anatomy_right_adrenal_voxels": int((organ_label == LABEL_IDS["right_adrenal"]).sum()),
                    "organ_tune_forbidden_left_adrenal_voxels": forbidden_counts[LABEL_IDS["left_adrenal"]],
                    "organ_tune_forbidden_right_adrenal_voxels": forbidden_counts[LABEL_IDS["right_adrenal"]],
                    "organ_tune_forbidden_tumor_voxels": forbidden_counts[LABEL_IDS["tumor"]],
                    "anatomy_tumor_voxels": int((anatomy_label == LABEL_IDS["tumor"]).sum()),
                    "old_tumor_voxels": int(tumor_candidate.sum()),
                    "apr_tumor_voxels": int(refined_tumor.sum()),
                    "final_tumor_voxels": int((final_label == LABEL_IDS["tumor"]).sum()),
                    "apr_applied": int(bool(apr_result.get("apr_applied", False))),
                    "apr_skip_reason": str(apr_result.get("skip_reason", "")),
                    "raw_component_count": int(apr_result.get("raw_component_count", 0)),
                    "kept_component_count": int(apr_result.get("kept_component_count", 0)),
                    "removed_component_count": int(apr_result.get("removed_component_count", 0)),
                    "removed_voxel_count": int(apr_result.get("removed_voxel_count", 0)),
                    "specialist_label_path": str(specialist_path) if bool(cfg.save_intermediate_nii) else "",
                    "anatomy_for_apr_path": str(anatomy_path) if bool(cfg.save_intermediate_nii) else "",
                    "apr_tumor_path": str(apr_tumor_path) if bool(cfg.save_intermediate_nii) else "",
                    "final_label_path": str(final_path),
                }
            )

            label_path = _case_label_path(cfg, case_id)
            if label_path is not None:
                gt_label, _gt_img = load_label(label_path)
                raw_row = {"case_id": case_id, "method": "old_gcpv5"}
                adrenal_source_row = {"case_id": case_id, "method": adrenal_method}
                final_row = {"case_id": case_id, "method": "otafv2_final"}
                side_dices_raw = []
                side_dices_adrenal_source = []
                side_dices_final = []
                for side in SIDES:
                    pred_label_id = SIDE_TO_ADRENAL_LABEL[side]
                    gt_label_id = gt_adrenal_label_id(cfg, side)
                    raw_metrics = _metrics_with_surface(old_label == pred_label_id, gt_label == gt_label_id, spacing)
                    adrenal_source_metrics = _metrics_with_surface(
                        adrenal_label == pred_label_id,
                        gt_label == gt_label_id,
                        spacing,
                    )
                    final_metrics = _metrics_with_surface(final_label == pred_label_id, gt_label == gt_label_id, spacing)
                    raw_row.update(prefix_metrics(f"{side}_adrenal", raw_metrics))
                    adrenal_source_row.update(prefix_metrics(f"{side}_adrenal", adrenal_source_metrics))
                    final_row.update(prefix_metrics(f"{side}_adrenal", final_metrics))
                    side_dices_raw.append(float(raw_metrics["dice"]))
                    side_dices_adrenal_source.append(float(adrenal_source_metrics["dice"]))
                    side_dices_final.append(float(final_metrics["dice"]))
                raw_row["mean_adrenal_dice"] = float(np.mean(side_dices_raw))
                adrenal_source_row["mean_adrenal_dice"] = float(np.mean(side_dices_adrenal_source))
                final_row["mean_adrenal_dice"] = float(np.mean(side_dices_final))

                for class_name in EVAL_CLASS_NAMES:
                    if class_name in {"left_adrenal", "right_adrenal", "tumor"}:
                        continue
                    gt_label_id = _gt_label_id_for_class(cfg, class_name)
                    if gt_label_id < 0:
                        continue
                    pred_label_id = LABEL_IDS[class_name]
                    metrics = _metrics_with_surface(final_label == pred_label_id, gt_label == gt_label_id, spacing)
                    final_row.update(prefix_metrics(class_name, metrics))

                if int(cfg.gt_tumor_label) >= 0:
                    raw_tumor = old_label == LABEL_IDS["tumor"]
                    final_tumor = final_label == LABEL_IDS["tumor"]
                    gt_tumor = gt_label == int(cfg.gt_tumor_label)
                    raw_tumor_metrics = _metrics_with_surface(raw_tumor, gt_tumor, spacing)
                    final_tumor_metrics = _metrics_with_surface(final_tumor, gt_tumor, spacing)
                    raw_tumor_metrics.update(_object_counts_at_iou(raw_tumor, gt_tumor, threshold=0.5))
                    final_tumor_metrics.update(_object_counts_at_iou(final_tumor, gt_tumor, threshold=0.5))
                    raw_row.update(prefix_metrics("tumor", raw_tumor_metrics))
                    final_row.update(prefix_metrics("tumor", final_tumor_metrics))

                metric_rows.extend([raw_row, adrenal_source_row, final_row])

        except Exception as exc:
            failed_rows.append({"case_id": case_id, "error": repr(exc)})

    write_csv(output_dir / "adrenal_qc.csv", adrenal_qc_rows)
    write_csv(output_dir / "fusion_qc.csv", fusion_qc_rows)
    write_csv(output_dir / "apr_component_metrics.csv", apr_component_rows)
    write_csv(output_dir / "case_metrics.csv", metric_rows)
    write_csv(output_dir / "failed_cases.csv", failed_rows)

    raw_rows = [row for row in metric_rows if row.get("method") == "old_gcpv5"]
    specialist_rows = [row for row in metric_rows if row.get("method") == "adrenal_specialist_auto_roi"]
    adrenal_source_rows = [
        row for row in metric_rows if row.get("method") in {"adrenal_specialist_auto_roi", "adrenal_anatomy_source"}
    ]
    final_rows = [row for row in metric_rows if row.get("method") == "otafv2_final"]
    class_summary_rows = _build_class_summary(cfg, final_rows)
    write_csv(output_dir / "class_summary.csv", class_summary_rows)
    summary = {
        "output_dir": str(output_dir),
        "num_cases": len(cases),
        "failed_cases": len(failed_rows),
        "specialist_accepted_case_sides": int(sum(int(row.get("accepted", 0)) for row in adrenal_qc_rows)),
        "specialist_total_case_sides": len(adrenal_qc_rows),
        "raw_mean_adrenal_dice": _safe_mean(
            [float(row["mean_adrenal_dice"]) for row in raw_rows if "mean_adrenal_dice" in row]
        ),
        "specialist_mean_adrenal_dice": _safe_mean(
            [float(row["mean_adrenal_dice"]) for row in specialist_rows if "mean_adrenal_dice" in row]
        ),
        "adrenal_source_mean_adrenal_dice": _safe_mean(
            [float(row["mean_adrenal_dice"]) for row in adrenal_source_rows if "mean_adrenal_dice" in row]
        ),
        "final_mean_adrenal_dice": _safe_mean(
            [float(row["mean_adrenal_dice"]) for row in final_rows if "mean_adrenal_dice" in row]
        ),
        "raw_mean_tumor_dice": _safe_mean([float(row["tumor_dice"]) for row in raw_rows if "tumor_dice" in row]),
        "final_mean_tumor_dice": _safe_mean([float(row["tumor_dice"]) for row in final_rows if "tumor_dice" in row]),
        "final_available_class_macro_dice": _safe_mean(
            [float(row["mean_dice"]) for row in class_summary_rows if int(row.get("num_valid_cases", 0)) > 0]
        ),
        "final_available_class_macro_nsd_1mm": _safe_mean(
            [float(row["mean_nsd_1mm"]) for row in class_summary_rows if int(row.get("num_valid_cases", 0)) > 0]
        ),
        "final_available_class_macro_hd95_mm": _safe_mean(
            [float(row["mean_hd95_mm"]) for row in class_summary_rows if int(row.get("num_valid_cases", 0)) > 0]
        ),
        "apr_removed_components": int(sum(int(row.get("removed_component_count", 0)) for row in fusion_qc_rows)),
        "apr_removed_voxels": int(sum(int(row.get("removed_voxel_count", 0)) for row in fusion_qc_rows)),
    }
    write_json(output_dir / "summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="OTAFV2 organ-tuned adrenal-tumor fusion pipeline.")
    parser.add_argument("--config", default="configs/pumch_v3_gcpv6_noflip_patch256.json")
    parser.add_argument("--run-old-gcp", action="store_true", help="Generate missing old GCP full-label NIfTI labels before OTAFV2.")
    parser.add_argument("--force-old-gcp", action="store_true", help="Regenerate old GCP full-label NIfTI labels even if they already exist.")
    parser.add_argument("--run-organ-tune", action="store_true", help="Generate missing anatomy NIfTI labels before OTAFV2.")
    parser.add_argument("--force-organ-tune", action="store_true", help="Regenerate anatomy NIfTI labels even if they already exist.")
    parser.add_argument("--prepare-only", action="store_true", help="Only generate OTAFV2 ROI images and manifest.")
    parser.add_argument("--skip-specialist-predict", action="store_true", help="Use existing roi_predictions.")
    parser.add_argument("--fuse-only", action="store_true", help="Reuse existing manifest/ROI predictions in the run output dir.")
    args = parser.parse_args()

    cfg_path = resolve_path(args.config, PROJECT_DIR)
    cfg = load_config(cfg_path)
    cases = load_case_ids(cfg)
    if bool(cfg.old_gcp_auto_generate) or bool(args.run_old_gcp) or bool(args.force_old_gcp):
        _run_old_gcp_generation(cfg, cases, force=bool(args.force_old_gcp))
    if bool(cfg.organ_tune_auto_generate) or bool(args.run_organ_tune) or bool(args.force_organ_tune):
        _run_organ_tune_generation(cfg, cases, force=bool(args.force_organ_tune))

    run_name = cfg.run_name.strip() or datetime.now().strftime("%Y%m%d_%H%M%S__otafv2")
    output_dir = ensure_dir(resolve_path(cfg.output_root, PROJECT_DIR) / run_name)
    dirs = _prepare_dirs(output_dir)
    _write_run_config(output_dir, cfg_path, cfg, args)

    manifest_path = output_dir / "otafv2_roi_manifest.csv"
    if args.fuse_only:
        if _uses_specialist_adrenals(cfg) and not manifest_path.exists():
            raise FileNotFoundError(f"fuse_only requested but manifest missing: {manifest_path}")
        manifest_rows = _read_csv(manifest_path) if manifest_path.exists() else []
    else:
        if _uses_specialist_adrenals(cfg):
            _stage("Stage 2/4 preparing adrenal specialist ROIs.")
            manifest_rows = prepare_rois(cfg, cases, output_dir, dirs)
        else:
            _stage("Stage 2/4 skipping adrenal specialist ROIs because adrenal_source=anatomy.")
            manifest_rows = []
            write_csv(manifest_path, manifest_rows)
        if args.prepare_only:
            return

    if _uses_specialist_adrenals(cfg) and not args.skip_specialist_predict and not args.fuse_only:
        run_specialist_prediction(cfg, dirs)
    else:
        reason = "reusing existing predictions" if _uses_specialist_adrenals(cfg) else "adrenal_source=anatomy"
        _stage(f"Stage 3/4 skipping AdrenalSpecialistV5 ROI inference ({reason}).")

    _stage("Stage 4/4 fusing labels, applying APR, saving final NIfTI, and computing metrics.")
    fuse_and_evaluate(cfg, cases, output_dir, dirs, manifest_rows)
    if not bool(cfg.save_intermediate_nii):
        _stage("Cleaning intermediate NIfTI directories; keeping final_fused_labels and metrics.")
        _cleanup_intermediate_dirs(output_dir, dirs)


if __name__ == "__main__":
    main()
