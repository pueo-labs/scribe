#!/usr/bin/env bash
# Download a pinned static ffmpeg into this job's directory.
# The runner has no apt or sudo, so the coverage job cannot install a package.
set -euo pipefail

tag="autobuild-2026-11-14-12-37"
archive_name="ffmpeg-n8.1.3-35-gf1acb0a266-linux64-gpl-8.1.tar.xz"
expected_sha256="b8277443ba6332534c1cdb272f7bfa8322905f22d08208f5db0b56bc17b5fb3e"
url="https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/${tag}/${archive_name}"

root="${FFMPEG_INSTALL_DIR:-${RUNNER_TEMP:-${TMPDIR:-/tmp}}/ci-ffmpeg}"
mkdir -p "$root"
archive_path="${root}/${archive_name}"

curl --fail --location --retry 3 --retry-delay 2 --output "$archive_path" "$url"

python_bin="$(uv python find 3.14)"
bin_dir="$(
  "$python_bin" - "$archive_path" "$expected_sha256" "$root" <<'PY'
import hashlib
import lzma
import stat
import sys
import tarfile
from pathlib import Path

archive = Path(sys.argv[1])
expected = sys.argv[2]
root = Path(sys.argv[3])
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
if digest != expected:
    raise SystemExit(f"ffmpeg archive checksum mismatch: {digest}")
with lzma.open(archive, "rb") as compressed, tarfile.open(fileobj=compressed, mode="r|") as bundle:
    bundle.extractall(root, filter="data")
ffmpeg = next(path for path in root.rglob("ffmpeg") if path.is_file() and path.parent.name == "bin")
ffprobe = ffmpeg.with_name("ffprobe")
if not ffprobe.is_file():
    raise SystemExit(f"ffprobe missing next to {ffmpeg}")
for binary in (ffmpeg, ffprobe):
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print(ffmpeg.parent)
PY
)"

"$bin_dir/ffmpeg" -hide_banner -version
"$bin_dir/ffprobe" -hide_banner -version >/dev/null

if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$bin_dir" >>"$GITHUB_PATH"
fi
if [[ -n "${GITHUB_ENV:-}" ]]; then
  printf 'FFMPEG_DIR=%s\n' "$bin_dir" >>"$GITHUB_ENV"
fi
export PATH="${bin_dir}:${PATH}"
