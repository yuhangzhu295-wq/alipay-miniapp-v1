#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
python_bin="${ALIPAY_STAGING_PYTHON:-${root_dir}/.venv/bin/python}"

if [[ ! -x "${python_bin}" ]]; then
  echo "ALIPAY_STAGING_PYTHON is not executable: ${python_bin}" >&2
  exit 1
fi

exec "${python_bin}" -m uvicorn main:app --host 127.0.0.1 --port "${PORT:-18001}"
