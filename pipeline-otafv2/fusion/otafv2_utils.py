from __future__ import annotations

import csv
import json
from collections import deque
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

try:
    from scipy import ndimage
    from scipy.spatial import cKDTree
except Exception:  # pragma: no cover - scipy is expected in the ppgl env.
    ndimage = None
    cKDTree = None


def ensure_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        Path(path).write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_image(path: str | Path) -> tuple[np.ndarray, nib.Nifti1Image]:
    img = nib.load(str(path))
    return np.asarray(img.dataobj, dtype=np.float32), img


def load_label(path: str | Path) -> tuple[np.ndarray, nib.Nifti1Image]:
    img = nib.load(str(path))
    arr = np.asarray(img.dataobj)
    return np.rint(arr).astype(np.uint8, copy=False), img


def save_image(path: str | Path, array: np.ndarray, affine: np.ndarray, like_img: nib.Nifti1Image) -> None:
    img = nib.Nifti1Image(np.asarray(array, dtype=np.float32), affine, header=like_img.header.copy())
    img.set_data_dtype(np.float32)
    nib.save(img, str(path))


def save_label(path: str | Path, array: np.ndarray, like_img: nib.Nifti1Image) -> None:
    img = nib.Nifti1Image(np.asarray(array, dtype=np.uint8), like_img.affine, header=like_img.header.copy())
    img.set_data_dtype(np.uint8)
    nib.save(img, str(path))


def translate_affine(affine: np.ndarray, start_xyz: tuple[int, int, int]) -> np.ndarray:
    transform = np.eye(4, dtype=np.float64)
    transform[:3, 3] = np.asarray(start_xyz, dtype=np.float64)
    return np.asarray(affine, dtype=np.float64) @ transform


def crop_with_padding(
    image: np.ndarray,
    center_xyz: tuple[float, float, float],
    roi_size: tuple[int, int, int],
    pad_value: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    shape = tuple(int(x) for x in image.shape[:3])
    size = tuple(int(x) for x in roi_size)
    start = tuple(int(round(float(center_xyz[i]) - size[i] / 2.0)) for i in range(3))
    end = tuple(start[i] + size[i] for i in range(3))
    src_start = tuple(max(0, start[i]) for i in range(3))
    src_end = tuple(min(shape[i], end[i]) for i in range(3))
    roi_start = tuple(src_start[i] - start[i] for i in range(3))
    roi_end = tuple(roi_start[i] + max(0, src_end[i] - src_start[i]) for i in range(3))

    crop = np.full(size, float(pad_value), dtype=np.float32)
    if all(src_end[i] > src_start[i] for i in range(3)):
        crop[
            roi_start[0] : roi_end[0],
            roi_start[1] : roi_end[1],
            roi_start[2] : roi_end[2],
        ] = image[
            src_start[0] : src_end[0],
            src_start[1] : src_end[1],
            src_start[2] : src_end[2],
        ]

    meta = {
        "crop_start_x": start[0],
        "crop_start_y": start[1],
        "crop_start_z": start[2],
        "crop_end_x": end[0],
        "crop_end_y": end[1],
        "crop_end_z": end[2],
        "src_start_x": src_start[0],
        "src_start_y": src_start[1],
        "src_start_z": src_start[2],
        "src_end_x": src_end[0],
        "src_end_y": src_end[1],
        "src_end_z": src_end[2],
        "roi_start_x": roi_start[0],
        "roi_start_y": roi_start[1],
        "roi_start_z": roi_start[2],
        "roi_end_x": roi_end[0],
        "roi_end_y": roi_end[1],
        "roi_end_z": roi_end[2],
        "padded": int(any(start[i] < 0 or end[i] > shape[i] for i in range(3))),
    }
    return crop, meta


def backproject_roi_mask(mask: np.ndarray, original_shape: tuple[int, int, int], meta: dict[str, Any]) -> np.ndarray:
    full = np.zeros(original_shape, dtype=bool)
    src_start = tuple(int(meta[f"src_start_{axis}"]) for axis in ("x", "y", "z"))
    src_end = tuple(int(meta[f"src_end_{axis}"]) for axis in ("x", "y", "z"))
    roi_start = tuple(int(meta[f"roi_start_{axis}"]) for axis in ("x", "y", "z"))
    roi_end = tuple(int(meta[f"roi_end_{axis}"]) for axis in ("x", "y", "z"))
    if all(src_end[i] > src_start[i] for i in range(3)):
        full[
            src_start[0] : src_end[0],
            src_start[1] : src_end[1],
            src_start[2] : src_end[2],
        ] = np.asarray(mask, dtype=bool)[
            roi_start[0] : roi_end[0],
            roi_start[1] : roi_end[1],
            roi_start[2] : roi_end[2],
        ]
    return full


def mask_centroid(mask: np.ndarray) -> tuple[float, float, float] | None:
    pts = np.argwhere(np.asarray(mask, dtype=bool))
    if pts.size == 0:
        return None
    return tuple(float(x) for x in pts.mean(axis=0))


def mask_bbox(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    pts = np.argwhere(np.asarray(mask, dtype=bool))
    if pts.size == 0:
        return None
    return pts.min(axis=0), pts.max(axis=0)


def connected_components_3d(mask: np.ndarray) -> tuple[np.ndarray, list[dict[str, Any]]]:
    mask_bool = np.asarray(mask, dtype=bool)
    if ndimage is not None:
        objects = ndimage.find_objects(mask_bool)
        labels = np.zeros(mask_bool.shape, dtype=np.int32)
        if not objects or objects[0] is None:
            return labels, []
        bbox = objects[0]
        bbox_lo = np.asarray([axis_slice.start for axis_slice in bbox], dtype=int)
        crop = mask_bool[bbox]
        crop_labels, n_comp = ndimage.label(crop, structure=ndimage.generate_binary_structure(3, 1))
        labels[bbox] = crop_labels.astype(np.int32, copy=False)
        foreground = np.argwhere(crop)
        component_ids = crop_labels[crop]
        comps: list[dict[str, Any]] = []
        for comp_id in range(1, int(n_comp) + 1):
            pts = foreground[component_ids == comp_id]
            if pts.size == 0:
                continue
            pts += bbox_lo.reshape(1, 3)
            centroid = pts.mean(axis=0)
            bbox_min = pts.min(axis=0)
            bbox_max = pts.max(axis=0)
            comps.append(
                {
                    "component_id": int(comp_id),
                    "voxel_count": int(pts.shape[0]),
                    "centroid_x": float(centroid[0]),
                    "centroid_y": float(centroid[1]),
                    "centroid_z": float(centroid[2]),
                    "bbox_min_x": int(bbox_min[0]),
                    "bbox_min_y": int(bbox_min[1]),
                    "bbox_min_z": int(bbox_min[2]),
                    "bbox_max_x": int(bbox_max[0]),
                    "bbox_max_y": int(bbox_max[1]),
                    "bbox_max_z": int(bbox_max[2]),
                }
            )
        comps.sort(key=lambda item: int(item["voxel_count"]), reverse=True)
        return labels, comps

    labels = np.zeros(mask_bool.shape, dtype=np.int32)
    foreground = np.argwhere(mask_bool)
    if foreground.size == 0:
        return labels, []

    current = 0
    comps: list[dict[str, Any]] = []
    shape = mask_bool.shape
    neighbor_offsets = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))

    for seed in foreground:
        sx, sy, sz = (int(seed[0]), int(seed[1]), int(seed[2]))
        if labels[sx, sy, sz] != 0:
            continue
        current += 1
        q: deque[tuple[int, int, int]] = deque([(sx, sy, sz)])
        labels[sx, sy, sz] = current
        count = 0
        sum_xyz = np.zeros(3, dtype=np.float64)
        min_xyz = np.asarray([sx, sy, sz], dtype=np.int64)
        max_xyz = np.asarray([sx, sy, sz], dtype=np.int64)
        while q:
            x, y, z = q.popleft()
            count += 1
            xyz = np.asarray([x, y, z], dtype=np.int64)
            sum_xyz += xyz
            min_xyz = np.minimum(min_xyz, xyz)
            max_xyz = np.maximum(max_xyz, xyz)
            for dx, dy, dz in neighbor_offsets:
                nx, ny, nz = x + dx, y + dy, z + dz
                if nx < 0 or ny < 0 or nz < 0 or nx >= shape[0] or ny >= shape[1] or nz >= shape[2]:
                    continue
                if mask_bool[nx, ny, nz] and labels[nx, ny, nz] == 0:
                    labels[nx, ny, nz] = current
                    q.append((nx, ny, nz))
        comps.append(
            {
                "component_id": current,
                "voxel_count": int(count),
                "centroid_x": float(sum_xyz[0] / count),
                "centroid_y": float(sum_xyz[1] / count),
                "centroid_z": float(sum_xyz[2] / count),
                "bbox_min_x": int(min_xyz[0]),
                "bbox_min_y": int(min_xyz[1]),
                "bbox_min_z": int(min_xyz[2]),
                "bbox_max_x": int(max_xyz[0]),
                "bbox_max_y": int(max_xyz[1]),
                "bbox_max_z": int(max_xyz[2]),
            }
        )
    comps.sort(key=lambda item: int(item["voxel_count"]), reverse=True)
    return labels, comps


def largest_component(mask: np.ndarray, min_voxels: int = 1) -> tuple[np.ndarray, dict[str, Any] | None]:
    labels, comps = connected_components_3d(mask)
    if not comps or int(comps[0]["voxel_count"]) < int(min_voxels):
        return np.zeros_like(mask, dtype=bool), None
    comp_id = int(comps[0]["component_id"])
    return labels == comp_id, comps[0]


def clean_specialist_mask(
    mask: np.ndarray,
    min_component_voxels: int,
    min_largest_component_voxels: int,
) -> tuple[bool, str, np.ndarray, dict[str, Any]]:
    mask_bool = np.asarray(mask, dtype=bool)
    raw_voxels = int(mask_bool.sum())
    if raw_voxels == 0:
        return False, "empty_prediction", mask_bool, {
            "raw_voxels": raw_voxels,
            "cleaned_voxels": 0,
            "cc_count": 0,
            "largest_cc_ratio": 0.0,
        }

    labels, comps = connected_components_3d(mask_bool)
    kept = np.zeros(mask_bool.shape, dtype=bool)
    for comp in comps:
        if int(comp["voxel_count"]) >= int(min_component_voxels):
            kept |= labels == int(comp["component_id"])
    cleaned_voxels = int(kept.sum())
    if cleaned_voxels == 0:
        return False, "all_components_removed", kept, {
            "raw_voxels": raw_voxels,
            "cleaned_voxels": 0,
            "cc_count": int(len(comps)),
            "largest_cc_ratio": 0.0,
        }

    _, kept_comps = connected_components_3d(kept)
    largest = int(kept_comps[0]["voxel_count"]) if kept_comps else 0
    largest_ratio = float(largest / cleaned_voxels) if cleaned_voxels else 0.0
    accepted = largest >= int(min_largest_component_voxels)
    reason = "" if accepted else "largest_component_too_small"
    return accepted, reason, kept, {
        "raw_voxels": raw_voxels,
        "cleaned_voxels": cleaned_voxels,
        "cc_count": int(len(kept_comps)),
        "largest_cc_ratio": largest_ratio,
    }


def binary_metrics(pred: np.ndarray, gt: np.ndarray) -> dict[str, float | int]:
    pred_bool = np.asarray(pred, dtype=bool)
    gt_bool = np.asarray(gt, dtype=bool)
    tp = int((pred_bool & gt_bool).sum())
    fp = int((pred_bool & ~gt_bool).sum())
    fn = int((~pred_bool & gt_bool).sum())
    pred_voxels = int(pred_bool.sum())
    gt_voxels = int(gt_bool.sum())
    denom_dice = 2 * tp + fp + fn
    denom_iou = tp + fp + fn
    dice = float(2 * tp / denom_dice) if denom_dice else 1.0
    iou = float(tp / denom_iou) if denom_iou else 1.0
    precision = float(tp / (tp + fp)) if (tp + fp) else (1.0 if gt_voxels == 0 else 0.0)
    recall = float(tp / (tp + fn)) if (tp + fn) else 1.0
    return {
        "dice": dice,
        "iou": iou,
        "precision": precision,
        "recall": recall,
        "pred_voxels": pred_voxels,
        "gt_voxels": gt_voxels,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def get_surface_mask_np(mask_np: np.ndarray) -> np.ndarray:
    mask_np = np.asarray(mask_np, dtype=bool)
    if not mask_np.any():
        return mask_np
    if ndimage is not None:
        structure = ndimage.generate_binary_structure(mask_np.ndim, 1)
        eroded = ndimage.binary_erosion(mask_np, structure=structure, border_value=0)
    else:
        padded = np.pad(mask_np, 1, mode="constant", constant_values=False)
        eroded = np.ones_like(mask_np, dtype=bool)
        sx, sy, sz = mask_np.shape
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
            eroded &= padded[1 + dx : 1 + dx + sx, 1 + dy : 1 + dy + sy, 1 + dz : 1 + dz + sz]
    surface = mask_np & (~eroded)
    return surface if surface.any() else mask_np.copy()


def compute_surface_metrics_np(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
    spacing_mm: tuple[float, float, float],
    tolerance_mm: float = 1.0,
) -> dict[str, float]:
    pred = np.asarray(pred_mask, dtype=bool)
    gt = np.asarray(gt_mask, dtype=bool)
    if pred.shape != gt.shape:
        raise ValueError(f"surface metric shape mismatch: pred={pred.shape}, gt={gt.shape}")

    pred_any = bool(pred.any())
    gt_any = bool(gt.any())
    if not pred_any and not gt_any:
        return {"nsd_1mm": 1.0, "hd95_mm": 0.0}
    if not pred_any or not gt_any:
        return {"nsd_1mm": 0.0, "hd95_mm": float("nan")}

    spacing = np.asarray(spacing_mm, dtype=np.float64).reshape(1, 3)
    pred_points = np.argwhere(get_surface_mask_np(pred)).astype(np.float64, copy=False) * spacing
    gt_points = np.argwhere(get_surface_mask_np(gt)).astype(np.float64, copy=False) * spacing
    if pred_points.size == 0 or gt_points.size == 0:
        return {"nsd_1mm": 0.0, "hd95_mm": float("nan")}

    if cKDTree is None:
        pred_distances = np.sqrt(((pred_points[:, None, :] - gt_points[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
        gt_distances = np.sqrt(((gt_points[:, None, :] - pred_points[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
    else:
        pred_tree = cKDTree(pred_points)
        gt_tree = cKDTree(gt_points)
        try:
            pred_distances, _ = gt_tree.query(pred_points, k=1, workers=-1)
            gt_distances, _ = pred_tree.query(gt_points, k=1, workers=-1)
        except TypeError:
            pred_distances, _ = gt_tree.query(pred_points, k=1)
            gt_distances, _ = pred_tree.query(gt_points, k=1)

    total_surface = int(pred_distances.size + gt_distances.size)
    nsd = (
        int(np.count_nonzero(pred_distances <= float(tolerance_mm)))
        + int(np.count_nonzero(gt_distances <= float(tolerance_mm)))
    ) / float(max(total_surface, 1))
    hd95 = float(np.percentile(np.concatenate([pred_distances, gt_distances]), 95.0))
    return {"nsd_1mm": float(nsd), "hd95_mm": hd95}


def prefix_metrics(prefix: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}
