import os
from pathlib import Path

def _load_env_file():
    """Load .env from project root without external dependencies."""
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _require_token(env_var_name):
    token = os.getenv(env_var_name, "").strip()
    if token:
        return token

    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"
    raise RuntimeError(
        f"Required environment variable {env_var_name} is missing. "
        f"Set it in shell or in {env_path}."
    )


_load_env_file()
DISCORD_TOKEN = _require_token("DISCORD_TOKEN")
TELEGRAM_TOKEN = _require_token("TELEGRAM_TOKEN")