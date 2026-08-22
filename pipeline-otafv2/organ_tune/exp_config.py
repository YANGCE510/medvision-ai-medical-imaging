from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import asdict, dataclass


@dataclass
class InferenceConfig:
    exp_name: str
    val_roi_size: int
    sw_batch_size: int
    val_overlap: float
    fg_margin: int
    use_gcp: bool
    num_classes: int = 11
    tumor_label: int = 10
    seed: int = 1123
    num_workers: int = 4
    center: str = "PUMCH_V3"
    data_root: str = "/path/to/private_data/PPGL/ALL_PUMCH_mutil"
    data_list_root: str = "/path/to/private_data/SFADA_PPGL/data_list"
    image_folder: str = "images"
    label_folder: str = "labels_multiV4"
    device: str = "cuda:0"

    def to_dict(self):
        return asdict(self)


def _preset(
    exp_name: str,
    val_roi_size: int,
    *,
    sw_batch_size: int = 1,
    val_overlap: float = 0.25,
    fg_margin: int = 10,
    use_gcp: bool = True,
    num_classes: int = 11,
    tumor_label: int = 10,
    center: str = "PUMCH_V3",
    data_root: str = "/path/to/private_data/PPGL/ALL_PUMCH_mutil",
) -> InferenceConfig:
    return InferenceConfig(
        exp_name=exp_name,
        val_roi_size=val_roi_size,
        sw_batch_size=sw_batch_size,
        val_overlap=val_overlap,
        fg_margin=fg_margin,
        use_gcp=use_gcp,
        num_classes=num_classes,
        tumor_label=tumor_label,
        center=center,
        data_root=data_root,
    )


EXPERIMENT_PRESETS = {
    "baseline_128_no_gcp": _preset("baseline_128_no_gcp", 128, sw_batch_size=2, use_gcp=False),
    "gcp_only_128": _preset("gcp_only_128", 128, sw_batch_size=2),
    "gcp_patch160": _preset("gcp_patch160", 160),
    "gcp_patch192": _preset("gcp_patch192", 192),
    "gcp_patch224": _preset("gcp_patch224", 224),
    "gcp_patch256": _preset("gcp_patch256", 256),
    "gcp_patch288": _preset("gcp_patch288", 288),
    "gcp_patch320": _preset("gcp_patch320", 320),
    "gcp_patch384": _preset("gcp_patch384", 384),
    "gcp_patch160_margin20": _preset("gcp_patch160_margin20", 160, fg_margin=20),
    "organ_tune_patch256": _preset(
        "organ_tune_patch256",
        256,
        num_classes=9,
        tumor_label=10,
        center="ORGAN_TUNE_V1",
        data_root="/",
    ),
}


def _str2bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _apply_env_override(cfg: InferenceConfig) -> None:
    int_fields = {
        "VAL_ROI_SIZE": "val_roi_size",
        "SW_BATCH_SIZE": "sw_batch_size",
        "FG_MARGIN": "fg_margin",
        "NUM_CLASSES": "num_classes",
        "TUMOR_LABEL": "tumor_label",
        "SEED": "seed",
        "NUM_WORKERS": "num_workers",
    }
    for env_key, field_name in int_fields.items():
        raw = os.getenv(env_key)
        if raw is not None:
            setattr(cfg, field_name, int(raw))

    if os.getenv("USE_GCP") is not None:
        cfg.use_gcp = _str2bool(os.getenv("USE_GCP"))
    if os.getenv("VAL_OVERLAP") is not None:
        cfg.val_overlap = float(os.getenv("VAL_OVERLAP"))

    str_fields = {
        "CENTER": "center",
        "DATA_ROOT": "data_root",
        "DATA_LIST_ROOT": "data_list_root",
        "IMAGE_FOLDER": "image_folder",
        "LABEL_FOLDER": "label_folder",
        "DEVICE": "device",
    }
    for env_key, field_name in str_fields.items():
        raw = os.getenv(env_key)
        if raw:
            setattr(cfg, field_name, raw)


def _validate_cfg(cfg: InferenceConfig) -> None:
    if cfg.val_roi_size % 32 != 0:
        raise ValueError("val_roi_size 必须是 32 的倍数。")
    if cfg.sw_batch_size <= 0:
        raise ValueError("sw_batch_size 必须 > 0")
    if not (0.0 <= cfg.val_overlap < 1.0):
        raise ValueError("val_overlap 必须在 [0,1) 区间")
    if cfg.num_classes < 2:
        raise ValueError("num_classes 必须 >= 2（至少包含背景+1个前景）")

    partial_label_mode = _str2bool(os.getenv("SIGMOID_MULTILABEL", "0")) or cfg.exp_name == "organ_tune_patch256"
    if (not partial_label_mode) and not (1 <= cfg.tumor_label < cfg.num_classes):
        raise ValueError(
            f"tumor_label={cfg.tumor_label} 非法，必须满足 1 <= tumor_label < num_classes({cfg.num_classes})"
        )


def load_experiment_config(exp_name: str = None) -> InferenceConfig:
    selected_name = exp_name or os.getenv("EXP_NAME", "gcp_only_128")
    if selected_name not in EXPERIMENT_PRESETS:
        available = ", ".join(sorted(EXPERIMENT_PRESETS.keys()))
        raise ValueError(f"未知推理配置名: {selected_name}. 可选: {available}")

    cfg = deepcopy(EXPERIMENT_PRESETS[selected_name])
    _apply_env_override(cfg)
    _validate_cfg(cfg)
    return cfg
