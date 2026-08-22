from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_DIR / "checkpoints" / "adrenal_specialist"
DEFAULT_DATASET_ID = "705"
DEFAULT_CONFIGURATION = "3d_fullres"
DEFAULT_FOLD = "0"
DEFAULT_CHECKPOINT = "checkpoint_best.pth"


def _nnunet_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["nnUNet_raw"] = str(root / "nnUNet_raw")
    env["nnUNet_preprocessed"] = str(root / "nnUNet_preprocessed")
    env["nnUNet_results"] = str(root / "nnUNet_results")
    return env


def _run(cmd: list[str], env: dict[str, str], dry_run: bool) -> None:
    print(" ".join(cmd), flush=True)
    if dry_run:
        return
    subprocess.run(cmd, env=env, check=True)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--conda-env", default="ppgl")
    parser.add_argument("--no-conda", action="store_true")
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--configuration", default=DEFAULT_CONFIGURATION)
    parser.add_argument("--fold", default=DEFAULT_FOLD)
    parser.add_argument("--dry-run", action="store_true")


def _prefix(args: argparse.Namespace) -> list[str]:
    if args.no_conda or not str(args.conda_env).strip():
        return []
    return ["conda", "run", "--no-capture-output", "-n", str(args.conda_env)]


def main() -> None:
    parser = argparse.ArgumentParser(description="OTAFV2 adrenal specialist nnU-Net wrapper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    env_parser = subparsers.add_parser("env", help="Print local nnU-Net paths.")
    _add_common_args(env_parser)

    predict_parser = subparsers.add_parser("predict", help="Run nnUNetv2_predict.")
    _add_common_args(predict_parser)
    predict_parser.add_argument("-i", "--input", required=True)
    predict_parser.add_argument("-o", "--output", required=True)
    predict_parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    predict_parser.add_argument("--num-processes-preprocessing", type=int, default=3)
    predict_parser.add_argument("--num-processes-segmentation-export", type=int, default=3)
    predict_parser.add_argument("--device", default="cuda")

    args = parser.parse_args()
    root = args.root.resolve()
    env = _nnunet_env(root)

    if args.command == "env":
        print(f"nnUNet_raw={env['nnUNet_raw']}")
        print(f"nnUNet_preprocessed={env['nnUNet_preprocessed']}")
        print(f"nnUNet_results={env['nnUNet_results']}")
        print(f"dataset_id={args.dataset_id}")
        print(f"configuration={args.configuration}")
        print(f"fold={args.fold}")
        return

    if args.command == "predict":
        cmd = _prefix(args) + [
            "nnUNetv2_predict",
            "-i",
            str(Path(args.input).resolve()),
            "-o",
            str(Path(args.output).resolve()),
            "-d",
            str(args.dataset_id),
            "-c",
            str(args.configuration),
            "-f",
            str(args.fold),
            "-chk",
            str(args.checkpoint),
            "-npp",
            str(args.num_processes_preprocessing),
            "-nps",
            str(args.num_processes_segmentation_export),
            "-device",
            str(args.device),
        ]
        _run(cmd, env=env, dry_run=bool(args.dry_run))
        return


if __name__ == "__main__":
    main()
