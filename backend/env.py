import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = Path(os.getenv("REELPICK_ENV_FILE", str(ROOT / ".env")))


def load_env_file(path: Path = ENV_FILE) -> None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in raw.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        entry = entry.removeprefix("export ").strip()
        key, separator, value = entry.partition("=")
        if not separator:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
