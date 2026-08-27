#!/usr/bin/env python3
import argparse
import importlib.util
import json
import shutil
import sys
import warnings
import zipfile
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*")
warnings.filterwarnings("ignore", module="urllib3")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOTALSEG_ROOT = PROJECT_ROOT / "TotalSegmentator-master"
sys.path.insert(0, str(TOTALSEG_ROOT))

import nibabel as nib
import numpy as np

from totalsegmentator.alignment import as_closest_canonical, undo_canonical
from totalsegmentator.cropping import undo_crop
from totalsegmentator.map_to_binary import class_map, class_map_5_parts, map_taskid_to_partname_ct
from totalsegmentator.nifti_ext_header import add_label_map_to_nifti
from totalsegmentator.postprocessing import remove_auxiliary_labels
from totalsegmentator.resampling import change_spacing

MESH_HELPER = PROJECT_ROOT.parent / "frontend-vue-prototype" / "run_totalseg.py"


def check_if_shape_and_affine_identical(img_1, img_2):
    max_diff = np.abs(img_1.affine - img_2.affine).max()
    if max_diff > 1e-5:
        raise RuntimeError(f"输出 affine 与输入不一致，最大差值：{max_diff}")
    if img_1.shape != img_2.shape:
        raise RuntimeError(f"输出 shape 与输入不一致：input={img_1.shape}, output={img_2.shape}")


def update_status(job_dir, status, message, progress=None):
    payload = {
        "status": status,
        "message": message,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    if progress is not None:
        payload["progress"] = progress
    Path(job_dir).mkdir(parents=True, exist_ok=True)
    Path(job_dir, "status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def task_config(task, fast=False):
    if task in {"abdomen", "full_total", "jetson_fast"}:
        task = "total"
    if task != "total":
        raise RuntimeError(f"当前 worker MVP 仅支持 task=total，不支持：{task}")
    if fast:
        return {
            "task_name": "total",
            "task_ids": [297],
            "resample": [3.0, 3.0, 3.0],
            "model": "3d_fullres",
            "trainer": "nnUNetTrainer_4000epochs_NoMirroring",
            "folds": [0],
            "multimodel": False,
        }
    return {
        "task_name": "total",
        "task_ids": [291, 292, 293, 294, 295],
        "resample": [1.5, 1.5, 1.5],
        "model": "3d_fullres",
        "trainer": "nnUNetTrainerNoMirroring",
        "folds": [0],
        "multimodel": True,
    }


def is_nifti(path):
    name = Path(path).name.lower()
    return name.endswith(".nii") or name.endswith(".nii.gz")


def load_input_as_nifti(input_path, job_dir, verbose=False):
    input_path = Path(input_path)
    original_nifti = Path(job_dir) / "input" / "original.nii.gz"
    original_nifti.parent.mkdir(parents=True, exist_ok=True)

    if is_nifti(input_path):
        if input_path.resolve() != original_nifti.resolve():
            shutil.copy2(input_path, original_nifti)
        return nib.load(original_nifti), original_nifti, "nifti"

    try:
        from totalsegmentator.dicom_io import dcm_to_nifti
    except Exception as exc:
        raise RuntimeError(
            "输入看起来不是 NIfTI，但当前 Python 环境缺少 DICOM 转换依赖 dicom2nifti/python-gdcm。"
            "请先安装 DICOM 依赖，或上传 .nii/.nii.gz。"
        ) from exc

    dcm_to_nifti(input_path, original_nifti, Path(job_dir) / "input", verbose=verbose)
    return nib.load(original_nifti), original_nifti, "dicom"


def prepare_totalseg_case(input_path, job_dir, task="total", fast=False, roi_subset=None):
    job_dir = Path(job_dir)
    preprocessed_dir = job_dir / "preprocessed"
    preprocessed_dir.mkdir(parents=True, exist_ok=True)

    update_status(job_dir, "preprocessing", "读取输入 CT", 10)
    cfg = task_config(task, fast=fast)
    img_in_orig, original_nifti, input_type = load_input_as_nifti(input_path, job_dir)

    if len(img_in_orig.shape) == 2:
        raise RuntimeError("TotalSegmentator 不支持 2D 图像")
    if len(img_in_orig.shape) > 3:
        img_in_orig = nib.Nifti1Image(img_in_orig.get_fdata()[:, :, :, 0], img_in_orig.affine)
        nib.save(img_in_orig, original_nifti)
    if img_in_orig.get_data_dtype().fields is not None:
        raise RuntimeError(f"输入 dtype 不合法：{img_in_orig.get_data_dtype()}")

    update_status(job_dir, "preprocessing", "执行 canonical 方向转换", 18)
    img_in = nib.Nifti1Image(img_in_orig.get_fdata(), img_in_orig.affine)
    bbox = None
    img_in = as_closest_canonical(img_in)
    canonical_shape = list(img_in.shape)
    canonical_affine = img_in.affine.tolist()

    update_status(job_dir, "preprocessing", "执行 TotalSegmentator resample", 25)
    resample = cfg["resample"]
    img_in_rsp = change_spacing(
        img_in,
        resample,
        order=3,
        dtype=np.int32,
        nr_cpus=1,
        use_gpu=False,
    )

    nib.save(img_in_rsp, preprocessed_dir / "s01_0000.nii.gz")

    nr_voxels_thr = 512 * 512 * 900
    img_parts = ["s01"]
    split = {
        "do_triple_split": False,
        "third": None,
        "margin": None,
    }
    ss = img_in_rsp.shape
    do_triple_split = np.prod(ss) > nr_voxels_thr and ss[2] > 200 and cfg["multimodel"]
    if do_triple_split:
        update_status(job_dir, "preprocessing", "大体积 CT 拆分为 s01/s02/s03", 30)
        img_parts = ["s01", "s02", "s03"]
        third = img_in_rsp.shape[2] // 3
        margin = 20
        data = img_in_rsp.get_fdata()
        nib.save(nib.Nifti1Image(data[:, :, : third + margin], img_in_rsp.affine), preprocessed_dir / "s01_0000.nii.gz")
        nib.save(nib.Nifti1Image(data[:, :, third + 1 - margin : third * 2 + margin], img_in_rsp.affine), preprocessed_dir / "s02_0000.nii.gz")
        nib.save(nib.Nifti1Image(data[:, :, third * 2 + 1 - margin :], img_in_rsp.affine), preprocessed_dir / "s03_0000.nii.gz")
        split = {
            "do_triple_split": True,
            "third": third,
            "margin": margin,
        }

    metadata = {
        "job_dir": str(job_dir),
        "input_type": input_type,
        "original_nifti": str(original_nifti),
        "task": task,
        "fast": fast,
        "task_name": cfg["task_name"],
        "task_ids": cfg["task_ids"],
        "model": cfg["model"],
        "trainer": cfg["trainer"],
        "folds": cfg["folds"],
        "resample": resample,
        "roi_subset": roi_subset,
        "crop_bbox": bbox,
        "original_shape": list(img_in_orig.shape),
        "original_affine": img_in_orig.affine.tolist(),
        "canonical_shape": canonical_shape,
        "canonical_affine": canonical_affine,
        "resampled_shape": list(img_in_rsp.shape),
        "resampled_affine": img_in_rsp.affine.tolist(),
        "img_parts": img_parts,
        "split": split,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    update_status(job_dir, "preprocessed", "预处理完成", 35)


def load_prediction(job_dir, task_id, img_part):
    path = Path(job_dir) / "jetson_result" / f"task_{task_id}" / f"{img_part}.nii.gz"
    if not path.is_file():
        raise RuntimeError(f"Jetson 结果缺少：{path}")
    return nib.load(path)


def combine_task_outputs(job_dir, metadata):
    task_name = metadata["task_name"]
    task_ids = metadata["task_ids"]
    img_parts = metadata["img_parts"]
    preprocessed_dir = Path(job_dir) / "preprocessed"

    if len(task_ids) == 1:
        for img_part in img_parts:
            pred = load_prediction(job_dir, task_ids[0], img_part)
            nib.save(pred, Path(job_dir) / "jetson_result" / f"{img_part}.nii.gz")
    else:
        class_map_inv = {v: k for k, v in class_map[task_name].items()}
        for img_part in img_parts:
            input_img = nib.load(preprocessed_dir / f"{img_part}_0000.nii.gz")
            combined = np.zeros(input_img.shape, dtype=np.uint8)
            for task_id in task_ids:
                part_name = map_taskid_to_partname_ct[task_id]
                seg = load_prediction(job_dir, task_id, img_part).get_fdata()
                for local_idx, class_name in class_map_5_parts[part_name].items():
                    combined[seg == local_idx] = class_map_inv[class_name]
            nib.save(nib.Nifti1Image(combined, input_img.affine), Path(job_dir) / "jetson_result" / f"{img_part}.nii.gz")


def merge_split_if_needed(job_dir, metadata):
    jetson_dir = Path(job_dir) / "jetson_result"
    split = metadata["split"]
    if not split["do_triple_split"]:
        return nib.load(jetson_dir / "s01.nii.gz")

    third = split["third"]
    margin = split["margin"]
    resampled_shape = tuple(metadata["resampled_shape"])
    affine = np.array(metadata["resampled_affine"])
    combined = np.zeros(resampled_shape, dtype=np.uint8)
    combined[:, :, :third] = nib.load(jetson_dir / "s01.nii.gz").get_fdata()[:, :, :-margin]
    combined[:, :, third : third * 2] = nib.load(jetson_dir / "s02.nii.gz").get_fdata()[:, :, margin - 1 : -margin]
    combined[:, :, third * 2 :] = nib.load(jetson_dir / "s03.nii.gz").get_fdata()[:, :, margin - 1 :]
    merged = nib.Nifti1Image(combined, affine)
    nib.save(merged, jetson_dir / "s01.nii.gz")
    return merged


def finalize_totalseg_case(job_dir, task="total", output_type="ml"):
    job_dir = Path(job_dir)
    metadata_path = job_dir / "metadata.json"
    if not metadata_path.is_file():
        raise RuntimeError(f"缺少 metadata.json：{metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["task"] != task:
        raise RuntimeError(f"任务不一致：metadata={metadata['task']} request={task}")

    update_status(job_dir, "postprocessing", "合并 Jetson 多模型输出", 78)
    combine_task_outputs(job_dir, metadata)

    update_status(job_dir, "postprocessing", "合并 split 输出", 82)
    img_pred = merge_split_if_needed(job_dir, metadata)
    img_pred = remove_auxiliary_labels(img_pred, metadata["task_name"])

    update_status(job_dir, "postprocessing", "resample 回 canonical 原始 shape", 88)
    original_nifti = Path(metadata["original_nifti"])
    img_in_orig = nib.load(original_nifti)
    img_in = as_closest_canonical(nib.Nifti1Image(img_in_orig.get_fdata(), img_in_orig.affine))
    img_pred = change_spacing(
        img_pred,
        metadata["resample"],
        tuple(metadata["canonical_shape"]),
        order=0,
        dtype=np.uint8,
        nr_cpus=1,
        force_affine=img_in.affine,
        use_gpu=False,
    )

    update_status(job_dir, "postprocessing", "undo canonical/crop 并保存最终分割", 94)
    img_pred = undo_canonical(img_pred, img_in_orig)
    if metadata["crop_bbox"] is not None:
        img_pred = undo_crop(img_pred, img_in_orig, metadata["crop_bbox"])
    check_if_shape_and_affine_identical(img_in_orig, img_pred)

    img_data = img_pred.get_fdata().astype(np.uint8)
    new_header = img_in_orig.header.copy()
    new_header.set_data_dtype(np.uint8)
    img_out = nib.Nifti1Image(img_data, img_pred.affine, new_header)
    img_out = add_label_map_to_nifti(img_out, class_map[metadata["task_name"]])

    final_dir = job_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    nib.save(img_out, final_dir / "segmentation.nii.gz")
    update_status(job_dir, "done", "后处理完成", 100)


def generate_mesh_outputs(job_dir):
    job_dir = Path(job_dir)
    final_dir = job_dir / "final"
    segmentation = final_dir / "segmentation.nii.gz"
    if not segmentation.is_file():
        raise RuntimeError(f"缺少三维重建输入：{segmentation}")
    if not MESH_HELPER.is_file():
        raise RuntimeError(f"缺少三维重建 helper：{MESH_HELPER}")

    label_map_path = final_dir / "label_map.json"
    if not label_map_path.is_file():
        payload = {
            "label_map": {str(label_id): name for label_id, name in class_map["total"].items()}
        }
        label_map_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    update_status(job_dir, "mesh", "正在生成三维模型", 100)
    spec = importlib.util.spec_from_file_location("ppgl_mesh_helper", MESH_HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    outputs = module.create_mesh_outputs(segmentation, label_map_path, final_dir)
    if not Path(outputs["glb_path"]).is_file() or not Path(outputs["manifest_path"]).is_file():
        raise RuntimeError("三维模型生成完成但缺少 scene.glb 或 mesh_manifest.json")
    update_status(job_dir, "done", "三维模型已生成", 100)


def export_totalseg_masks(job_dir):
    job_dir = Path(job_dir)
    final_dir = job_dir / "final"
    segmentation = final_dir / "segmentation.nii.gz"
    if not segmentation.is_file():
        raise RuntimeError(f"缺少 TotalSegmentator 多标签结果：{segmentation}")

    update_status(job_dir, "exporting", "正在拆分 TotalSegmentator 器官 mask", 96)
    img = nib.load(str(segmentation))
    data = np.rint(np.asarray(img.dataobj)).astype(np.uint16, copy=False)
    mask_dir = job_dir / "totalseg_existing"
    if mask_dir.exists():
        shutil.rmtree(mask_dir)
    mask_dir.mkdir(parents=True, exist_ok=True)

    header = img.header.copy()
    header.set_data_dtype(np.uint8)
    exported = 0
    for label_id, name in class_map["total"].items():
        mask = (data == int(label_id)).astype(np.uint8)
        if int(mask.sum()) == 0:
            continue
        nib.save(nib.Nifti1Image(mask, img.affine, header), mask_dir / f"{name}.nii.gz")
        exported += 1

    if exported == 0:
        raise RuntimeError("TotalSegmentator 结果中没有可导出的器官 mask")

    zip_path = job_dir / "totalseg_existing.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file in sorted(mask_dir.glob("*.nii.gz")):
            zip_file.write(file, file.name)
    update_status(job_dir, "exported", f"已导出 {exported} 个器官 mask", 97)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "finalize", "mesh", "export-totalseg"])
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--input")
    parser.add_argument("--task", default="total")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--roi-subset")
    parser.add_argument("--output-type", default="ml")
    args = parser.parse_args()

    job_dir = Path(args.job_dir)
    try:
        if args.action == "prepare":
            if not args.input:
                raise RuntimeError("--input 不能为空")
            prepare_totalseg_case(Path(args.input), job_dir, args.task, args.fast, args.roi_subset)
        elif args.action == "finalize":
            finalize_totalseg_case(job_dir, args.task, args.output_type)
        elif args.action == "mesh":
            generate_mesh_outputs(job_dir)
        else:
            export_totalseg_masks(job_dir)
    except Exception as exc:
        update_status(job_dir, "failed", str(exc))
        raise


if __name__ == "__main__":
    main()
