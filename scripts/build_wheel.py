"""Build this checkout with its locked project build tools, without global pip."""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import shutil
import sys
import tomllib
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from video_chronicle.process_control import ProcessControlError, run_managed_command

ROOT = Path(__file__).resolve().parents[1]


def build(out_dir: Path, *, offline: bool) -> Path:
    if sys.prefix == sys.base_prefix:
        raise ValueError("run from the locked project virtual environment")
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    for name in ("setuptools", "wheel"):
        versions = [item["version"] for item in lock["package"] if item["name"] == name]
        if len(versions) != 1 or importlib.metadata.version(name) != versions[0]:
            raise ValueError(
                f"{name} must match uv.lock; run uv sync --locked --extra dev"
            )
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("canonical uv executable is required")
    # --project avoids depending on the shell's working directory or another
    # project's lock. The build itself uses this same explicit interpreter.
    checked = run_managed_command(
        [uv, "lock", "--check", "--offline", "--project", str(ROOT)],
        cancellation=None,
        timeout=60,
        max_output_bytes=1024 * 1024,
    )
    if checked.returncode != 0:
        raise ValueError("manifest and uv.lock are inconsistent")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.glob("video_chronicle-*.whl")):
        raise ValueError(
            "output already contains a project wheel; choose a fresh directory"
        )
    # Same-filesystem private staging: no failed build can publish a partial wheel.
    with TemporaryDirectory(prefix=".wheel-build-", dir=out_dir) as private:
        stage = Path(private)
        command = [
            uv,
            "build",
            str(ROOT),
            "--wheel",
            "--no-build-isolation",
            "--python",
            sys.executable,
            "--out-dir",
            str(stage),
        ]
        if offline:
            command.append("--offline")
        result = run_managed_command(
            command,
            cancellation=None,
            timeout=180,
            max_output_bytes=1024 * 1024,
        )
        if result.returncode != 0:
            raise ValueError(
                "wheel build failed: " + (result.stderr + result.stdout)[-2000:]
            )
        wheels = list(stage.glob("video_chronicle-*.whl"))
        if len(wheels) != 1 or wheels[0].is_symlink() or not wheels[0].is_file():
            raise ValueError("build did not produce exactly one regular project wheel")
        try:
            with zipfile.ZipFile(wheels[0]) as archive:
                if archive.testzip() is not None or not archive.namelist():
                    raise ValueError("wheel archive integrity check failed")
        except zipfile.BadZipFile as error:
            raise ValueError("build produced an invalid wheel archive") from error
        final = out_dir / wheels[0].name
        # link is atomic and fails if final exists (including a racing writer).
        os.link(wheels[0], final)
        return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        wheel = build(args.out_dir, offline=args.offline)
    except (
        ValueError,
        importlib.metadata.PackageNotFoundError,
        OSError,
        ProcessControlError,
    ) as error:
        parser.exit(2, f"build error: {error}\n")
    print(wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
