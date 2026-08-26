#!/usr/bin/env python
from __future__ import annotations

import json
import os
import re
import shutil
import traceback
import zipfile
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict
import inspect
import hmac


for _name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS",
):
    os.environ.setdefault(_name, "1")

os.environ.setdefault(
    "TOTALSEG_WEIGHTS_PATH",
    str(Path.home() / ".totalsegmentator" / "nnunet" / "results"),
)
os.environ.setdefault("nnUNet_raw", os.environ["TOTALSEG_WEIGHTS_PATH"])
os.environ.setdefault("nnUNet_preprocessed", os.environ["TOTALSEG_WEIGHTS_PATH"])
os.environ.setdefault("nnUNet_results", os.environ["TOTALSEG_WEIGHTS_PATH"])

try:
    import sklearn  # noqa: F401
except Exception:
    pass
import torch
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
from nnunetv2.utilities.file_path_utilities import get_output_folder


try:
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass


JOB_ROOT = Path(os.environ.get("JETSON_JOB_ROOT", "/data/jobs")).expanduser()
MAX_CACHED_MODELS = int(os.environ.get("MAX_CACHED_MODELS", "0"))
DEFAULT_PLANS = os.environ.get("NNUNET_PLANS", "nnUNetPlans")
DEFAULT_CHECKPOINT = os.environ.get("NNUNET_CHECKPOINT", "checkpoint_final.pth")
CASE_FILE_RE = re.compile(r"^s\d+_0000\.nii\.gz$")

app = FastAPI(title="Jetson TotalSegmentator nnU-Net Predictor")
INTERNAL_API_KEY = os.environ.get("PPGL_INTERNAL_API_KEY", "").strip()
PREDICT_LOCK = Lock()
PREDICTOR_CACHE: "OrderedDict[tuple[Any, ...], nnUNetPredictor]" = OrderedDict()


@app.middleware("http")
async def require_internal_api_key(request: Request, call_next):
    provided = request.headers.get("X-PPGL-Internal-Key", "")
    if not INTERNAL_API_KEY:
        return JSONResponse(status_code=503, content={"detail": "PPGL_INTERNAL_API_KEY is not configured"})
    if not provided or not hmac.compare_digest(provided, INTERNAL_API_KEY):
        return JSONResponse(status_code=401, content={"detail": "Invalid internal API key"})
    return await call_next(request)


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def update_status(job_id: str, status: str, message: str, **extra: Any) -> None:
    write_json(
        JOB_ROOT / job_id / "status.json",
        {
            "job_id": job_id,
            "status": status,
            "message": message,
            "updated_at": now_text(),
            **extra,
        },
    )


def parse_jsonish(value: str | None, default: Any) -> Any:
    if value is None or str(value).strip() == "":
        return default
    text = str(value).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return text


def parse_task_ids(value: str) -> list[int]:
    parsed = parse_jsonish(value, [])
    if isinstance(parsed, int):
        return [parsed]
    if isinstance(parsed, str):
        parsed = [parsed]
    if not isinstance(parsed, list) or not parsed:
        raise HTTPException(status_code=400, detail="task_ids must be a task id or a non-empty list")
    try:
        return [int(item) for item in parsed]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="task_ids must contain integers") from exc


def parse_folds(value: str | None) -> list[int] | None:
    parsed = parse_jsonish(value, [0])
    if parsed in (None, "", "all"):
        return None
    if isinstance(parsed, int):
        return [parsed]
    if isinstance(parsed, str):
        parsed = [parsed]
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="folds must be an integer, list, or 'all'")
    try:
        return [int(item) for item in parsed]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="folds must contain integers") from exc


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def ensure_job_id(value: str) -> str:
    job_id = str(value or "").strip()
    if not re.match(r"^[A-Za-z0-9_.-]+$", job_id):
        raise HTTPException(status_code=400, detail="job_id may only contain letters, numbers, dot, underscore, or dash")
    return job_id


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_root = dest_dir.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            target = (dest_dir / member.filename).resolve()
            if not str(target).startswith(str(dest_root) + os.sep) and target != dest_root:
                raise HTTPException(status_code=400, detail=f"Unsafe zip member path: {member.filename}")
        zf.extractall(dest_dir)


def validate_input_dir(job_dir: Path) -> Path:
    input_dir = job_dir / "input"
    if not input_dir.is_dir():
        root_case_files = sorted(path for path in job_dir.glob("s*_0000.nii.gz") if CASE_FILE_RE.match(path.name))
        if root_case_files:
            input_dir.mkdir(parents=True, exist_ok=True)
            for path in root_case_files:
                shutil.move(str(path), input_dir / path.name)
        else:
            raise HTTPException(status_code=400, detail="zip must contain input/s01_0000.nii.gz")

    case_files = sorted(path.name for path in input_dir.glob("*.nii.gz"))
    invalid = [name for name in case_files if not CASE_FILE_RE.match(name)]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid nnU-Net input filename(s): {invalid}")
    if "s01_0000.nii.gz" not in case_files:
        raise HTTPException(status_code=400, detail="input/s01_0000.nii.gz is required")
    return input_dir


def model_folder_for(task_id: int, trainer: str, plans: str, model: str) -> Path:
    try:
        folder = Path(get_output_folder(task_id, trainer, plans, model))
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not resolve model folder for task_id={task_id}: {exc}") from exc
    if not folder.exists():
        raise HTTPException(status_code=404, detail=f"Model folder not found for task_id={task_id}: {folder}")
    return folder


def supports_keyword_argument(func: Any, keyword: str) -> bool:
    try:
        return keyword in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def make_predictor(device: torch.device, tta: bool, step_size: float) -> nnUNetPredictor:
    kwargs = {
        "tile_step_size": step_size,
        "use_gaussian": True,
        "use_mirroring": bool(tta),
        "device": device,
        "verbose": False,
        "verbose_preprocessing": False,
        "allow_tqdm": True,
    }
    if supports_keyword_argument(nnUNetPredictor, "perform_everything_on_gpu"):
        kwargs["perform_everything_on_gpu"] = True
    else:
        kwargs["perform_everything_on_device"] = True
    return nnUNetPredictor(**kwargs)


def get_predictor(
    task_id: int,
    model: str,
    trainer: str,
    plans: str,
    folds: list[int] | None,
    tta: bool,
    step_size: float,
) -> nnUNetPredictor:
    key = (task_id, model, trainer, plans, tuple(folds) if folds is not None else "all", bool(tta), float(step_size))
    cached = PREDICTOR_CACHE.get(key)
    if cached is not None:
        PREDICTOR_CACHE.move_to_end(key)
        return cached

    device = torch.device("cuda")
    folder = model_folder_for(task_id, trainer, plans, model)
    predictor = make_predictor(device, tta=tta, step_size=step_size)
    predictor.initialize_from_trained_model_folder(folder, use_folds=folds, checkpoint_name=DEFAULT_CHECKPOINT)
    PREDICTOR_CACHE[key] = predictor
    PREDICTOR_CACHE.move_to_end(key)

    while len(PREDICTOR_CACHE) > max(0, MAX_CACHED_MODELS):
        PREDICTOR_CACHE.popitem(last=False)
        torch.cuda.empty_cache()
    return predictor


def predict_with_cached_predictor(
    input_dir: Path,
    output_dir: Path,
    task_id: int,
    model: str,
    trainer: str,
    plans: str,
    folds: list[int] | None,
    tta: bool,
    step_size: float,
) -> None:
    predictor = get_predictor(task_id, model, trainer, plans, folds, tta, step_size)
    output_dir.mkdir(parents=True, exist_ok=True)
    predictor.predict_from_files(
        str(input_dir),
        str(output_dir),
        save_probabilities=False,
        overwrite=True,
        num_processes_preprocessing=1,
        num_processes_segmentation_export=1,
        folder_with_segs_from_prev_stage=None,
        num_parts=1,
        part_id=0,
    )


def predict_without_cache(
    input_dir: Path,
    output_dir: Path,
    task_id: int,
    model: str,
    trainer: str,
    plans: str,
    folds: list[int] | None,
    tta: bool,
    step_size: float,
) -> None:
    device = torch.device("cuda")
    model_folder = model_folder_for(task_id, trainer, plans, model)
    predictor = make_predictor(device, tta=tta, step_size=step_size)
    predictor.initialize_from_trained_model_folder(
        model_folder,
        use_folds=folds,
        checkpoint_name=DEFAULT_CHECKPOINT,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    predictor.predict_from_files(
        str(input_dir),
        str(output_dir),
        save_probabilities=False,
        overwrite=True,
        num_processes_preprocessing=1,
        num_processes_segmentation_export=1,
        folder_with_segs_from_prev_stage=None,
        num_parts=1,
        part_id=0,
    )


def zip_output(output_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(output_dir))


def module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


@app.get("/health")
def health() -> Dict[str, Any]:
    cuda_available = torch.cuda.is_available()
    weights_path = Path(os.environ.get("TOTALSEG_WEIGHTS_PATH", "")).expanduser()
    return {
        "status": "ok" if cuda_available else "cuda_unavailable",
        "cuda_available": cuda_available,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "cudnn_version": torch.backends.cudnn.version(),
        "device_name": torch.cuda.get_device_name(0) if cuda_available else "",
        "totalsegmentator_available": module_available("totalsegmentator"),
        "nnunet_available": module_available("nnunetv2"),
        "weights_path": str(weights_path),
        "weights_path_exists": weights_path.exists(),
        "job_root": str(JOB_ROOT),
        "max_cached_models": MAX_CACHED_MODELS,
        "cached_models": len(PREDICTOR_CACHE),
    }


@app.post("/predict")
async def predict(
    job_id: str = Form(...),
    task_ids: str = Form(...),
    model: str = Form("3d_fullres"),
    trainer: str = Form("nnUNetTrainerNoMirroring"),
    folds: str = Form("[0]"),
    tta: str = Form("false"),
    plans: str = Form(DEFAULT_PLANS),
    step_size: float = Form(0.5),
    file: UploadFile = File(...),
) -> FileResponse:
    if not torch.cuda.is_available():
        raise HTTPException(status_code=503, detail="CUDA is not available on this Jetson service")

    clean_job_id = ensure_job_id(job_id)
    task_id_list = parse_task_ids(task_ids)
    fold_list = parse_folds(folds)
    use_tta = parse_bool(tta, default=False)

    job_dir = JOB_ROOT / clean_job_id
    input_zip = job_dir / "request.zip"
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    response_zip = job_dir / "prediction_output.zip"

    try:
        update_status(clean_job_id, "received", "Request received", task_ids=task_id_list)
        if job_dir.exists():
            shutil.rmtree(job_dir)
        input_dir.mkdir(parents=True, exist_ok=True)

        with input_zip.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        safe_extract_zip(input_zip, job_dir)
        input_dir = validate_input_dir(job_dir)

        metadata_path = job_dir / "metadata.json"
        if not metadata_path.exists():
            update_status(clean_job_id, "warning", "metadata.json not found; continuing GPU inference only")

        with PREDICT_LOCK:
            for task_id in task_id_list:
                task_output_dir = output_dir / f"task_{task_id}"
                update_status(clean_job_id, "running", f"Predicting task {task_id}", task_id=task_id)
                if MAX_CACHED_MODELS > 0:
                    predict_with_cached_predictor(
                        input_dir, task_output_dir, task_id, model, trainer, plans, fold_list, use_tta, step_size
                    )
                else:
                    predict_without_cache(
                        input_dir, task_output_dir, task_id, model, trainer, plans, fold_list, use_tta, step_size
                    )
                torch.cuda.empty_cache()

        zip_output(output_dir, response_zip)
        update_status(clean_job_id, "completed", "Prediction completed", output_zip=str(response_zip))
        return FileResponse(
            response_zip,
            media_type="application/zip",
            filename=f"{clean_job_id}_prediction_output.zip",
        )
    except HTTPException:
        raise
    except torch.cuda.OutOfMemoryError as exc:
        torch.cuda.empty_cache()
        update_status(clean_job_id, "failed", "CUDA out of memory", error=str(exc))
        raise HTTPException(status_code=507, detail=f"CUDA out of memory: {exc}") from exc
    except Exception as exc:
        error_log = job_dir / "error.log"
        error_log.parent.mkdir(parents=True, exist_ok=True)
        error_log.write_text(traceback.format_exc(), encoding="utf-8")
        update_status(clean_job_id, "failed", f"Prediction failed: {exc}", error_log=str(error_log))
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}") from exc
