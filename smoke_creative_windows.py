"""Isolated Creative runtime smoke: offline by default, --real uses local Ollama.

Never reads or writes a live NOVEL_DATA_DIR. Works on Windows and Ubuntu.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing


class FixtureAI:
    def __init__(self):
        self.settings = type('SettingsFixture', (), {'tokens': 1700, 'ctx': 4096})()
        self.roles = []

    def chat(self, system, user, **kwargs):
        role = kwargs.get('role', 'writer')
        self.roles.append(role)
        if role == 'critic':
            return json.dumps({'critical': [], 'style': [], 'missing': [],
                               'strengths': [], 'fixes': []})
        if role == 'summary':
            return json.dumps({'summary': 'An nghe tiếng chuông ở bến đò.',
                               'proposals': []})
        if role == 'editor':
            return ('An giữ chuông đồng gỉ và quan sát mặt nước lặng. '
                    'Tiếng mưa rơi xuống bến đò, để lại dư âm cũ. ') * 45
        return ('An nghe tiếng chuông đồng gỉ vang từ bến đò. '
                'Cô đứng trong mưa, ngập ngừng trước ký ức đã mất. ') * 48


def run(*, real: bool):
    with tempfile.TemporaryDirectory(prefix='novel-creative-smoke-') as root, \
         tempfile.TemporaryDirectory(prefix='novel-creative-restore-') as restore_root:
        os.environ['NOVEL_DATA_DIR'] = root
        os.environ['NOVEL_CLOUD_ENABLED'] = '0'
        os.environ['NOVEL_HOST'] = '127.0.0.1'
        from novelengine.config import Settings, project_dir
        from novelengine.store import bootstrap
        from novelengine.project_state import enable_creative
        from novelengine.creative_runtime import creative_propose, creative_action, creative_packet
        from novelengine.pipeline import process_scene
        from novelengine.outline import load_outline
        from novelengine.project_backup import create_backup, restore_backup

        bootstrap()
        pid = 'demo'
        enable_creative(pid)
        state = creative_propose(pid, {
            'kind': 'canon', 'subject': 'bell', 'value': 'An từng nghe tiếng chuông.',
        })
        creative_action(pid, {'event_id': state['id'], 'action': 'approve'})
        link = creative_propose(pid, {
            'kind': 'knowledge', 'subject': 'An', 'key': 'bell', 'value': 'known',
            'evidence': 'Dữ kiện được người biên tập xác nhận.',
        })
        creative_action(pid, {'event_id': link['id'], 'action': 'approve'})
        outline = load_outline(project_dir(pid) / 'outline.json')
        chapter = outline['chapters'][0]
        scene = chapter['scenes'][0]
        packet, _, revision = creative_packet(pid, outline, chapter, scene)
        if 'An từng nghe tiếng chuông.' not in packet or revision != 4:
            raise RuntimeError('Creative Memory không vào packet hợp lệ.')
        another = json.loads(json.dumps(outline))
        another['chapters'][0]['scenes'][0]['pov'] = 'Linh'
        if 'An từng nghe tiếng chuông.' in creative_packet(
                pid, another, another['chapters'][0], another['chapters'][0]['scenes'][0])[0]:
            raise RuntimeError('Rò rỉ thông tin giữa các nhân vật POV.')
        if real:
            from novelengine.ai import AI
            ai = AI(Settings())
        else:
            ai = FixtureAI()
        result = process_scene(pid, outline, chapter, scene, ai)
        archive = project_dir(pid) / 'backups' / create_backup(pid)
        recovered = restore_backup(archive, pid, data_root=Path(restore_root))
        with closing(sqlite3.connect(Path(restore_root) / 'projects' / pid / 'story.db')) as db:
            count = db.execute('SELECT COUNT(*) FROM scene_versions').fetchone()[0]
        if count != 2 or recovered['ledger_revision'] != 4:
            raise RuntimeError('Mất phiên bản cảnh hoặc revision ledger khi restore.')
        return {
            'mode': 'Qwen/Ollama thật' if real else 'FixtureAI offline',
            'data_isolated': True, 'pov_secrecy': True, 'writer_roles': ai.roles if not real else None,
            'edited_words': result['words'], 'scene_versions': count,
            'ledger_revision_restored': recovered['ledger_revision'],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--real', action='store_true',
                        help='Chạy model Ollama thật trong dữ liệu TEMP, không đụng dự án thật.')
    args = parser.parse_args()
    try:
        print(json.dumps(run(real=args.real), ensure_ascii=False, indent=2))
    except Exception as exc:
        parser.exit(1, f'Creative smoke FAILED: {type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
