from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict, deque
from datetime import datetime
from typing import Dict, List

import numpy as np
import torch
import nibabel as nib
from nibabel.processing import resample_from_to
from monai.data import CacheDataset, DataLoader, Dataset
from monai.inferers import sliding_window_inference
from tqdm import tqdm

from Dataloader_mutil import build_val_transforms, parse_data_list
from exp_config import load_experiment_config
from gcp_unet import build_unet_model

DEFAULT_PARTIAL_ORGAN_NAMES = (
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


def normalize_case_id(case_name) -> str:
    case_id = str(case_name)
    case_id = os.path.basename(case_id)
    if case_id.endswith(".nii.gz"):
        return case_id[:-7]
    if case_id.endswith(".nii"):
        return case_id[:-4]
    return case_id


def resolve_state_dict(checkpoint_obj):
    if isinstance(checkpoint_obj, dict):
        for key in ("state_dict", "model_state_dict"):
            value = checkpoint_obj.get(key)
            if isinstance(value, dict):
                return value
    if isinstance(checkpoint_obj, dict):
        return checkpoint_obj
    raise ValueError("Unsupported checkpoint format. Expect state_dict or dict containing state_dict.")


def load_state_dict_allow_adrenal_aux(model, state_dict):
    model_keys = set(model.state_dict().keys())
    extra_keys = sorted(k for k in state_dict.keys() if k not in model_keys)
    bad_extra = [k for k in extra_keys if not k.startswith("adrenal_aux_head.")]
    if bad_extra:
        raise RuntimeError(f"checkpoint 包含非 adrenal aux 的多余参数: {bad_extra[:10]}")

    filtered_state = {k: v for k, v in state_dict.items() if k in model_keys}
    missing_keys = sorted(k for k in model_keys if k not in filtered_state)
    if missing_keys:
        raise RuntimeError(f"checkpoint 缺少模型参数: {missing_keys[:10]}")
    return model.load_state_dict(filtered_state, strict=True)


def load_checkpoint_object(checkpoint_path, runtime_device):
    try:
        return torch.load(checkpoint_path, map_location=runtime_device, weights_only=True)
    except TypeError:
        return torch.load(checkpoint_path, map_location=runtime_device)


def resolve_runtime_device(requested_device: str) -> str:
    requested = str(requested_device).strip()
    if requested.startswith("cuda"):
        if torch.cuda.is_available():
            return requested
        raise RuntimeError(
            f"CUDA device {requested!r} was requested, but this PyTorch runtime cannot use CUDA. "
            "Install a Jetson CUDA-enabled PyTorch build or run with --device cpu."
        )
    return "cpu"


def safe_mean(values: List[float]):
    if not values:
        return None
    return float(np.mean(values))


def _str2bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def compute_binary_metrics(pred_mask: torch.Tensor, gt_mask: torch.Tensor) -> Dict[str, float]:
    pred_bool = pred_mask.bool()
    gt_bool = gt_mask.bool()

    tp = int((pred_bool & gt_bool).sum().item())
    pred_voxels = int(pred_bool.sum().item())
    gt_voxels = int(gt_bool.sum().item())

    eps = 1e-5
    dice = (2.0 * tp + eps) / (pred_voxels + gt_voxels + eps)
    iou = (tp + eps) / (pred_voxels + gt_voxels - tp + eps)

    if pred_voxels == 0 and gt_voxels == 0:
        precision = 1.0
        recall = 1.0
        f1 = 1.0
    else:
        precision = tp / pred_voxels if pred_voxels > 0 else 0.0
        recall = tp / gt_voxels if gt_voxels > 0 else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "dice": float(dice),
        "iou": float(iou),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "tp_voxels": int(tp),
        "pred_voxels": int(pred_voxels),
        "gt_voxels": int(gt_voxels),
    }


def to_metric_key(name: str) -> str:
    key = re.sub(r"[^0-9a-zA-Z_]+", "_", name.strip().lower())
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "class"


def build_class_metas(num_classes: int, tumor_label: int, class_names_csv: str):
    fg_labels = list(range(1, num_classes))

    provided_names = []
    if class_names_csv:
        provided_names = [x.strip() for x in class_names_csv.split(",") if x.strip()]
        if len(provided_names) != len(fg_labels):
            raise ValueError(
                f"--class-names 提供了 {len(provided_names)} 个名称，但前景类别数为 {len(fg_labels)}。"
            )

    class_metas = []
    used_keys = set()
    for idx, label_id in enumerate(fg_labels):
        if provided_names:
            display_name = provided_names[idx]
        elif label_id == tumor_label:
            display_name = "tumor"
        else:
            display_name = f"organ_{label_id}"

        metric_key = to_metric_key(display_name)
        if metric_key in used_keys:
            metric_key = f"{metric_key}_label{label_id}"
        used_keys.add(metric_key)

        class_metas.append(
            {
                "label_id": int(label_id),
                "display_name": display_name,
                "metric_key": metric_key,
                "class_type": "tumor" if label_id == tumor_label else "organ",
            }
        )
    return class_metas


def prepare_output_paths(output_root: str, run_name: str):
    run_dir = os.path.join(output_root, run_name)
    os.makedirs(run_dir, exist_ok=True)
    return {
        "run_dir": run_dir,
        "case_csv": os.path.join(run_dir, "case_metrics.csv"),
        "class_csv": os.path.join(run_dir, "class_summary.csv"),
        "summary_json": os.path.join(run_dir, "summary.json"),
        "failed_csv": os.path.join(run_dir, "failed_cases.csv"),
        "run_config_json": os.path.join(run_dir, "run_config.json"),
        "overlay_dir": os.path.join(run_dir, "prediction_overlays"),
        "nifti_label_dir": os.path.join(run_dir, "prediction_labels_nii"),
    }


def write_csv(rows: List[Dict], path: str, fieldnames: List[str]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def append_index_row(path: str, row: Dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    exists = os.path.exists(path)
    fieldnames = list(row.keys())
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _sanitize_token(text: str) -> str:
    token = re.sub(r"[^0-9a-zA-Z._-]+", "-", str(text).strip())
    token = re.sub(r"-+", "-", token).strip("-")
    return token or "na"


def build_eval_run_name(args, checkpoint_stem: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag = _sanitize_token(args.tag) if getattr(args, "tag", "").strip() else ""
    parts = [
        ts,
        "eval",
        _sanitize_token(args.split),
        _sanitize_token(args.exp_name),
        _sanitize_token(args.center),
        _sanitize_token(checkpoint_stem),
    ]
    if tag:
        parts.insert(2, tag)
    return "__".join(parts)


def resolve_default_checkpoint(script_dir: str, center: str, exp_name: str):
    candidates = []
    if exp_name:
        candidates.append(os.path.join(script_dir, "outputs", "ckpts", f"model{center}_{exp_name}.pth"))
        candidates.append(os.path.join(script_dir, "test_segment", "checkpoint", f"model{center}_{exp_name}.pth"))
    candidates.append(os.path.join(script_dir, "outputs", "ckpts", f"model{center}.pth"))

    for ckpt in candidates:
        if os.path.exists(ckpt):
            return ckpt
    raise FileNotFoundError(
        "未找到默认 checkpoint。请通过 --checkpoint 显式传入，"
        "或确保 outputs/ckpts 或 test_segment/checkpoint 下存在对应模型文件。"
    )


def build_partial_class_names(class_names_csv: str, num_channels: int):
    if class_names_csv:
        names = [x.strip() for x in class_names_csv.split(",") if x.strip()]
        if len(names) != num_channels:
            raise ValueError(f"--class-names 提供了 {len(names)} 个名称，但 partial-label channel 数为 {num_channels}")
        return names
    if num_channels == len(DEFAULT_PARTIAL_ORGAN_NAMES):
        return list(DEFAULT_PARTIAL_ORGAN_NAMES)
    return [f"organ_{idx + 1}" for idx in range(num_channels)]


def select_round_robin_cases(data_list: List[Dict], max_cases: int):
    if max_cases <= 0 or len(data_list) <= max_cases:
        return list(data_list)

    buckets: dict[str, deque] = defaultdict(deque)
    for item in data_list:
        dataset = str(item.get("dataset", "unknown"))
        buckets[dataset].append(item)

    selected: list[dict] = []
    while len(selected) < max_cases:
        progressed = False
        for dataset in sorted(buckets.keys()):
            if not buckets[dataset]:
                continue
            selected.append(buckets[dataset].popleft())
            progressed = True
            if len(selected) >= max_cases:
                break
        if not progressed:
            break
    return selected


def extract_case_dataset(batch, fallback="unknown") -> str:
    dataset_value = batch.get("dataset", fallback)
    if isinstance(dataset_value, (list, tuple)):
        return str(dataset_value[0])
    return str(dataset_value)


def make_overlay_png(
    image_3d: np.ndarray,
    pred_4d: np.ndarray,
    gt_4d: np.ndarray,
    valid_labels: np.ndarray,
    organ_names: List[str],
    output_path: str,
):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    image_3d = np.asarray(image_3d, dtype=np.float32)
    pred_4d = np.asarray(pred_4d, dtype=np.uint8)
    gt_4d = np.asarray(gt_4d, dtype=np.uint8)
    valid_labels = np.asarray(valid_labels, dtype=np.uint8).reshape(-1)

    valid_idx = [idx for idx, flag in enumerate(valid_labels.tolist()) if int(flag) == 1]
    union = np.zeros(gt_4d.shape[1:], dtype=bool)
    for idx in valid_idx:
        union |= gt_4d[idx].astype(bool)
        union |= pred_4d[idx].astype(bool)

    if union.any():
        coords = np.argwhere(union)
        z_idx = int(np.median(coords[:, 0]))
        y_idx = int(np.median(coords[:, 1]))
        x_idx = int(np.median(coords[:, 2]))
    else:
        z_idx = image_3d.shape[0] // 2
        y_idx = image_3d.shape[1] // 2
        x_idx = image_3d.shape[2] // 2

    planes = [
        ("axial", image_3d[z_idx], gt_4d[:, z_idx], pred_4d[:, z_idx]),
        ("coronal", image_3d[:, y_idx, :], gt_4d[:, :, y_idx, :], pred_4d[:, :, y_idx, :]),
        ("sagittal", image_3d[:, :, x_idx], gt_4d[:, :, :, x_idx], pred_4d[:, :, :, x_idx]),
    ]
    colors = plt.get_cmap("tab10")(np.linspace(0.0, 1.0, max(10, len(organ_names))))[:, :3]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), dpi=160)
    for ax, (view_name, image_2d, gt_stack, pred_stack) in zip(axes, planes):
        ax.imshow(image_2d, cmap="gray")
        for organ_idx in valid_idx:
            color = colors[organ_idx % len(colors)]
            gt_mask = np.asarray(gt_stack[organ_idx] > 0, dtype=np.uint8)
            pred_mask = np.asarray(pred_stack[organ_idx] > 0, dtype=np.uint8)
            if gt_mask.any():
                overlay = np.zeros((*gt_mask.shape, 4), dtype=np.float32)
                overlay[..., :3] = color
                overlay[..., 3] = gt_mask * 0.25
                ax.imshow(overlay)
            if pred_mask.any():
                ax.contour(pred_mask.astype(np.float32), levels=[0.5], colors=[color], linewidths=0.8)
        ax.set_title(view_name)
        ax.axis("off")

    legend_items = [organ_names[idx] for idx in valid_idx[:9]]
    if legend_items:
        fig.suptitle("GT fill + Pred contour | " + ", ".join(legend_items), fontsize=10)
    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def _unwrap_meta_value(value):
    if isinstance(value, (list, tuple)) and value:
        return _unwrap_meta_value(value[0])
    if isinstance(value, np.ndarray):
        if value.shape == ():
            return value.item()
        if value.size > 0:
            return _unwrap_meta_value(value.reshape(-1)[0])
    return value


def _image_filename_from_item(item) -> str:
    image = item.get("image")
    if hasattr(image, "meta") and isinstance(image.meta, dict):
        filename = _unwrap_meta_value(image.meta.get("filename_or_obj"))
        if filename:
            return str(filename)

    meta_dict = item.get("image_meta_dict", {})
    if isinstance(meta_dict, dict):
        filename = _unwrap_meta_value(meta_dict.get("filename_or_obj"))
        if filename:
            return str(filename)

    raise ValueError("无法从 image metadata 取得原始影像路径，不能保存对齐原图的 nii.gz 标签。")


def _first_affine(value):
    if value is None:
        return None
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    affine = np.asarray(value, dtype=np.float64)
    while affine.ndim > 2:
        affine = affine[0]
    if affine.shape != (4, 4):
        return None
    return affine


def _image_current_affine(batch) -> np.ndarray:
    image = batch.get("image")
    if hasattr(image, "meta") and isinstance(image.meta, dict):
        affine = _first_affine(image.meta.get("affine"))
        if affine is not None:
            return affine

    meta_dict = batch.get("image_meta_dict", {})
    if isinstance(meta_dict, dict):
        affine = _first_affine(meta_dict.get("affine"))
        if affine is not None:
            return affine

    raise ValueError("无法从 image metadata 取得当前 affine，不能保存对齐原图的 nii.gz 标签。")


def _as_numpy_array(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "numpy"):
        return value.numpy()
    return np.asarray(value)


def save_prediction_label_nifti(batch, pred_cls: torch.Tensor, output_dir: str, case_id: str, postfix: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    pred_np = _as_numpy_array(pred_cls)
    while pred_np.ndim > 3 and pred_np.shape[0] == 1:
        pred_np = pred_np[0]
    if pred_np.ndim != 3:
        raise ValueError(f"预测标签维度非法: shape={tuple(pred_np.shape)}")

    pred_np = np.rint(pred_np).astype(np.uint8, copy=False)
    reference_path = _image_filename_from_item(batch)
    reference_img = nib.load(reference_path)
    current_affine = _image_current_affine(batch)
    pred_img = nib.Nifti1Image(pred_np, current_affine)
    pred_img = resample_from_to(pred_img, (reference_img.shape[:3], reference_img.affine), order=0)
    pred_np = np.rint(np.asarray(pred_img.dataobj)).astype(np.uint8, copy=False)

    output_path = os.path.join(output_dir, f"{case_id}_{postfix}.nii.gz")
    header = reference_img.header.copy()
    header.set_data_dtype(np.uint8)
    nib.save(nib.Nifti1Image(pred_np, reference_img.affine, header=header), output_path)
    return output_path


def build_args():
    cfg = load_experiment_config()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(
        description="GCPV4 multi-class test script: evaluate tumor and each organ class."
    )
    parser.add_argument("--center", type=str, default=cfg.center)
    parser.add_argument("--split", type=str, default="test", choices=["val", "test"])
    parser.add_argument("--exp-name", type=str, default=cfg.exp_name)
    parser.add_argument("--data-root", type=str, default=cfg.data_root)
    parser.add_argument("--data-list-root", type=str, default=cfg.data_list_root)
    parser.add_argument("--image-folder", type=str, default=cfg.image_folder)
    parser.add_argument("--label-folder", type=str, default=cfg.label_folder)
    parser.add_argument("--checkpoint", type=str, default="")
    parser.add_argument("--num-classes", type=int, default=cfg.num_classes)
    parser.add_argument("--tumor-label", type=int, default=cfg.tumor_label)
    parser.add_argument("--class-names", type=str, default="")
    parser.add_argument("--roi-size", type=int, default=cfg.val_roi_size)
    parser.add_argument("--sw-batch-size", type=int, default=cfg.sw_batch_size)
    parser.add_argument("--overlap", type=float, default=cfg.val_overlap)
    parser.add_argument("--fg-margin", type=int, default=cfg.fg_margin)
    parser.add_argument("--cache-rate", type=float, default=0.0)
    parser.add_argument("--num-workers", type=int, default=max(0, cfg.num_workers // 2))
    parser.add_argument("--device", type=str, default=cfg.device)
    parser.add_argument("--seed", type=int, default=cfg.seed)
    parser.add_argument("--output-root", type=str, default=os.path.join(script_dir, "outputs", "test_eval"))
    parser.add_argument("--run-name", type=str, default="")
    parser.add_argument("--tag", type=str, default="")
    parser.add_argument("--sigmoid-multilabel", action="store_true", default=_str2bool(os.getenv("SIGMOID_MULTILABEL")))
    parser.add_argument("--prob-threshold", type=float, default=0.5)
    parser.add_argument("--overlay-max-cases", type=int, default=0)
    parser.add_argument("--save-nifti-labels", action="store_true")
    parser.add_argument("--nifti-output-dir", type=str, default="")
    parser.add_argument("--nifti-postfix", type=str, default="pred")

    args = parser.parse_args()
    if args.num_classes < 1:
        raise ValueError("num_classes 必须 >= 1")
    if (not args.sigmoid_multilabel) and not (1 <= args.tumor_label < args.num_classes):
        raise ValueError(
            f"tumor_label={args.tumor_label} 非法，必须满足 1 <= tumor_label < num_classes({args.num_classes})"
        )
    if not (0.0 <= args.overlap < 1.0):
        raise ValueError("overlap 必须在 [0,1) 区间")
    if args.cache_rate < 0.0 or args.cache_rate > 1.0:
        raise ValueError("cache_rate 必须在 [0,1] 区间")
    if not (0.0 < args.prob_threshold < 1.0):
        raise ValueError("prob_threshold 必须在 (0,1) 区间")
    if args.nifti_postfix.strip() == "":
        raise ValueError("nifti_postfix 不能为空")

    if not args.checkpoint:
        args.checkpoint = resolve_default_checkpoint(script_dir, args.center, args.exp_name)

    return args


def run_partial_test(args):
    if args.seed is not None:
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(args.seed)

    runtime_device = resolve_runtime_device(args.device)
    organ_names = build_partial_class_names(args.class_names, args.num_classes)

    split_txt = os.path.join(args.data_list_root, args.center, f"{args.split}.jsonl")
    test_files = parse_data_list(
        split_txt,
        args.data_root,
        image_folder=args.image_folder,
        label_folder=args.label_folder,
    )
    if len(test_files) == 0:
        raise ValueError(f"测试集为空，请检查: {split_txt}, data_root={args.data_root}")

    transforms = build_val_transforms(
        val_roi_size=args.roi_size,
        fg_margin=args.fg_margin,
        partial_label_mode=True,
    )
    if args.cache_rate > 0:
        dataset = CacheDataset(
            data=test_files,
            transform=transforms,
            cache_rate=args.cache_rate,
            num_workers=max(1, args.num_workers),
            copy_cache=False,
        )
    else:
        dataset = Dataset(data=test_files, transform=transforms)

    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
    )

    model = build_unet_model(use_gcp=False, out_channels=args.num_classes).to(runtime_device)
    checkpoint_obj = load_checkpoint_object(args.checkpoint, runtime_device)
    state_dict = resolve_state_dict(checkpoint_obj)
    load_state_dict_allow_adrenal_aux(model, state_dict)
    model.eval()

    checkpoint_stem = os.path.splitext(os.path.basename(args.checkpoint))[0]
    default_run_name = build_eval_run_name(args, checkpoint_stem)
    run_name = args.run_name.strip() if args.run_name.strip() else default_run_name
    paths = prepare_output_paths(args.output_root, run_name)

    selected_overlay_items = select_round_robin_cases(test_files, args.overlay_max_cases)
    overlay_case_ids = {normalize_case_id(item.get("name", item.get("case_id", ""))) for item in selected_overlay_items}
    overlay_paths = []

    run_config = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "run_name": run_name,
        "tag": args.tag,
        "argv": sys.argv,
        "args": vars(args),
        "checkpoint_stem": checkpoint_stem,
        "output_paths": paths,
        "partial_label_mode": True,
        "organ_names": organ_names,
    }
    with open(paths["run_config_json"], "w", encoding="utf-8") as f:
        json.dump(run_config, f, ensure_ascii=False, indent=2)

    case_rows = []
    failed_rows = []
    organ_records = {organ_name: [] for organ_name in organ_names}
    organ_valid_case_counts = {organ_name: 0 for organ_name in organ_names}
    organ_nonempty_pred_counts = {organ_name: 0 for organ_name in organ_names}

    with torch.no_grad():
        progress = tqdm(loader, desc="Test(partial-label)", ncols=120)
        for batch in progress:
            case_name = batch.get("name", ["Unknown"])[0]
            case_id = normalize_case_id(case_name)
            dataset_name = extract_case_dataset(batch)

            try:
                images = batch["image"].to(runtime_device)
                labels = batch["label"].to(runtime_device).float()
                valid_labels = batch["valid_labels"].to(runtime_device).float()

                if labels.ndim != 5 or int(labels.shape[1]) != args.num_classes:
                    raise ValueError(
                        f"partial-label GT 形状非法: expected [B,{args.num_classes},D,H,W], got={tuple(labels.shape)}"
                    )
                if valid_labels.ndim != 2 or int(valid_labels.shape[1]) != args.num_classes:
                    raise ValueError(
                        f"partial-label valid_labels 形状非法: expected [B,{args.num_classes}], got={tuple(valid_labels.shape)}"
                    )

                logits = sliding_window_inference(
                    inputs=images,
                    roi_size=(args.roi_size, args.roi_size, args.roi_size),
                    sw_batch_size=args.sw_batch_size,
                    predictor=model,
                    overlap=args.overlap,
                    mode="gaussian",
                    sw_device=runtime_device,
                )
                probs = torch.sigmoid(logits)
                pred_mask = (probs >= args.prob_threshold).float()

                case_row = {"case_id": case_id, "dataset": dataset_name}
                visible_pred = False

                for organ_idx, organ_name in enumerate(organ_names):
                    is_valid = int(valid_labels[0, organ_idx].item()) == 1
                    case_row[f"valid_{organ_name}"] = int(is_valid)
                    if not is_valid:
                        continue

                    metrics = compute_binary_metrics(pred_mask[:, organ_idx], labels[:, organ_idx])
                    organ_records[organ_name].append(metrics)
                    organ_valid_case_counts[organ_name] += 1
                    if metrics["pred_voxels"] > 0:
                        organ_nonempty_pred_counts[organ_name] += 1
                        visible_pred = True

                    case_row[f"dice_{organ_name}"] = metrics["dice"]
                    case_row[f"iou_{organ_name}"] = metrics["iou"]
                    case_row[f"precision_{organ_name}"] = metrics["precision"]
                    case_row[f"recall_{organ_name}"] = metrics["recall"]
                    case_row[f"f1_{organ_name}"] = metrics["f1"]
                    case_row[f"pred_voxels_{organ_name}"] = metrics["pred_voxels"]
                    case_row[f"gt_voxels_{organ_name}"] = metrics["gt_voxels"]

                case_rows.append(case_row)

                if case_id in overlay_case_ids and len(overlay_paths) < int(args.overlay_max_cases):
                    overlay_path = os.path.join(paths["overlay_dir"], f"{case_id}.png")
                    make_overlay_png(
                        image_3d=images[0, 0].detach().cpu().numpy(),
                        pred_4d=pred_mask[0].detach().cpu().numpy().astype(np.uint8),
                        gt_4d=labels[0].detach().cpu().numpy().astype(np.uint8),
                        valid_labels=valid_labels[0].detach().cpu().numpy().astype(np.uint8),
                        organ_names=organ_names,
                        output_path=overlay_path,
                    )
                    overlay_paths.append(overlay_path)

                progress.set_postfix({"ID": case_id, "pred": int(visible_pred)})

            except Exception as exc:
                failed_rows.append(
                    {
                        "case_id": case_id,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

    case_fields = ["case_id", "dataset"]
    for organ_name in organ_names:
        case_fields.extend(
            [
                f"valid_{organ_name}",
                f"dice_{organ_name}",
                f"iou_{organ_name}",
                f"precision_{organ_name}",
                f"recall_{organ_name}",
                f"f1_{organ_name}",
                f"pred_voxels_{organ_name}",
                f"gt_voxels_{organ_name}",
            ]
        )
    write_csv(case_rows, paths["case_csv"], case_fields)

    failed_fields = ["case_id", "error_type", "error_message"]
    write_csv(failed_rows, paths["failed_csv"], failed_fields)

    class_rows = []
    for organ_idx, organ_name in enumerate(organ_names):
        records = organ_records[organ_name]
        class_rows.append(
            {
                "channel_index": organ_idx,
                "organ_name": organ_name,
                "valid_case_count": int(organ_valid_case_counts[organ_name]),
                "nonempty_pred_case_count": int(organ_nonempty_pred_counts[organ_name]),
                "mean_dice_valid_cases": safe_mean([r["dice"] for r in records]),
                "mean_iou_valid_cases": safe_mean([r["iou"] for r in records]),
                "mean_precision_valid_cases": safe_mean([r["precision"] for r in records]),
                "mean_recall_valid_cases": safe_mean([r["recall"] for r in records]),
                "mean_f1_valid_cases": safe_mean([r["f1"] for r in records]),
                "mean_gt_voxels_valid_cases": safe_mean([r["gt_voxels"] for r in records]),
                "mean_pred_voxels_valid_cases": safe_mean([r["pred_voxels"] for r in records]),
            }
        )

    class_fields = [
        "channel_index",
        "organ_name",
        "valid_case_count",
        "nonempty_pred_case_count",
        "mean_dice_valid_cases",
        "mean_iou_valid_cases",
        "mean_precision_valid_cases",
        "mean_recall_valid_cases",
        "mean_f1_valid_cases",
        "mean_gt_voxels_valid_cases",
        "mean_pred_voxels_valid_cases",
    ]
    write_csv(class_rows, paths["class_csv"], class_fields)

    macro_valid_organ_dice = safe_mean(
        [row["mean_dice_valid_cases"] for row in class_rows if row["mean_dice_valid_cases"] is not None]
    )

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "center": args.center,
        "split": args.split,
        "exp_name": args.exp_name,
        "checkpoint": args.checkpoint,
        "runtime_device": runtime_device,
        "num_channels": args.num_classes,
        "partial_label_mode": True,
        "organ_names": organ_names,
        "num_total_cases": len(test_files),
        "num_scored_cases": len(case_rows),
        "num_failed_cases": len(failed_rows),
        "macro_valid_organ_dice": macro_valid_organ_dice,
        "outputs": paths,
        "overlay_paths": overlay_paths,
    }
    with open(paths["summary_json"], "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    append_index_row(
        os.path.join(args.output_root, "eval_index.csv"),
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "run_name": run_name,
            "tag": args.tag,
            "center": args.center,
            "split": args.split,
            "exp_name": args.exp_name,
            "checkpoint": args.checkpoint,
            "num_classes": args.num_classes,
            "partial_label_mode": True,
            "num_total_cases": len(test_files),
            "num_scored_cases": len(case_rows),
            "num_failed_cases": len(failed_rows),
            "macro_valid_organ_dice": macro_valid_organ_dice,
            "run_dir": paths["run_dir"],
            "summary_json": paths["summary_json"],
            "run_config_json": paths["run_config_json"],
        },
    )

    print("\n------ Test Summary (Partial-label Organs) ------")
    print(f"Scored cases: {len(case_rows)}")
    print(f"Failed cases: {len(failed_rows)}")
    print(f"macro_valid_organ_dice: {macro_valid_organ_dice}")
    for row in class_rows:
        print(
            f"[organ] ch={row['channel_index']} {row['organ_name']}: "
            f"valid_cases={row['valid_case_count']}, "
            f"Dice={row['mean_dice_valid_cases']}, "
            f"nonempty_pred_cases={row['nonempty_pred_case_count']}"
        )
    print("-----------------------------------------------")
    print(f"Case metrics : {paths['case_csv']}")
    print(f"Class summary: {paths['class_csv']}")
    print(f"Summary json : {paths['summary_json']}")
    if overlay_paths:
        print(f"Overlays     : {paths['overlay_dir']}")


def run_test(args):
    if args.sigmoid_multilabel:
        if args.save_nifti_labels:
            raise NotImplementedError("--save-nifti-labels 当前只支持多类 softmax 推理，不支持 sigmoid-multilabel。")
        return run_partial_test(args)

    if args.seed is not None:
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(args.seed)

    runtime_device = resolve_runtime_device(args.device)
    class_metas = build_class_metas(args.num_classes, args.tumor_label, args.class_names)

    split_txt = os.path.join(args.data_list_root, args.center, args.split)
    test_files = parse_data_list(
        split_txt,
        args.data_root,
        image_folder=args.image_folder,
        label_folder=args.label_folder,
    )
    if len(test_files) == 0:
        raise ValueError(f"测试集为空，请检查: {split_txt}, data_root={args.data_root}")

    transforms = build_val_transforms(val_roi_size=args.roi_size, fg_margin=args.fg_margin)
    if args.cache_rate > 0:
        dataset = CacheDataset(
            data=test_files,
            transform=transforms,
            cache_rate=args.cache_rate,
            num_workers=max(1, args.num_workers),
            copy_cache=False,
        )
    else:
        dataset = Dataset(data=test_files, transform=transforms)

    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
    )

    model = build_unet_model(use_gcp=False, out_channels=args.num_classes).to(runtime_device)
    checkpoint_obj = load_checkpoint_object(args.checkpoint, runtime_device)
    state_dict = resolve_state_dict(checkpoint_obj)
    load_state_dict_allow_adrenal_aux(model, state_dict)
    model.eval()

    checkpoint_stem = os.path.splitext(os.path.basename(args.checkpoint))[0]
    default_run_name = build_eval_run_name(args, checkpoint_stem)
    run_name = args.run_name.strip() if args.run_name.strip() else default_run_name
    paths = prepare_output_paths(args.output_root, run_name)
    if args.nifti_output_dir.strip():
        paths["nifti_label_dir"] = os.path.abspath(args.nifti_output_dir.strip())

    run_config = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "run_name": run_name,
        "tag": args.tag,
        "argv": sys.argv,
        "args": vars(args),
        "checkpoint_stem": checkpoint_stem,
        "output_paths": paths,
    }
    with open(paths["run_config_json"], "w", encoding="utf-8") as f:
        json.dump(run_config, f, ensure_ascii=False, indent=2)

    case_rows = []
    failed_rows = []
    class_records = {meta["label_id"]: [] for meta in class_metas}
    nifti_label_paths = []

    with torch.no_grad():
        progress = tqdm(loader, desc="Test", ncols=120)
        for batch in progress:
            case_name = batch.get("name", ["Unknown"])[0]
            case_id = normalize_case_id(case_name)

            try:
                images = batch["image"].to(runtime_device)
                labels = batch["label"].to(runtime_device).long()
                gt_cls = labels.squeeze(1) if labels.ndim == 5 else labels

                gt_min = int(gt_cls.min().item())
                gt_max = int(gt_cls.max().item())
                if gt_min < 0 or gt_max >= args.num_classes:
                    raise ValueError(
                        f"GT 标签越界: min={gt_min}, max={gt_max}, num_classes={args.num_classes}"
                    )

                logits = sliding_window_inference(
                    inputs=images,
                    roi_size=(args.roi_size, args.roi_size, args.roi_size),
                    sw_batch_size=args.sw_batch_size,
                    predictor=model,
                    overlap=args.overlap,
                    mode="gaussian",
                    sw_device=runtime_device,
                )
                pred_cls = torch.argmax(logits, dim=1).long()

                case_row = {"case_id": case_id}
                tumor_dice_for_bar = None

                for meta in class_metas:
                    label_id = meta["label_id"]
                    key = meta["metric_key"]
                    pred_mask = pred_cls == label_id
                    gt_mask = gt_cls == label_id
                    metrics = compute_binary_metrics(pred_mask, gt_mask)
                    class_records[label_id].append(metrics)

                    case_row[f"dice_{key}"] = metrics["dice"]
                    case_row[f"iou_{key}"] = metrics["iou"]
                    case_row[f"precision_{key}"] = metrics["precision"]
                    case_row[f"recall_{key}"] = metrics["recall"]
                    case_row[f"f1_{key}"] = metrics["f1"]
                    case_row[f"tp_voxels_{key}"] = metrics["tp_voxels"]
                    case_row[f"pred_voxels_{key}"] = metrics["pred_voxels"]
                    case_row[f"gt_voxels_{key}"] = metrics["gt_voxels"]

                    if label_id == args.tumor_label:
                        tumor_dice_for_bar = metrics["dice"]

                if args.save_nifti_labels:
                    saved_label_path = save_prediction_label_nifti(
                        batch=batch,
                        pred_cls=pred_cls,
                        output_dir=paths["nifti_label_dir"],
                        case_id=case_id,
                        postfix=args.nifti_postfix.strip(),
                    )
                    case_row["pred_nifti"] = saved_label_path
                    nifti_label_paths.append(saved_label_path)

                case_rows.append(case_row)
                if tumor_dice_for_bar is not None:
                    progress.set_postfix({"ID": case_id, "Dice_tumor": f"{tumor_dice_for_bar:.4f}"})
                else:
                    progress.set_postfix({"ID": case_id})

            except Exception as exc:
                failed_rows.append(
                    {
                        "case_id": case_id,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )

    case_fields = ["case_id"]
    if args.save_nifti_labels:
        case_fields.append("pred_nifti")
    for meta in class_metas:
        key = meta["metric_key"]
        case_fields.extend(
            [
                f"dice_{key}",
                f"iou_{key}",
                f"precision_{key}",
                f"recall_{key}",
                f"f1_{key}",
                f"tp_voxels_{key}",
                f"pred_voxels_{key}",
                f"gt_voxels_{key}",
            ]
        )
    write_csv(case_rows, paths["case_csv"], case_fields)

    failed_fields = ["case_id", "error_type", "error_message"]
    write_csv(failed_rows, paths["failed_csv"], failed_fields)

    class_rows = []
    for meta in class_metas:
        label_id = meta["label_id"]
        records = class_records[label_id]
        present_records = [r for r in records if r["gt_voxels"] > 0]

        class_rows.append(
            {
                "label_id": label_id,
                "class_name": meta["display_name"],
                "class_type": meta["class_type"],
                "num_cases": len(records),
                "num_gt_present_cases": len(present_records),
                "mean_dice_all_cases": safe_mean([r["dice"] for r in records]),
                "mean_iou_all_cases": safe_mean([r["iou"] for r in records]),
                "mean_precision_all_cases": safe_mean([r["precision"] for r in records]),
                "mean_recall_all_cases": safe_mean([r["recall"] for r in records]),
                "mean_f1_all_cases": safe_mean([r["f1"] for r in records]),
                "mean_dice_gt_present": safe_mean([r["dice"] for r in present_records]),
                "mean_iou_gt_present": safe_mean([r["iou"] for r in present_records]),
                "mean_gt_voxels": safe_mean([r["gt_voxels"] for r in records]),
                "mean_pred_voxels": safe_mean([r["pred_voxels"] for r in records]),
            }
        )

    class_fields = [
        "label_id",
        "class_name",
        "class_type",
        "num_cases",
        "num_gt_present_cases",
        "mean_dice_all_cases",
        "mean_iou_all_cases",
        "mean_precision_all_cases",
        "mean_recall_all_cases",
        "mean_f1_all_cases",
        "mean_dice_gt_present",
        "mean_iou_gt_present",
        "mean_gt_voxels",
        "mean_pred_voxels",
    ]
    write_csv(class_rows, paths["class_csv"], class_fields)

    macro_dice_all = safe_mean([r["mean_dice_all_cases"] for r in class_rows if r["mean_dice_all_cases"] is not None])
    macro_iou_all = safe_mean([r["mean_iou_all_cases"] for r in class_rows if r["mean_iou_all_cases"] is not None])
    macro_dice_present = safe_mean([r["mean_dice_gt_present"] for r in class_rows if r["mean_dice_gt_present"] is not None])
    macro_iou_present = safe_mean([r["mean_iou_gt_present"] for r in class_rows if r["mean_iou_gt_present"] is not None])

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "center": args.center,
        "split": args.split,
        "exp_name": args.exp_name,
        "checkpoint": args.checkpoint,
        "runtime_device": runtime_device,
        "num_classes": args.num_classes,
        "tumor_label": args.tumor_label,
        "class_metas": class_metas,
        "num_total_cases": len(test_files),
        "num_scored_cases": len(case_rows),
        "num_failed_cases": len(failed_rows),
        "macro_mean_dice_all_cases": macro_dice_all,
        "macro_mean_iou_all_cases": macro_iou_all,
        "macro_mean_dice_gt_present": macro_dice_present,
        "macro_mean_iou_gt_present": macro_iou_present,
        "outputs": paths,
        "nifti_label_paths": nifti_label_paths,
    }
    with open(paths["summary_json"], "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    append_index_row(
        os.path.join(args.output_root, "eval_index.csv"),
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "run_name": run_name,
            "tag": args.tag,
            "center": args.center,
            "split": args.split,
            "exp_name": args.exp_name,
            "checkpoint": args.checkpoint,
            "num_classes": args.num_classes,
            "tumor_label": args.tumor_label,
            "num_total_cases": len(test_files),
            "num_scored_cases": len(case_rows),
            "num_failed_cases": len(failed_rows),
            "macro_mean_dice_all_cases": macro_dice_all,
            "macro_mean_iou_all_cases": macro_iou_all,
            "macro_mean_dice_gt_present": macro_dice_present,
            "macro_mean_iou_gt_present": macro_iou_present,
            "run_dir": paths["run_dir"],
            "summary_json": paths["summary_json"],
            "run_config_json": paths["run_config_json"],
        },
    )

    print("\n------ Test Summary (Tumor + Organs) ------")
    print(f"Scored cases: {len(case_rows)}")
    print(f"Failed cases: {len(failed_rows)}")
    print(f"Macro Dice (all cases): {macro_dice_all}")
    print(f"Macro IoU  (all cases): {macro_iou_all}")
    print(f"Macro Dice (gt present): {macro_dice_present}")
    print(f"Macro IoU  (gt present): {macro_iou_present}")
    for row in class_rows:
        print(
            f"[{row['class_type']}] label={row['label_id']} {row['class_name']}: "
            f"Dice={row['mean_dice_all_cases']}, IoU={row['mean_iou_all_cases']}, "
            f"Dice(gt_present)={row['mean_dice_gt_present']}"
        )
    print("--------------------------------------------")
    print(f"Case metrics : {paths['case_csv']}")
    print(f"Class summary: {paths['class_csv']}")
    print(f"Summary json : {paths['summary_json']}")
    if args.save_nifti_labels:
        print(f"NIfTI labels : {paths['nifti_label_dir']}")


def main():
    args = build_args()
    run_test(args)


if __name__ == "__main__":
    main()
