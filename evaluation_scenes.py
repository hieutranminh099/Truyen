"""Validate original Vietnamese evaluation scenes and export app-compatible outlines."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from novelengine.outline import parse_outline

DEFAULT_SCENES = Path(__file__).resolve().parent / 'evaluation' / 'scenes_vi.json'
TEXT_FIELDS = ('id', 'title', 'genre', 'setting', 'goal', 'voice')
LIST_FIELDS = ('characters', 'beats', 'required', 'withheld', 'constraints', 'criteria')


def load_scenes(path=DEFAULT_SCENES):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if (not isinstance(data, dict) or type(data.get('schema_version')) is not int
            or data['schema_version'] != 1 or not isinstance(data.get('title'), str)
            or not data['title'].strip()):
        raise ValueError('Bộ cảnh cần schema_version=1 và title')
    scenes = data.get('scenes')
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 1500:
        raise ValueError('Bộ cảnh cần 1–1500 mục trong scenes')
    seen = set()
    for index, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            raise ValueError(f'Cảnh {index} phải là object')
        for key in TEXT_FIELDS:
            value = scene.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'Cảnh {index} thiếu trường văn bản {key}')
        ident = scene['id']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', ident) or ident in seen:
            raise ValueError(f'Cảnh {index} có id không hợp lệ hoặc trùng')
        seen.add(ident)
        for key in LIST_FIELDS:
            value = scene.get(key)
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ValueError(f'Cảnh {ident} cần danh sách không rỗng {key}')
        words = scene.get('target_words')
        if type(words) is not int or not 100 <= words <= 5000:
            raise ValueError(f'Cảnh {ident} cần target_words là số nguyên từ 100 đến 5000')
    return data


def to_outline(corpus, selected=None):
    seen = {s['id'] for s in corpus['scenes']}
    if selected and set(selected) - seen:
        raise ValueError('Không tìm thấy cảnh yêu cầu trong bộ mẫu')
    chapters = []
    for scene in corpus['scenes']:
        if selected and scene['id'] not in selected:
            continue
        chapters.append({
            'id': scene['id'], 'title': scene['title'], 'purpose': scene['goal'],
            'genre': scene['genre'], 'setting': scene['setting'], 'characters': scene['characters'],
            'scenes': [{
                'id': scene['id'], 'title': scene['title'], 'goal': scene['goal'],
                'beats': scene['beats'], 'must_include': scene['required'], 'forbidden': scene['withheld'],
                'continuity_requirements': scene['constraints'], 'creative_freedom': scene['voice'],
                'target_words': scene['target_words'],
            }],
        })
    return parse_outline({'title': corpus['title'], 'schema_version': '4.0', 'chapters': chapters})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_SCENES)
    parser.add_argument('--output', type=Path, help='Tạo tệp outline JSON mới để nhập thủ công')
    parser.add_argument('--scene', action='append', help='Chọn ID cảnh, có thể lặp cờ')
    args = parser.parse_args()
    try:
        corpus = load_scenes(args.dataset)
        outline = to_outline(corpus, args.scene)
        if args.output:
            with args.output.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(outline, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        print(f"Đã xác thực {len(outline['chapters'])} cảnh.")
    except (ValueError, OSError) as exc:
        parser.exit(1, f'Không thể xử lý bộ cảnh: {exc}\n')


if __name__ == '__main__':
    main()
