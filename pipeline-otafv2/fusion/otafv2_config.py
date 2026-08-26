from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]

LABEL_IDS = {
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

SIDES = ("left", "right")
SIDE_TO_ADRENAL_LABEL = {"left": LABEL_IDS["left_adrenal"], "right": LABEL_IDS["right_adrenal"]}
SIDE_TO_KIDNEY_LABEL = {"left": LABEL_IDS["left_kidney"], "right": LABEL_IDS["right_kidney"]}


@dataclass
class OTAFV2Config:
    run_name: str = ""
    output_root: str = "outputs"
    use_model_registry: bool = False
    model_registry_path: str = "outputs/model_registry.json"

    image_dir: str = "input/images"
    label_dir: str = ""
    old_gcp_label_dir: str = "outputs/raw_gcp/gcpv6_noflip_patch256/prediction_labels_nii"
    old_gcp_suffix: str = "_pred.nii.gz"
    old_gcp_auto_generate: bool = True
    old_gcp_root: str = "raw_gcp"
    old_gcp_python: str = ""
    old_gcp_center: str = "PUMCH_V3"
    old_gcp_split: str = "test"
    old_gcp_exp_name: str = "gcp_patch256"
    old_gcp_data_root: str = "input"
    old_gcp_data_list_root: str = "data_list"
    old_gcp_image_folder: str = "images"
    old_gcp_label_folder: str = "labels_multiV4"
    old_gcp_checkpoint: str = "checkpoints/raw_gcp/gcpv6_noflip_patch256/model_best.pth"
    old_gcp_num_classes: int = 11
    old_gcp_tumor_label: int = LABEL_IDS["tumor"]
    old_gcp_roi_size: int = 256
    old_gcp_sw_batch_size: int = 1
    old_gcp_overlap: float = 0.25
    old_gcp_fg_margin: int = 10
    old_gcp_cache_rate: float = 0.0
    old_gcp_num_workers: int = 2
    old_gcp_device: str = "cuda:0"
    old_gcp_output_root: str = "outputs/raw_gcp"
    old_gcp_run_name: str = "gcpv6_noflip_patch256"
    old_gcp_tag: str = "gcpv6_noflip_patch256"
    old_gcp_nifti_postfix: str = "pred"
    old_gcp_pytorch_cuda_alloc_conf: str = "expandable_segments:True"
    organ_tune_label_dir: str = "outputs/organ_tune/gcpv5_1_model_best/prediction_labels_nii"
    organ_tune_suffix: str = "_organ_tune.nii.gz"
    organ_tune_auto_generate: bool = True
    organ_tune_gcpv5_1_root: str = "organ_tune"
    organ_tune_python: str = ""
    organ_tune_center: str = "OTAFV2_PUMCH_ORGAN_TUNE"
    organ_tune_split: str = "test"
    organ_tune_exp_name: str = "organ_tune_patch256"
    organ_tune_data_root: str = "input"
    organ_tune_data_list_root: str = "data_list"
    organ_tune_image_folder: str = "images"
    organ_tune_label_folder: str = "labels_multiV4"
    organ_tune_checkpoint: str = "checkpoints/organ_tune/gcpv5_1_model_best/model_best.pth"
    organ_tune_num_classes: int = 9
    organ_tune_class_names: str = (
        "aorta,left_kidney,right_kidney,ivc,left_adrenal,right_adrenal,left_psoas,right_psoas,vertebrae"
    )
    organ_tune_roi_size: int = 160
    organ_tune_sw_batch_size: int = 1
    organ_tune_overlap: float = 0.25
    organ_tune_cache_rate: float = 0.0
    organ_tune_num_workers: int = 2
    organ_tune_device: str = "cuda:0"
    organ_tune_prob_threshold: float = 0.5
    organ_tune_output_root: str = "outputs/organ_tune"
    organ_tune_run_name: str = "gcpv5_1_model_best"
    organ_tune_tag: str = "gcpv5_1_model_best"
    organ_tune_nifti_postfix: str = "organ_tune"
    organ_tune_export_only: bool = True
    totalseg_root: str = ""
    totalseg_python: str = ""
    totalseg_task: str = "total"
    totalseg_device: str = ""
    totalseg_fast: bool = False
    totalseg_fastest: bool = False
    totalseg_roi_subset: list[str] = field(default_factory=list)
    totalseg_nr_thr_resamp: int = 1
    totalseg_nr_thr_saving: int = 1
    totalseg_remove_small_blobs_mm3: float = 0.0
    totalseg_save_raw_total: bool = False
    totalseg_quiet: bool = True
    save_intermediate_nii: bool = False
    gt_left_adrenal_label: int = LABEL_IDS["left_adrenal"]
    gt_right_adrenal_label: int = LABEL_IDS["right_adrenal"]
    gt_tumor_label: int = LABEL_IDS["tumor"]
    gt_label_map: dict[str, int] = field(default_factory=dict)

    case_ids: list[str] = field(default_factory=list)
    case_list_file: str = ""
    max_cases: int = 0

    roi_proposal_mode: str = "otafv2_hybrid_conservative"
    roi_anchor_source: str = "old_gcp_adrenal"
    anatomy_source: str = "gcpv5_1_organs"
    adrenal_source: str = "specialist"
    roi_size: list[int] = field(default_factory=lambda: [96, 96, 96])
    roi_pad_value: float = -1024.0
    min_pred_adrenal_voxels: int = 16
    min_kidney_voxels: int = 256
    anatomy_prior_config: str = "configs/anatomy_prior_amos_cads_prior_train.json"

    adrenal_specialist_root: str = "checkpoints/adrenal_specialist"
    nnunet_dataset_id: int = 705
    nnunet_configuration: str = "3d_fullres"
    nnunet_fold: str = "0"
    nnunet_checkpoint: str = "checkpoint_best.pth"
    conda_env: str = "ppgl"
    nnunet_device: str = "cuda"
    num_processes_preprocessing: int = 3
    num_processes_export: int = 3
    overwrite_specialist_predictions: bool = False

    min_specialist_component_voxels: int = 8
    min_specialist_largest_component_voxels: int = 16
    keep_old_adrenal_if_specialist_rejected: bool = False

    apr_enabled: bool = True
    apr_min_component_voxels: int = 0
    apr_tau: float = 0.50
    apr_use_candidate_quality: bool = False
    apr_weight_anatomy: float = 0.55
    apr_weight_geometry: float = 0.25
    apr_weight_adrenal: float = 0.20
    apr_good_distance_mm: float = 8.0
    apr_bad_distance_mm: float = 80.0
    apr_volume_ref_mm3: float = 2222.0
    apr_adrenal_bonus_weight: float = 0.10


def gt_adrenal_label_id(cfg: OTAFV2Config, side: str) -> int:
    if side == "left":
        return int(cfg.gt_left_adrenal_label)
    if side == "right":
        return int(cfg.gt_right_adrenal_label)
    raise ValueError(f"Invalid side={side!r}")


def resolve_path(path_value: str | Path, base: Path = PROJECT_DIR) -> Path:
    path = Path(str(path_value))
    return path if path.is_absolute() else (base / path).resolve()


def normalize_case_id(case_id: str) -> str:
    name = Path(str(case_id).strip()).name
    if name.endswith(".nii.gz"):
        return name[:-7]
    if name.endswith(".nii"):
        return name[:-4]
    return name


def load_config(path: str | Path) -> OTAFV2Config:
    cfg_path = resolve_path(path)
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)
    cfg = OTAFV2Config(**raw)
    if bool(cfg.use_model_registry):
        _apply_model_registry(cfg)
    if cfg.roi_proposal_mode not in {"otafv2_hybrid_conservative"}:
        raise ValueError("roi_proposal_mode must be 'otafv2_hybrid_conservative'.")
    if cfg.roi_anchor_source != "old_gcp_adrenal":
        raise ValueError("roi_anchor_source must be 'old_gcp_adrenal'.")
    if cfg.anatomy_source not in {"gcpv5_1_organs", "totalsegmentator_organs"}:
        raise ValueError("anatomy_source must be 'gcpv5_1_organs' or 'totalsegmentator_organs'.")
    if cfg.adrenal_source not in {"specialist", "anatomy"}:
        raise ValueError("adrenal_source must be 'specialist' or 'anatomy'.")
    if cfg.anatomy_source == "totalsegmentator_organs":
        if str(cfg.totalseg_task) not in {"total", "total_mr"}:
            raise ValueError("totalseg_task must be 'total' or 'total_mr' for totalsegmentator_organs.")
        if bool(cfg.totalseg_fast) and bool(cfg.totalseg_fastest):
            raise ValueError("totalseg_fast and totalseg_fastest cannot both be true.")
        if int(cfg.totalseg_nr_thr_resamp) <= 0 or int(cfg.totalseg_nr_thr_saving) <= 0:
            raise ValueError("totalseg_nr_thr_resamp and totalseg_nr_thr_saving must be > 0.")
    if len(cfg.roi_size) != 3 or any(int(x) <= 0 for x in cfg.roi_size):
        raise ValueError(f"roi_size must be three positive integers, got {cfg.roi_size!r}.")
    if not str(cfg.anatomy_prior_config).strip():
        raise ValueError("otafv2_hybrid_conservative requires anatomy_prior_config.")
    if not (0.0 <= float(cfg.apr_tau) <= 1.0):
        raise ValueError("apr_tau must be in [0, 1].")
    for key in ("apr_weight_anatomy", "apr_weight_geometry", "apr_weight_adrenal"):
        if float(getattr(cfg, key)) < 0.0:
            raise ValueError(f"{key} must be non-negative.")
    return cfg


def _registry_models(cfg: OTAFV2Config) -> dict[str, Any]:
    registry_path = resolve_path(cfg.model_registry_path, PROJECT_DIR)
    if not registry_path.exists():
        raise FileNotFoundError(f"use_model_registry=True but registry is missing: {registry_path}")
    with registry_path.open("r", encoding="utf-8") as f:
        registry = json.load(f)
    models = registry.get("models", {})
    if not isinstance(models, dict):
        raise ValueError(f"Invalid model registry format: {registry_path}")
    return models


def _apply_model_registry(cfg: OTAFV2Config) -> None:
    models = _registry_models(cfg)

    raw_gcp = models.get("raw_gcp", {})
    if isinstance(raw_gcp, dict):
        if raw_gcp.get("checkpoint"):
            cfg.old_gcp_checkpoint = str(raw_gcp["checkpoint"])
        if raw_gcp.get("run_name"):
            cfg.old_gcp_run_name = str(raw_gcp["run_name"])
        if raw_gcp.get("tag"):
            cfg.old_gcp_tag = str(raw_gcp["tag"])
        if raw_gcp.get("label_dir"):
            cfg.old_gcp_label_dir = str(raw_gcp["label_dir"])
        elif raw_gcp.get("run_name"):
            cfg.old_gcp_label_dir = f"{cfg.old_gcp_output_root}/{raw_gcp['run_name']}/prediction_labels_nii"

    organ_tune = models.get("organ_tune", {})
    if isinstance(organ_tune, dict):
        if organ_tune.get("checkpoint"):
            cfg.organ_tune_checkpoint = str(organ_tune["checkpoint"])
        if organ_tune.get("run_name"):
            cfg.organ_tune_run_name = str(organ_tune["run_name"])
        if organ_tune.get("tag"):
            cfg.organ_tune_tag = str(organ_tune["tag"])
        if organ_tune.get("label_dir"):
            cfg.organ_tune_label_dir = str(organ_tune["label_dir"])
        elif organ_tune.get("run_name"):
            cfg.organ_tune_label_dir = f"{cfg.organ_tune_output_root}/{organ_tune['run_name']}/prediction_labels_nii"

    specialist = models.get("adrenal_specialist", {})
    if isinstance(specialist, dict):
        if specialist.get("root"):
            cfg.adrenal_specialist_root = str(specialist["root"])
        if specialist.get("nnunet_checkpoint"):
            cfg.nnunet_checkpoint = str(specialist["nnunet_checkpoint"])
        elif specialist.get("checkpoint"):
            cfg.nnunet_checkpoint = Path(str(specialist["checkpoint"])).name
        if specialist.get("dataset_id"):
            cfg.nnunet_dataset_id = int(specialist["dataset_id"])
        if specialist.get("configuration"):
            cfg.nnunet_configuration = str(specialist["configuration"])
        if specialist.get("fold"):
            cfg.nnunet_fold = str(specialist["fold"])


def load_case_ids(cfg: OTAFV2Config) -> list[str]:
    if cfg.case_ids:
        cases = [normalize_case_id(str(x)) for x in cfg.case_ids if str(x).strip()]
    elif cfg.case_list_file:
        case_file = resolve_path(cfg.case_list_file, PROJECT_DIR)
        cases = [normalize_case_id(line) for line in case_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        raw_dir = resolve_path(cfg.old_gcp_label_dir, PROJECT_DIR)
        suffix = str(cfg.old_gcp_suffix)
        cases = []
        for path in sorted(raw_dir.glob(f"*{suffix}")):
            name = path.name
            cases.append(normalize_case_id(name[: -len(suffix)] if suffix else path.stem))
        if not cases and bool(cfg.old_gcp_auto_generate):
            split_file = resolve_path(cfg.old_gcp_data_list_root, PROJECT_DIR) / str(cfg.old_gcp_center) / str(cfg.old_gcp_split)
            if not split_file.exists() and split_file.with_suffix(".jsonl").exists():
                split_file = split_file.with_suffix(".jsonl")
            for line in split_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                if split_file.suffix == ".jsonl":
                    row = json.loads(line)
                    cases.append(normalize_case_id(row.get("case_id") or row.get("sample_id") or row.get("image_path", "")))
                else:
                    cases.append(normalize_case_id(line))

    seen: set[str] = set()
    unique: list[str] = []
    for case_id in cases:
        if case_id not in seen:
            unique.append(case_id)
            seen.add(case_id)
    if int(cfg.max_cases) > 0:
        unique = unique[: int(cfg.max_cases)]
    if not unique:
        raise ValueError("No case ids resolved for OTAFV2 run.")
    return unique
