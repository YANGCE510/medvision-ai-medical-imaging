from __future__ import annotations

from typing import Any

import numpy as np

try:
    from scipy.spatial import cKDTree
except Exception:  # pragma: no cover - scipy is expected in the ppgl env.
    cKDTree = None

try:
    from scipy import ndimage
except Exception:  # pragma: no cover - scipy is expected in the ppgl env.
    ndimage = None

from fusion.otafv2_config import LABEL_IDS, OTAFV2Config
from fusion.otafv2_utils import connected_components_3d


ANCHOR_ORGANS = (
    "aorta",
    "left_kidney",
    "right_kidney",
    "ivc",
    "left_adrenal",
    "right_adrenal",
    "left_psoas",
    "right_psoas",
    "vertebrae",
)


def _safe_float(value: Any, default: float = float("nan")) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    return out if np.isfinite(out) else float(default)


def _linear_decay_score(distance_mm: float, good_mm: float, bad_mm: float) -> float:
    distance = _safe_float(distance_mm, float("nan"))
    if not np.isfinite(distance):
        return 0.0
    good = float(good_mm)
    bad = max(float(bad_mm), good + 1e-6)
    if distance <= good:
        return 1.0
    if distance >= bad:
        return 0.0
    return float(1.0 - ((distance - good) / (bad - good)))


def _weighted_mean(pairs: list[tuple[float, float]]) -> float:
    valid = [(float(w), float(v)) for w, v in pairs if float(w) > 0 and np.isfinite(float(v))]
    if not valid:
        return 0.0
    total_weight = sum(w for w, _ in valid)
    return float(sum(w * v for w, v in valid) / max(total_weight, 1e-6))


def _finite_min(values: list[float]) -> float:
    finite = [float(v) for v in values if np.isfinite(float(v))]
    return float(min(finite)) if finite else float("nan")


def _surface_mask(mask: np.ndarray) -> np.ndarray:
    mask_bool = np.asarray(mask, dtype=bool)
    if not mask_bool.any():
        return mask_bool.copy()
    padded = np.pad(mask_bool, 1, mode="constant", constant_values=False)
    eroded = np.ones_like(mask_bool, dtype=bool)
    sx, sy, sz = mask_bool.shape
    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
        eroded &= padded[1 + dx : 1 + dx + sx, 1 + dy : 1 + dy + sy, 1 + dz : 1 + dz + sz]
    surface = mask_bool & (~eroded)
    return surface if surface.any() else mask_bool.copy()


def _surface_points_mm(mask: np.ndarray, spacing_mm: tuple[float, float, float]) -> np.ndarray:
    mask_bool = np.asarray(mask, dtype=bool)
    if ndimage is not None:
        objects = ndimage.find_objects(mask_bool)
        if not objects or objects[0] is None:
            return np.empty((0, 3), dtype=np.float64)
        bbox = objects[0]
        bbox_lo = np.asarray([axis_slice.start for axis_slice in bbox], dtype=int)
        bbox_hi = np.asarray([axis_slice.stop for axis_slice in bbox], dtype=int)
    else:
        foreground = np.argwhere(mask_bool)
        if foreground.size == 0:
            return np.empty((0, 3), dtype=np.float64)
        bbox_lo = foreground.min(axis=0)
        bbox_hi = foreground.max(axis=0) + 1
    lo = np.maximum(bbox_lo - 1, 0)
    hi = np.minimum(bbox_hi + 1, np.asarray(mask_bool.shape, dtype=int))
    crop = mask_bool[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]]
    pts = np.argwhere(_surface_mask(crop))
    if pts.size == 0:
        return np.empty((0, 3), dtype=np.float64)
    pts += lo.reshape(1, 3)
    return pts.astype(np.float64, copy=False) * np.asarray(spacing_mm, dtype=np.float64).reshape(1, 3)


def _min_surface_distance_mm(component_points: np.ndarray, organ_points: np.ndarray) -> float:
    if component_points.size == 0 or organ_points.size == 0:
        return float("nan")
    if cKDTree is None:
        # Small fallback for environments without scipy; intended for smoke tests only.
        best = float("inf")
        for start in range(0, component_points.shape[0], 256):
            chunk = component_points[start : start + 256]
            distances = np.sqrt(((chunk[:, None, :] - organ_points[None, :, :]) ** 2).sum(axis=2))
            best = min(best, float(np.min(distances)))
        return best
    tree = cKDTree(organ_points)
    try:
        distances, _ = tree.query(component_points, k=1, workers=-1)
    except TypeError:
        distances, _ = tree.query(component_points, k=1)
    return float(np.min(distances)) if distances.size else float("nan")


def _build_anchor_points(
    anatomy_label: np.ndarray,
    spacing_mm: tuple[float, float, float],
    min_voxels: int = 16,
) -> dict[str, dict[str, Any]]:
    anchors: dict[str, dict[str, Any]] = {}
    present_labels = {int(value) for value in np.unique(anatomy_label)}
    for name in ANCHOR_ORGANS:
        label_id = int(LABEL_IDS[name])
        if label_id not in present_labels:
            anchors[name] = {
                "available": False,
                "voxels": 0,
                "points": np.empty((0, 3)),
            }
            continue
        mask = anatomy_label == LABEL_IDS[name]
        voxels = int(mask.sum())
        anchors[name] = {
            "available": voxels >= int(min_voxels),
            "voxels": voxels,
            "points": _surface_points_mm(mask, spacing_mm) if voxels >= int(min_voxels) else np.empty((0, 3)),
        }
    return anchors


def _nearest_side(left_dist: float, right_dist: float) -> str:
    left_ok = np.isfinite(left_dist)
    right_ok = np.isfinite(right_dist)
    if left_ok and right_ok:
        if abs(left_dist - right_dist) <= 1e-6:
            return "tie"
        return "left" if left_dist < right_dist else "right"
    if left_ok:
        return "left"
    if right_ok:
        return "right"
    return "uncertain"


def apply_apr_to_tumor(
    anatomy_label: np.ndarray,
    tumor_candidate: np.ndarray,
    spacing_mm: tuple[float, float, float],
    cfg: OTAFV2Config,
    case_id: str,
) -> dict[str, Any]:
    raw_tumor = np.asarray(tumor_candidate, dtype=bool)
    if not bool(cfg.apr_enabled):
        return {
            "case_id": case_id,
            "apr_applied": False,
            "skip_reason": "apr_disabled",
            "refined_tumor_mask": raw_tumor.copy(),
            "component_records": [],
            "raw_component_count": 0,
            "kept_component_count": 0,
            "removed_component_count": 0,
            "raw_pred_voxels": int(raw_tumor.sum()),
            "refined_pred_voxels": int(raw_tumor.sum()),
            "removed_voxel_count": 0,
        }

    labels, comps = connected_components_3d(raw_tumor)
    if not comps:
        empty = np.zeros_like(raw_tumor, dtype=bool)
        return {
            "case_id": case_id,
            "apr_applied": True,
            "skip_reason": "",
            "refined_tumor_mask": empty,
            "component_records": [],
            "raw_component_count": 0,
            "kept_component_count": 0,
            "removed_component_count": 0,
            "raw_pred_voxels": 0,
            "refined_pred_voxels": 0,
            "removed_voxel_count": 0,
        }

    anchors = _build_anchor_points(anatomy_label, spacing_mm)
    has_anchor = any(bool(info["available"]) for info in anchors.values())
    if not has_anchor:
        return {
            "case_id": case_id,
            "apr_applied": False,
            "skip_reason": "no_valid_anatomy_anchor",
            "refined_tumor_mask": raw_tumor.copy(),
            "component_records": [],
            "raw_component_count": int(len(comps)),
            "kept_component_count": int(len(comps)),
            "removed_component_count": 0,
            "raw_pred_voxels": int(raw_tumor.sum()),
            "refined_pred_voxels": int(raw_tumor.sum()),
            "removed_voxel_count": 0,
        }

    refined = np.zeros_like(raw_tumor, dtype=bool)
    records: list[dict[str, Any]] = []
    kept = 0
    spacing_arr = np.asarray(spacing_mm, dtype=np.float64)
    component_voxel_volume = float(np.prod(spacing_arr))

    for comp in comps:
        component_id = int(comp["component_id"])
        bbox_lo = np.asarray(
            [int(comp["bbox_min_x"]), int(comp["bbox_min_y"]), int(comp["bbox_min_z"])],
            dtype=int,
        )
        bbox_hi = np.asarray(
            [int(comp["bbox_max_x"]) + 1, int(comp["bbox_max_y"]) + 1, int(comp["bbox_max_z"]) + 1],
            dtype=int,
        )
        component_slices = tuple(slice(int(bbox_lo[i]), int(bbox_hi[i])) for i in range(3))
        component_mask = labels[component_slices] == component_id
        component_points = _surface_points_mm(component_mask, spacing_mm)
        if component_points.size:
            component_points += (bbox_lo.astype(np.float64) * spacing_arr).reshape(1, 3)
        distances = {
            name: _min_surface_distance_mm(component_points, anchors[name]["points"])
            if bool(anchors[name]["available"])
            else float("nan")
            for name in ANCHOR_ORGANS
        }

        left_kidney_dist = distances["left_kidney"]
        right_kidney_dist = distances["right_kidney"]
        candidate_side = _nearest_side(left_kidney_dist, right_kidney_dist)
        vessel_dist = distances["ivc"] if candidate_side == "right" else distances["aorta"]
        if not np.isfinite(vessel_dist):
            vessel_dist = _finite_min([distances["aorta"], distances["ivc"]])
        kidney_dist = _finite_min([left_kidney_dist, right_kidney_dist])
        posterior_dist = _finite_min([distances["vertebrae"], distances["left_psoas"], distances["right_psoas"]])
        if candidate_side == "left":
            adrenal_dist = distances["left_adrenal"]
        elif candidate_side == "right":
            adrenal_dist = distances["right_adrenal"]
        else:
            adrenal_dist = _finite_min([distances["left_adrenal"], distances["right_adrenal"]])

        good = float(cfg.apr_good_distance_mm)
        bad = float(cfg.apr_bad_distance_mm)
        vessel_score = _linear_decay_score(vessel_dist, good, bad)
        kidney_score = _linear_decay_score(kidney_dist, good, bad)
        posterior_score = _linear_decay_score(posterior_dist, good, bad)
        anatomy_score = _weighted_mean([(0.45, vessel_score), (0.35, kidney_score), (0.20, posterior_score)])

        volume_mm3 = int(comp["voxel_count"]) * component_voxel_volume
        geometry_score = float(np.clip(volume_mm3 / max(float(cfg.apr_volume_ref_mm3), 1e-6), 0.0, 1.0))
        adrenal_score = _linear_decay_score(adrenal_dist, good, bad)
        total_score = _weighted_mean(
            [
                (float(cfg.apr_weight_anatomy), anatomy_score),
                (float(cfg.apr_weight_geometry), geometry_score),
                (float(cfg.apr_weight_adrenal) * float(cfg.apr_adrenal_bonus_weight), adrenal_score),
            ]
        )

        if int(comp["voxel_count"]) < int(cfg.apr_min_component_voxels):
            keep = False
            reason = "prefilter_small_component"
        else:
            keep = bool(total_score >= float(cfg.apr_tau))
            reason = "kept" if keep else "score_below_tau"

        if keep:
            refined_crop = refined[component_slices]
            refined_crop[component_mask] = True
            kept += 1

        records.append(
            {
                "case_id": case_id,
                "component_id": component_id,
                "keep_flag": int(keep),
                "remove_reason": reason,
                "voxel_count": int(comp["voxel_count"]),
                "volume_mm3": float(volume_mm3),
                "candidate_side": candidate_side,
                "d_aorta_mm": distances["aorta"],
                "d_ivc_mm": distances["ivc"],
                "d_left_kidney_mm": left_kidney_dist,
                "d_right_kidney_mm": right_kidney_dist,
                "d_left_adrenal_mm": distances["left_adrenal"],
                "d_right_adrenal_mm": distances["right_adrenal"],
                "d_vertebrae_mm": distances["vertebrae"],
                "d_left_psoas_mm": distances["left_psoas"],
                "d_right_psoas_mm": distances["right_psoas"],
                "vessel_score": vessel_score,
                "kidney_score": kidney_score,
                "posterior_score": posterior_score,
                "anatomy_score": anatomy_score,
                "geometry_score": geometry_score,
                "adrenal_score": adrenal_score,
                "aprv5_like_score": total_score,
            }
        )

    return {
        "case_id": case_id,
        "apr_applied": True,
        "skip_reason": "",
        "refined_tumor_mask": refined,
        "component_records": records,
        "raw_component_count": int(len(comps)),
        "kept_component_count": int(kept),
        "removed_component_count": int(max(len(comps) - kept, 0)),
        "raw_pred_voxels": int(raw_tumor.sum()),
        "refined_pred_voxels": int(refined.sum()),
        "removed_voxel_count": int(max(int(raw_tumor.sum()) - int(refined.sum()), 0)),
    }
