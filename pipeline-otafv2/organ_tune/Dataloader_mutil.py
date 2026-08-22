from __future__ import annotations

import json
import os
import random
from pathlib import Path

import nibabel as nib
import numpy as np
import torch
from monai.data import MetaTensor
from monai.transforms import (
    Compose,
    CropForegroundd,
    DeleteItemsd,
    EnsureChannelFirstd,
    EnsureTyped,
    Lambdad,
    LoadImaged,
    MapTransform,
    Orientationd,
    ScaleIntensityRanged,
    SpatialPadd,
    Spacingd,
    ToTensord,
)

# 在祝愿师兄的论文里，它设置里hu指对应的是【127，255】，对应的最大最小值为【0，255】
window_low = 0
window_high = 255

PARTIAL_LABEL_CHANNELS = 9
PARTIAL_LABEL_LAYOUT = "xyzc_last"
PARTIAL_SMALL_ORGAN_NAMES = ("left_kidney", "right_kidney", "left_adrenal", "right_adrenal")


class PartialLabelError(RuntimeError):
    pass


def _resolve_data_path(raw_path: str, root_dir: str) -> str:
    path = Path(str(raw_path))
    if path.is_absolute():
        return str(path)
    return str((Path(root_dir) / path).resolve())


def _load_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class LoadPartialMultichannelLabeld(MapTransform):
    def __init__(
        self,
        keys,
        valid_labels_key: str = "valid_labels",
        num_channels: int = PARTIAL_LABEL_CHANNELS,
        label_layout_key: str = "label_layout",
    ):
        super().__init__(keys)
        self.valid_labels_key = valid_labels_key
        self.num_channels = int(num_channels)
        self.label_layout_key = label_layout_key

    def __call__(self, data):
        d = dict(data)
        valid_labels = np.asarray(d.get(self.valid_labels_key, []), dtype=np.uint8)
        if valid_labels.shape != (self.num_channels,):
            raise PartialLabelError(
                f"valid_labels shape 非法: expected=({self.num_channels},), got={tuple(valid_labels.shape)}"
            )
        declared_channels = int(d.get("num_channels", self.num_channels))
        if declared_channels != self.num_channels:
            raise PartialLabelError(
                f"num_channels 非法: expected={self.num_channels}, got={declared_channels}"
            )
        label_layout = str(d.get(self.label_layout_key, PARTIAL_LABEL_LAYOUT))
        if label_layout != PARTIAL_LABEL_LAYOUT:
            raise PartialLabelError(
                f"partial-label label_layout 非法: expected={PARTIAL_LABEL_LAYOUT}, got={label_layout}"
            )

        for key in self.keys:
            path = Path(str(d[key]))
            if not path.exists():
                raise FileNotFoundError(f"找不到 partial-label 文件: {path}")

            nifti = nib.load(str(path))
            arr = np.asarray(nifti.dataobj)
            if arr.ndim != 4:
                raise PartialLabelError(f"partial-label 必须是 4D NIfTI: path={path}, shape={arr.shape}")
            if int(arr.shape[-1]) != self.num_channels:
                raise PartialLabelError(
                    f"partial-label channel 轴非法: path={path}, expected_last_dim={self.num_channels}, got={arr.shape[-1]}"
                )

            arr = np.moveaxis(arr, -1, 0).astype(np.uint8, copy=False)
            if int(arr.shape[0]) != self.num_channels:
                raise PartialLabelError(
                    f"channel-first 后 channel 数非法: path={path}, got={arr.shape[0]}"
                )

            uniq = set(int(v) for v in np.unique(arr).tolist())
            if not uniq.issubset({0, 1}):
                raise PartialLabelError(f"label 仅允许 {{0,1}}: path={path}, unique={sorted(uniq)}")

            flat_sum = arr.reshape(self.num_channels, -1).sum(axis=1)
            for channel_idx, is_valid in enumerate(valid_labels.tolist()):
                if int(is_valid) == 1 and int(flat_sum[channel_idx]) <= 0:
                    raise PartialLabelError(
                        f"valid_labels[{channel_idx}] == 1 但 full-case label 为空: path={path}"
                    )

            affine = np.asarray(nifti.affine, dtype=np.float64)
            d[key] = MetaTensor(
                arr,
                affine=affine,
                meta={
                    "filename_or_obj": str(path),
                    "affine": affine,
                    "original_affine": affine,
                    "spatial_shape": np.asarray(arr.shape[1:], dtype=np.int64),
                    "original_channel_dim": 0,
                },
            )
            d[f"{key}_meta_dict"] = {
                "filename_or_obj": str(path),
                "affine": affine,
                "original_affine": affine,
                "spatial_shape": np.asarray(arr.shape[1:], dtype=np.int64),
                "original_channel_dim": 0,
            }

        d[self.valid_labels_key] = valid_labels
        return d


class BuildValidUnionMaskd(MapTransform):
    def __init__(self, label_key: str = "label", valid_labels_key: str = "valid_labels", output_key: str = "label_union_valid"):
        super().__init__([label_key])
        self.label_key = label_key
        self.valid_labels_key = valid_labels_key
        self.output_key = output_key

    def __call__(self, data):
        d = dict(data)
        label = d[self.label_key]
        valid_labels = np.asarray(d.get(self.valid_labels_key, []), dtype=np.uint8)
        if valid_labels.shape != (int(label.shape[0]),):
            raise PartialLabelError(
                f"BuildValidUnionMaskd: label channels={label.shape[0]} 与 valid_labels={valid_labels.shape} 不匹配"
            )

        valid_indices = [idx for idx, flag in enumerate(valid_labels.tolist()) if int(flag) == 1]
        if not valid_indices:
            raise PartialLabelError("BuildValidUnionMaskd: 当前样本没有任何 valid organ，不应进入 loader。")

        union = (label[valid_indices] > 0).any(dim=0, keepdim=True).to(dtype=label.dtype)
        if int(union.sum().item()) <= 0:
            raise PartialLabelError("BuildValidUnionMaskd: valid organ union 为空，无法用于 foreground crop。")
        d[self.output_key] = union
        return d


class BuildPartialSamplingMaskd(MapTransform):
    def __init__(
        self,
        label_key: str = "label",
        valid_labels_key: str = "valid_labels",
        union_key: str = "label_union_valid",
        sampling_key: str = "label_sampling_valid",
        small_key: str = "label_small_valid",
        small_organ_names: tuple[str, ...] = PARTIAL_SMALL_ORGAN_NAMES,
        enable_mixed_small_sampling: bool = False,
        small_sample_prob: float = 0.6,
        random_seed: int = 0,
    ):
        super().__init__([label_key])
        self.label_key = label_key
        self.valid_labels_key = valid_labels_key
        self.union_key = union_key
        self.sampling_key = sampling_key
        self.small_key = small_key
        self.small_organ_names = set(str(x) for x in small_organ_names)
        self.enable_mixed_small_sampling = bool(enable_mixed_small_sampling)
        self.small_sample_prob = float(small_sample_prob)
        self.rng = random.Random(int(random_seed))

    def __call__(self, data):
        d = dict(data)
        label = d[self.label_key]
        valid_labels = np.asarray(d.get(self.valid_labels_key, []), dtype=np.uint8)
        if valid_labels.shape != (int(label.shape[0]),):
            raise PartialLabelError(
                f"BuildPartialSamplingMaskd: label channels={label.shape[0]} 与 valid_labels={valid_labels.shape} 不匹配"
            )

        valid_indices = [idx for idx, flag in enumerate(valid_labels.tolist()) if int(flag) == 1]
        if not valid_indices:
            raise PartialLabelError("BuildPartialSamplingMaskd: 当前样本没有任何 valid organ，不应进入 loader。")

        union = (label[valid_indices] > 0).any(dim=0, keepdim=True).to(dtype=label.dtype)
        if int(union.sum().item()) <= 0:
            raise PartialLabelError("BuildPartialSamplingMaskd: valid organ union 为空，无法用于 foreground crop。")

        channel_names = tuple(str(x) for x in d.get("channel_names", ()))
        if len(channel_names) != int(label.shape[0]):
            channel_names = tuple(
                (
                    "aorta",
                    "left_kidney",
                    "right_kidney",
                    "ivc",
                    "left_adrenal",
                    "right_adrenal",
                    "left_psoas",
                    "right_psoas",
                    "vertebrae",
                )[idx]
                if idx < 9
                else f"ch_{idx}"
                for idx in range(int(label.shape[0]))
            )

        small_indices = [idx for idx in valid_indices if channel_names[idx] in self.small_organ_names]
        small_union = (
            (label[small_indices] > 0).any(dim=0, keepdim=True).to(dtype=label.dtype)
            if small_indices
            else torch.zeros_like(union)
        )

        use_small = (
            self.enable_mixed_small_sampling
            and int(small_union.sum().item()) > 0
            and (self.rng.random() < self.small_sample_prob)
        )
        sampling = small_union if use_small else union

        d[self.union_key] = union
        d[self.small_key] = small_union
        d[self.sampling_key] = sampling
        d["partial_sampling_mode"] = "small_valid" if use_small else "union_valid"
        return d


def build_val_transforms(
    val_roi_size: int = 128,
    fg_margin: int = 10,
    partial_label_mode: bool = False,
    skip_preprocess_transforms: bool = False,
    skip_crop_foreground: bool = False,
):
    if partial_label_mode:
        transforms = [
            LoadImaged(keys=["image"]),
            EnsureChannelFirstd(keys=["image"]),
            LoadPartialMultichannelLabeld(keys=["label"]),
        ]
        if not skip_preprocess_transforms:
            transforms.extend(
                [
                    Orientationd(keys=["image", "label"], axcodes="RAS"),
                    Spacingd(
                        keys=["image", "label"],
                        pixdim=(1.0, 1.0, 1.0),
                        mode=("bilinear", "nearest"),
                    ),
                ]
            )
        transforms.extend(
            [
                EnsureTyped(keys=["image", "label"], track_meta=True),
                Lambdad(keys="valid_labels", func=lambda x: np.asarray(x, dtype=np.uint8)),
                ScaleIntensityRanged(
                    keys=["image"],
                    a_min=window_low,
                    a_max=window_high,
                    b_min=0,
                    b_max=1,
                    clip=True,
                ),
                BuildPartialSamplingMaskd(
                    label_key="label",
                    valid_labels_key="valid_labels",
                    union_key="label_union_valid",
                    sampling_key="label_sampling_valid",
                    small_key="label_small_valid",
                    enable_mixed_small_sampling=False,
                    small_sample_prob=0.0,
                    random_seed=0,
                ),
            ]
        )
        if not skip_crop_foreground:
            transforms.append(
                    CropForegroundd(
                        keys=["image", "label", "label_union_valid"],
                        source_key="image",
                        margin=fg_margin,
                    )
            )
        transforms.extend(
            [
                SpatialPadd(
                    keys=["image", "label", "label_union_valid"],
                    spatial_size=(val_roi_size, val_roi_size, val_roi_size),
                    method="symmetric",
                    mode="constant",
                ),
                ToTensord(keys=["image", "label", "valid_labels", "label_union_valid"]),
                DeleteItemsd(
                    keys=[
                        "label_union_valid",
                        "label_sampling_valid",
                        "label_small_valid",
                        "partial_sampling_mode",
                        "available_organs",
                        "missing_organs",
                    ]
                ),
            ]
        )
        return Compose(transforms)

    return Compose(
        [
            LoadImaged(keys=["image", "label"]),
            EnsureChannelFirstd(keys=["image", "label"]),
            Orientationd(keys=["image", "label"], axcodes="RAS"),
            Spacingd(
                keys=["image", "label"],
                pixdim=(1.0, 1.0, 1.0),
                mode=("bilinear", "nearest"),
            ),
            EnsureTyped(keys=["image", "label"], track_meta=True),
            Lambdad(keys="label", func=lambda x: x.long()),
            ScaleIntensityRanged(
                keys=["image"],
                a_min=window_low,
                a_max=window_high,
                b_min=0,
                b_max=1,
                clip=True,
            ),
            CropForegroundd(
                keys=["image", "label"],
                source_key="image",
                margin=fg_margin,
            ),
            SpatialPadd(
                keys=["image", "label"],
                spatial_size=(val_roi_size, val_roi_size, val_roi_size),
                method="symmetric",
                mode="constant",
            ),
            ToTensord(keys=["image", "label"]),
        ]
    )


def parse_data_list(txt_path, root_dir, image_folder="images", label_folder="labels_multiV4"):
    data_list = []

    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"未找到数据列表文件: {txt_path}")

    if str(txt_path).lower().endswith(".jsonl"):
        for row in _load_jsonl(txt_path):
            img_path = _resolve_data_path(str(row["image_path"]), root_dir)
            mask_raw = row.get("mask_path")
            if not mask_raw:
                mask_raw = row.get("label_path") or row.get("label_4d_nifti_path")
            if not mask_raw:
                raise PartialLabelError(
                    f"JSONL 缺少 mask_path/label_path/label_4d_nifti_path: sample={row.get('sample_id', 'unknown')}"
                )
            lbl_path = _resolve_data_path(str(mask_raw), root_dir)

            if not os.path.exists(img_path):
                print(f"⚠️ 警告: 找不到影像文件 {img_path}")
                continue
            if not os.path.exists(lbl_path):
                print(f"⚠️ 警告: 找不到标签文件 {lbl_path}")
                continue

            data_list.append(
                {
                    "image": img_path,
                    "label": lbl_path,
                    "name": row.get("sample_id", Path(lbl_path).stem),
                    "dataset": str(row.get("dataset", "unknown")),
                    "case_id": str(row.get("case_id", "")),
                    "available_organs": tuple(row.get("available_organs", [])),
                    "missing_organs": tuple(row.get("missing_organs", [])),
                    "valid_labels": list(row.get("valid_labels", [])),
                    "label_layout": str(row.get("label_layout", PARTIAL_LABEL_LAYOUT)),
                    "num_channels": int(row.get("num_channels", PARTIAL_LABEL_CHANNELS)),
                    "channel_names": tuple(row.get("channel_names", [])),
                    "source_domain": str(row.get("source_domain", row.get("dataset", "unknown"))),
                    "source_weight": float(row.get("source_weight", 1.0)),
                    "split": str(row.get("split", "")),
                    "preprocessed_ras1mm": bool(row.get("preprocessed_ras1mm", False)),
                    "cropped_foreground": bool(row.get("cropped_foreground", False)),
                    "crop_margin": int(row.get("crop_margin", 0) or 0),
                }
            )
        return data_list

    with open(txt_path, "r", encoding="utf-8") as f:
        file_names = [line.strip() for line in f.readlines() if line.strip()]

    for fname in file_names:
        if not fname.endswith(".nii.gz") and not fname.endswith(".nii"):
            fname_full = fname + ".nii.gz"
        else:
            fname_full = fname

        img_path = os.path.join(root_dir, image_folder, fname_full)
        lbl_path = os.path.join(root_dir, label_folder, fname_full)

        if not os.path.exists(img_path):
            print(f"⚠️ 警告: 找不到影像文件 {img_path}")
            continue
        if not os.path.exists(lbl_path):
            print(f"⚠️ 警告: 找不到标签文件 {lbl_path}")
            continue

        data_list.append({"image": img_path, "label": lbl_path, "name": fname})

    return data_list


def parse_image_only_data_list(txt_path, root_dir, image_folder="images"):
    data_list = []

    if not os.path.exists(txt_path):
        raise FileNotFoundError(f"未找到数据列表文件: {txt_path}")

    if str(txt_path).lower().endswith(".jsonl"):
        for row in _load_jsonl(txt_path):
            image_raw = row.get("image_path") or row.get("image")
            if not image_raw:
                raise PartialLabelError(
                    f"JSONL 缺少 image_path/image: sample={row.get('sample_id', 'unknown')}"
                )
            img_path = _resolve_data_path(str(image_raw), root_dir)
            if not os.path.exists(img_path):
                print(f"⚠️ 警告: 找不到影像文件 {img_path}")
                continue

            sample_id = row.get("sample_id") or row.get("case_id") or Path(img_path).name
            data_list.append(
                {
                    "image": img_path,
                    "name": str(sample_id),
                    "dataset": str(row.get("dataset", "unknown")),
                    "case_id": str(row.get("case_id", sample_id)),
                    "source_domain": str(row.get("source_domain", row.get("dataset", "unknown"))),
                    "split": str(row.get("split", "")),
                }
            )
        return data_list

    with open(txt_path, "r", encoding="utf-8") as f:
        file_names = [line.strip() for line in f.readlines() if line.strip()]

    for fname in file_names:
        if not fname.endswith(".nii.gz") and not fname.endswith(".nii"):
            fname_full = fname + ".nii.gz"
        else:
            fname_full = fname

        img_path = os.path.join(root_dir, image_folder, fname_full)
        if not os.path.exists(img_path):
            print(f"⚠️ 警告: 找不到影像文件 {img_path}")
            continue

        name = Path(fname_full).name
        if name.endswith(".nii.gz"):
            name = name[:-7]
        elif name.endswith(".nii"):
            name = name[:-4]
        data_list.append({"image": img_path, "name": name, "case_id": name, "dataset": "unknown"})

    return data_list


def build_image_only_val_transforms(
    val_roi_size: int = 128,
    fg_margin: int = 10,
    skip_preprocess_transforms: bool = False,
    skip_crop_foreground: bool = False,
):
    transforms = [
        LoadImaged(keys=["image"]),
        EnsureChannelFirstd(keys=["image"]),
    ]
    if not skip_preprocess_transforms:
        transforms.extend(
            [
                Orientationd(keys=["image"], axcodes="RAS"),
                Spacingd(
                    keys=["image"],
                    pixdim=(1.0, 1.0, 1.0),
                    mode=("bilinear",),
                ),
            ]
        )
    transforms.extend(
        [
            EnsureTyped(keys=["image"], track_meta=True),
            ScaleIntensityRanged(
                keys=["image"],
                a_min=window_low,
                a_max=window_high,
                b_min=0,
                b_max=1,
                clip=True,
            ),
        ]
    )
    if not skip_crop_foreground:
        transforms.append(
            CropForegroundd(
                keys=["image"],
                source_key="image",
                margin=fg_margin,
            )
        )
    transforms.extend(
        [
            SpatialPadd(
                keys=["image"],
                spatial_size=(val_roi_size, val_roi_size, val_roi_size),
                method="symmetric",
                mode="constant",
            ),
            ToTensord(keys=["image"]),
        ]
    )
    return Compose(transforms)
