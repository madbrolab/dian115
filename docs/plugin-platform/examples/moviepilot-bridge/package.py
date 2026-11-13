"""Build only the MoviePilot plugin source; never include local test artifacts."""
import hashlib
from pathlib import Path
import sys
import zipfile

target = Path(sys.argv[1])
source = Path(__file__).parent / "plugins.v2/dian115bridge/__init__.py"
entry = zipfile.ZipInfo("dian115bridge/__init__.py", date_time=(2026, 11, 12, 0, 0, 0))
entry.compress_type = zipfile.ZIP_DEFLATED
entry.external_attr = 0o644 << 16
with zipfile.ZipFile(target, "x") as archive:
    archive.writestr(entry, source.read_bytes())
print(f"SHA256 {hashlib.sha256(target.read_bytes()).hexdigest()}  {target}")
