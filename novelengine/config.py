"""Runtime configuration. Secrets never go to the browser or project DB."""
from __future__ import annotations
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.environ.get('NOVEL_DATA_DIR', str(ROOT / 'data'))).expanduser().resolve()
PROJECTS = DATA_ROOT / 'projects'
PROJECT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,48}$')
MAX_JSON_BYTES = 2_000_000
MAX_UPLOAD_BYTES = 8_000_000


def slug(value: str) -> str:
    value = re.sub(r'[^a-zA-Z0-9_-]+', '-', value.strip()).strip('-').lower()[:48]
    if not PROJECT_ID_PATTERN.fullmatch(value):
        raise ValueError('ID dự án chỉ gồm chữ cái ASCII, số, gạch ngang, gạch dưới.')
    return value


def validate_project_id(value: str) -> str:
    if not PROJECT_ID_PATTERN.fullmatch(str(value)):
        raise ValueError('ID dự án không hợp lệ')
    return str(value)


def project_dir(project_id: str) -> Path:
    return PROJECTS / validate_project_id(project_id)


def secret(name: str) -> str:
    """Generate a private random credential on first launch, with restrictive POSIX perms."""
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    path = DATA_ROOT / name
    if path.is_file():
        token = path.read_text(encoding='utf8').strip()
        if len(token) < 30:
            raise RuntimeError(f'Mã bảo mật trong {path} quá ngắn')
        return token
    token = secrets.token_urlsafe(32)
    # Exclusive create makes first startup race-safe.
    try:
        with path.open('x', encoding='utf8') as f:
            f.write(token + '\n')
        try: path.chmod(0o600)
        except OSError: pass
        return token
    except FileExistsError:
        return path.read_text(encoding='utf8').strip()


def env_bool(key: str, default: bool = False) -> bool:
    v = os.environ.get(key)
    return default if v is None else v.lower() in ('1', 'true', 'yes', 'on')


def validate_provider_url(value, *, cloud=False):
    parts = urlsplit(value)
    port = parts.port  # Reject malformed and out-of-range ports.
    loopback = parts.hostname in {'127.0.0.1', 'localhost', '::1'}
    if (parts.scheme not in {'http', 'https'} or not parts.hostname or port == 0
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment):
        raise ValueError('URL nhà cung cấp không hợp lệ')
    if cloud and parts.scheme != 'https' and not loopback:
        raise ValueError('Cloud API phải dùng HTTPS, ngoại trừ proxy loopback')


class Settings:
    def __init__(self):
        self.host = os.environ.get('NOVEL_HOST', '127.0.0.1')
        self.port = int(os.environ.get('NOVEL_PORT', '8765'))
        self.model = os.environ.get('NOVEL_MODEL', 'qwen3:8b')
        self.embed_model = os.environ.get('NOVEL_EMBED_MODEL', 'qwen3-embedding:0.6b')
        self.ollama_url = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
        self.ctx = max(2048, min(32768, int(os.environ.get('NOVEL_CTX', '4096'))))
        self.tokens = max(256, min(8192, int(os.environ.get('NOVEL_TOKENS', '1300'))))
        self.cloud_enabled = env_bool('NOVEL_CLOUD_ENABLED')
        self.cloud_url = os.environ.get('NOVEL_CLOUD_URL', '').rstrip('/')
        self.cloud_model = os.environ.get('NOVEL_CLOUD_MODEL', '')
        self.cloud_key = os.environ.get('NOVEL_CLOUD_API_KEY', '')
        self.cloud_timeout = int(os.environ.get('NOVEL_CLOUD_TIMEOUT', '180'))
        if self.host not in ('127.0.0.1', '::1', 'localhost'):
            if not env_bool('NOVEL_ALLOW_LAN'):
                raise RuntimeError('Không cho phép bind mạng ngoài localhost. Cần NOVEL_ALLOW_LAN=1 nếu thực sự chủ động mở LAN.')
        if not 1 <= self.port <= 65535 or self.cloud_timeout < 1:
            raise ValueError('Cổng hoặc thời gian chờ không hợp lệ')
        validate_provider_url(self.ollama_url)
        if self.cloud_enabled:
            validate_provider_url(self.cloud_url, cloud=True)
            if not self.cloud_model or not self.cloud_key:
                raise RuntimeError('Cloud API thiếu NOVEL_CLOUD_MODEL hoặc NOVEL_CLOUD_API_KEY')

        self.browser_token = secret('browser_token.txt')
        self.gateway_token = secret('gateway_token.txt')

    def info(self) -> dict:
        return {'model': self.model, 'embed_model': self.embed_model,
                'ctx': self.ctx, 'tokens': self.tokens,
                'cloud_enabled': self.cloud_enabled, 'cloud_model': self.cloud_model if self.cloud_enabled else None,
                'host': self.host, 'port': self.port}
