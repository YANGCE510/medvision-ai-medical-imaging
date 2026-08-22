from pathlib import Path
import subprocess
import sys


def run_single_case(
    input_path: str,
    output_dir: str,
    device: str = "cuda",
    gcp_amp: bool = True,
    allow_tf32: bool = True,
    gcp_backend: str = "torch",
    gcp_engine: str = "",
):
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    cmd = [
        sys.executable,
        "run_otafv2.py",
        "--input",
        str(input_path),
        "--output",
        str(output_dir),
        "--device",
        device,
        "--gcp-backend",
        gcp_backend,
    ]
    if gcp_amp:
        cmd.append("--gcp-amp")
    else:
        cmd.append("--no-gcp-amp")
    if allow_tf32:
        cmd.append("--allow-tf32")
    else:
        cmd.append("--no-allow-tf32")
    if str(gcp_engine).strip():
        cmd += ["--gcp-engine", str(gcp_engine)]

    result = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Segmentation failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    return {
        "output_dir": str(output_dir)
    }
