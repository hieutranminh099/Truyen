"""Isolated Windows/Ollama acceptance harness with an offline HTTP fixture."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen


class OllamaFixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.server.fail:
            self.send_error(503)
            return
        system = payload['messages'][0]['content']
        if payload.get('format') == 'json':
            if 'Bạn là thư ký theo dõi' in system:
                text = json.dumps({'summary': 'An đem chiếc chuông từ bến đò về nhà.', 'proposals': []})
            else:
                text = json.dumps({
                    'critical': [], 'style': [], 'missing': [], 'strengths': [], 'fixes': [],
                })
        elif 'Chỉnh những câu' in system:
            text = ('An đặt chuông lên bàn. Ngoài cửa, tiếng mưa đã ngớt. ' * 28).strip()
        else:
            text = ('An nghe tiếng chuông đồng gỉ ở bến đò rồi bước xuống thuyền. ' * 24).strip()
        body = json.dumps({'message': {'content': text}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def probe(base, route):
    with urlopen(base + route, timeout=5) as response:
        return json.load(response)


def gpu_info():
    executable = shutil.which('nvidia-smi')
    if not executable:
        return 'nvidia-smi không có'
    try:
        result = subprocess.run(
            [executable, '--query-gpu=name,driver_version,memory.total,memory.used',
             '--format=csv,noheader'], check=True, capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 'Không đọc được thông số NVIDIA'


def run(real, data_dir):
    # Set before importing the application, which resolves DATA_ROOT at import.
    os.environ.update(NOVEL_DATA_DIR=data_dir, NOVEL_CLOUD_ENABLED='0', NOVEL_HOST='127.0.0.1')
    from novelengine.ai import AI
    from novelengine.config import Settings
    from novelengine.jobs import JobQueue
    from novelengine.outline import sample_outline
    from novelengine.store import bootstrap, save_outline

    settings = Settings()
    real_url = settings.ollama_url
    if real:
        if settings.model not in {x.get('name') for x in probe(real_url, '/api/tags')['models']}:
            raise ValueError('Ollama chưa có mô hình được chọn trong NOVEL_MODEL')

    bootstrap()
    outline = sample_outline()
    outline['chapters'] = outline['chapters'][:1]
    outline['chapters'][0]['scenes'] = outline['chapters'][0]['scenes'][:1]
    save_outline('demo', outline)

    fixture = ThreadingHTTPServer(('127.0.0.1', 0), OllamaFixture)
    fixture.fail = True
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    settings.ollama_url = f'http://127.0.0.1:{fixture.server_port}'
    queue = JobQueue(AI(settings), poll=.05)
    try:
        queue.start()
        job = queue.submit('demo', 'series')

        def wait_for(state, timeout):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                row = next(row for row in queue.list('demo') if row['id'] == job)
                if row['state'] == state:
                    return row
                if row['state'] == 'failed':
                    raise RuntimeError('Tác vụ thất bại khi phục hồi: ' + row['error'])
                time.sleep(.1)
            raise TimeoutError(f'Tác vụ chưa đạt trạng thái {state}')

        if '503' not in wait_for('failed', 30)['error']:
            raise RuntimeError('Chưa xác nhận được lỗi Ollama mô phỏng')
        fixture.fail = False
        if real:
            settings.ollama_url = real_url
        started = time.monotonic()
        queue.command(job, 'resume')
        wait_for('waiting_approval', 7500 if real else 30)
        elapsed = round(time.monotonic() - started, 2)
        project = Path(data_dir) / 'projects' / 'demo'
        database = sqlite3.connect(project / 'story.db')
        try:
            scenes = database.execute('SELECT draft, review, edited FROM scenes WHERE stage=?',
                                      ('edited',)).fetchall()
            versions = database.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0]
        finally:
            database.close()
        markdown = (project / 'exports' / 'chapter_001.md').read_text(encoding='utf-8')
        if len(scenes) != 1 or not all(scenes[0]) or versions != 2 or scenes[0][2].strip() not in markdown:
            raise RuntimeError('Thiếu checkpoint Writer/Critic/Editor, phiên bản hoặc Markdown')
        return {'mode': 'ollama_thật' if real else 'giả_lập_http', 'os': platform.platform(),
                'python': platform.python_version(), 'gpu': gpu_info(), 'model': settings.model if real else None,
                'context': settings.ctx, 'token_limit': settings.tokens, 'seconds_including_summary': elapsed,
                'edited_words': len(scenes[0][2].split()), 'provider_failure_and_resume': True,
                'saved_versions': versions, 'markdown_verified': True}
    finally:
        queue.shutdown()
        fixture.shutdown()
        fixture.server_close()
        thread.join()


def main():
    parser = argparse.ArgumentParser(description='Smoke test cách ly cho Novel Engine')
    parser.add_argument('--real', action='store_true', help='Dùng Ollama thật sau lỗi HTTP giả lập có kiểm soát')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.exit(1, 'Cần Python 3.10 trở lên.\n')
    try:
        with tempfile.TemporaryDirectory(prefix='novel-smoke-') as data_dir:
            report = run(args.real, data_dir)
    except (ValueError, RuntimeError, OSError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f'Nghiệm thu không đạt ({type(exc).__name__}). Kiểm tra cấu hình, mô hình và Ollama.\n')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
