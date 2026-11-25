#!/bin/sh
# Run explicitly when upgrading dependencies, not on the small deployment host.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
cd "$root"
temporary=$(mktemp)
trap 'rm -f "$temporary"' EXIT INT TERM
uv pip compile requirements.txt backend/requirements-api.txt \
  --python-version 3.14.10 --python-platform x86_64-unknown-linux-gnu \
  --only-binary :all: --torch-backend cpu --generate-hashes --emit-index-url \
  --quiet -o "$temporary"
# The CPU index is required by pip as well as uv. Every distribution is pinned
# and hash-checked, so the supplemental index cannot change package contents.
python3 - "$temporary" <<'PY'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text()
text = text.replace('--index-url https://pypi.org/simple',
    '--index-url https://pypi.org/simple\n--extra-index-url https://download.pytorch.org/whl/cpu\n--only-binary :all:')
Path('deploy/aws/image/requirements-linux-cpu.lock').write_text(text)
PY
