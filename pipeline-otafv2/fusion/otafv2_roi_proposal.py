from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from fusion.otafv2_config import (
    LABEL_IDS,
    PROJECT_DIR,
    SIDE_TO_ADRENAL_LABEL,
    SIDE_TO_KIDNEY_LABEL,
    SIDES,
    OTAFV2Config,
    resolve_path,
)
from fusion.otafv2_utils import largest_component, mask_bbox, mask_centroid


_ANATOMY_PRIOR_CACHE: dict[str, dict[str, Any]] = {}


@dataclass
class ROIProposal:
    case_id: str
    side: str
    accepted: bool
    source: str
    reason: str
    center_xyz: tuple[float, float, float]
    old_gcp_adrenal_voxels: int
    organ_tune_kidney_voxels: int
    midline_source: str
    old_gcp_adrenal_largest_component_voxels: int = 0
    anatomy_center_x: float = float("nan")
    anatomy_center_y: float = float("nan")
    anatomy_center_z: float = float("nan")


def _clip_center(center: tuple[float, float, float], shape: tuple[int, int, int]) -> tuple[float, float, float]:
    return tuple(float(np.clip(center[i], 0, max(0, shape[i] - 1))) for i in range(3))


def _midline_x(label: np.ndarray, organ_names: tuple[str, ...] = ("aorta", "ivc", "vertebrae")) -> tuple[float, str]:
    centers = []
    sources = []
    for name in organ_names:
        mask = label == LABEL_IDS[name]
        if int(mask.sum()) > 0:
            center = mask_centroid(mask)
            if center is not None:
                centers.append(float(center[0]))
                sources.append(name)
    if centers:
        return float(np.mean(centers)), "+".join(sources)
    return float((label.shape[0] - 1) / 2.0), "image_center"


def _load_anatomy_prior(cfg: OTAFV2Config) -> dict[str, Any]:
    path = resolve_path(cfg.anatomy_prior_config, PROJECT_DIR)
    key = str(path)
    if key not in _ANATOMY_PRIOR_CACHE:
        with open(path, "r", encoding="utf-8") as f:
            _ANATOMY_PRIOR_CACHE[key] = json.load(f)
    return _ANATOMY_PRIOR_CACHE[key]


def _anatomy_prior_center(
    side: str,
    organ_tune_label: np.ndarray,
    cfg: OTAFV2Config,
) -> tuple[tuple[float, float, float] | None, int, str]:
    prior = _load_anatomy_prior(cfg)
    params = prior.get(side)
    if not isinstance(params, dict):
        raise ValueError(f"Anatomy prior missing side={side!r}: {cfg.anatomy_prior_config}")

    kidney_mask = organ_tune_label == SIDE_TO_KIDNEY_LABEL[side]
    kidney_voxels = int(kidney_mask.sum())
    if kidney_voxels < int(cfg.min_kidney_voxels):
        return None, kidney_voxels, "none"

    kidney_center = mask_centroid(kidney_mask)
    kidney_box = mask_bbox(kidney_mask)
    if kidney_center is None or kidney_box is None:
        return None, kidney_voxels, "none"

    _bbox_min, bbox_max = kidney_box
    midline, midline_source = _midline_x(organ_tune_label, organ_names=("aorta", "ivc"))
    if midline_source == "image_center":
        midline, midline_source = _midline_x(organ_tune_label, organ_names=("vertebrae",))

    medial_fraction = float(params["medial_fraction_from_kidney_to_vessel_midline_x"])
    y_offset = float(params["y_offset_from_kidney_center_vox"])
    z_offset = float(params["z_offset_from_kidney_top_vox"])

    center = (
        float(kidney_center[0] + medial_fraction * (midline - kidney_center[0])),
        float(kidney_center[1] + y_offset),
        float(bbox_max[2] + z_offset),
    )
    return center, kidney_voxels, midline_source


def _old_gcp_adrenal_component(
    side: str,
    old_gcp_label: np.ndarray,
    cfg: OTAFV2Config,
) -> tuple[tuple[float, float, float] | None, int, int]:
    adrenal_mask = old_gcp_label == SIDE_TO_ADRENAL_LABEL[side]
    adrenal_voxels = int(adrenal_mask.sum())
    if adrenal_voxels < int(cfg.min_pred_adrenal_voxels):
        return None, adrenal_voxels, 0
    _mask, comp = largest_component(adrenal_mask, min_voxels=int(cfg.min_pred_adrenal_voxels))
    if comp is None:
        return None, adrenal_voxels, 0
    center = (float(comp["centroid_x"]), float(comp["centroid_y"]), float(comp["centroid_z"]))
    return center, adrenal_voxels, int(comp["voxel_count"])


def proposal_from_sources(
    case_id: str,
    side: str,
    old_gcp_label: np.ndarray,
    organ_tune_label: np.ndarray,
    cfg: OTAFV2Config,
) -> ROIProposal:
    if side not in SIDES:
        raise ValueError(f"Invalid side={side!r}")
    if tuple(old_gcp_label.shape) != tuple(organ_tune_label.shape):
        raise ValueError(
            f"{case_id}: old GCP and organ-tune label shape mismatch "
            f"{old_gcp_label.shape} vs {organ_tune_label.shape}"
        )

    shape = tuple(int(x) for x in old_gcp_label.shape[:3])
    old_center, old_adrenal_voxels, old_largest = _old_gcp_adrenal_component(side, old_gcp_label, cfg)
    anatomy_center, organ_kidney_voxels, midline_source = _anatomy_prior_center(side, organ_tune_label, cfg)

    if old_center is not None:
        source = "old_gcp_adrenal_anchor"
        reason = "old_gcp_adrenal_largest_component_available"
        if anatomy_center is not None:
            source = "old_gcp_adrenal_anchor_gcpv5_1_anatomy_available"
            reason = "old_gcp_adrenal_center_preserved;gcpv5_1_anatomy_fallback_available"
        return ROIProposal(
            case_id=case_id,
            side=side,
            accepted=True,
            source=source,
            reason=reason,
            center_xyz=_clip_center(old_center, shape),
            old_gcp_adrenal_voxels=old_adrenal_voxels,
            organ_tune_kidney_voxels=organ_kidney_voxels,
            midline_source=midline_source,
            old_gcp_adrenal_largest_component_voxels=old_largest,
            anatomy_center_x=float(anatomy_center[0]) if anatomy_center is not None else float("nan"),
            anatomy_center_y=float(anatomy_center[1]) if anatomy_center is not None else float("nan"),
            anatomy_center_z=float(anatomy_center[2]) if anatomy_center is not None else float("nan"),
        )

    if anatomy_center is not None:
        return ROIProposal(
            case_id=case_id,
            side=side,
            accepted=True,
            source="gcpv5_1_organ_anatomy_prior",
            reason="old_gcp_adrenal_missing_or_too_small",
            center_xyz=_clip_center(anatomy_center, shape),
            old_gcp_adrenal_voxels=old_adrenal_voxels,
            organ_tune_kidney_voxels=organ_kidney_voxels,
            midline_source=midline_source,
            old_gcp_adrenal_largest_component_voxels=old_largest,
            anatomy_center_x=float(anatomy_center[0]),
            anatomy_center_y=float(anatomy_center[1]),
            anatomy_center_z=float(anatomy_center[2]),
        )

    center = tuple(float((shape[i] - 1) / 2.0) for i in range(3))
    return ROIProposal(
        case_id=case_id,
        side=side,
        accepted=False,
        source="none",
        reason="no_old_gcp_adrenal_or_gcpv5_1_kidney_anchor",
        center_xyz=center,
        old_gcp_adrenal_voxels=old_adrenal_voxels,
        organ_tune_kidney_voxels=organ_kidney_voxels,
        midline_source=midline_source,
        old_gcp_adrenal_largest_component_voxels=old_largest,
    )
