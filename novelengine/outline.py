"""Outline schema v4 and compatibility with V2/V3 scene IDs."""
from __future__ import annotations
import json
from pathlib import Path

MAX_CHAPTERS = 1500
MAX_SCENES_PER_CHAPTER = 100


def parse_outline(data: dict | str) -> dict:
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise ValueError('Dàn ý phải là JSON object')
    chapters = data.get('chapters')
    if not isinstance(chapters, list) or not (1 <= len(chapters) <= MAX_CHAPTERS):
        raise ValueError('Dàn ý cần chapters[] không rỗng (tối đa 1500)')
    chapter_ids = set()
    total = 0
    for ch in chapters:
        if not isinstance(ch, dict) or not isinstance(ch.get('scenes'), list):
            raise ValueError('Mỗi chương phải có scenes[]')
        ch['id'] = str(ch.get('id', '')).strip()
        if not ch['id'] or len(ch['id']) > 80 or not ch.get('title'):
            raise ValueError('Chương cần id và title')
        if ch['id'] in chapter_ids:
            raise ValueError('Trùng id chương: ' + ch['id'])
        chapter_ids.add(ch['id'])
        scenes = ch['scenes']
        if not (1 <= len(scenes) <= MAX_SCENES_PER_CHAPTER):
            raise ValueError(f'Chương {ch["id"]} cần 1–100 cảnh')
        seen = set()
        for s in scenes:
            if not isinstance(s, dict):
                raise ValueError('Cảnh phải là JSON object')
            s['id'] = str(s.get('id', s.get('scene_id', ''))).strip()
            if not s['id'] or len(s['id']) > 80 or not s.get('goal'):
                raise ValueError(f'Cảnh chương {ch["id"]} thiếu id hoặc goal')
            beats = s.get('beats')
            if not isinstance(beats, list) or not beats or any(not isinstance(x, str) or not x.strip() for x in beats):
                raise ValueError(f'Cảnh {s["id"]} phải có beats[] (các bước diễn biến)')
            for k in ('must_include', 'forbidden', 'continuity_requirements'):
                if k in s and (not isinstance(s[k], list) or not all(isinstance(x, str) for x in s[k])):
                    raise ValueError(f'{k} phải là mảng chuỗi')
            if s['id'] in seen:
                raise ValueError(f'Trùng id cảnh {s["id"]} trong chương {ch["id"]}')
            seen.add(s['id'])
            total += 1
    if total > 20000:
        raise ValueError('Dàn ý quá lớn')
    data.setdefault('schema_version', '4.0')
    return data


def sample_outline() -> dict:
    return {'schema_version': '4.0', 'story_id': 'duong_ve', 'title': 'Người Giữ Những Mùa Mưa',
            'genre': 'Huyền bí / tâm lý', 'premise': 'Một thị trấn nơi người ta có thể đánh mất một phần ký ức vào những ngày mưa.',
            'world': 'Thị trấn ven núi, thời hiện đại. Không ai được chủ động lấy ký ức người khác nếu không có nghi lễ.',
            'characters': [{'name': 'An', 'traits': 'quan sát, kín đáo', 'secret': 'từng tham gia một nghi lễ đã quên'}],
            'chapters': [
                {'id': '001', 'title': 'Dấu nước', 'purpose': 'Gieo bí mật về ký ức', 'scenes': [
                    {'id': '01', 'title': 'Bến đò cuối chiều', 'pov': 'An', 'goal': 'An phát hiện một chỗ trống trong ký ức',
                     'beats': ['An về thị trấn sau nhiều năm', 'Người chèo đò nói một câu quá quen', 'An nhận ra không nhớ giọng của mẹ'],
                     'must_include': ['chuông đồng gỉ'], 'forbidden': ['Nội dung nghi lễ ký ức'],
                     'emotional_arc': 'thờ ơ → bất an', 'target_words': 350, 'creative_freedom': 'Tự sáng tạo lời thoại, cử chỉ và nhịp kể.'},
                    {'id': '02', 'title': 'Căn nhà đóng cửa', 'pov': 'An', 'goal': 'An tìm manh mối',
                     'beats': ['An trở về căn nhà cũ', 'Phát hiện vết nước trên tường', 'Một mẩu giấy mới được đặt vào hộp thư'],
                     'must_include': ['mẩu giấy không có tên'], 'forbidden': ['Tiết lộ thủ phạm'], 'target_words': 350}
                ]},
                {'id': '002', 'title': 'Người đến sau cơn mưa', 'scenes': [
                    {'id': '01', 'title': 'Gặp lại', 'pov': 'An', 'goal': 'An đối diện người bạn cũ',
                     'beats': ['An gặp Linh trong quán trà', 'Linh biết nhiều hơn những gì cô thừa nhận', 'An nghe thấy tiếng chuông'],
                     'forbidden': ['Nội dung nghi lễ ký ức'], 'target_words': 400}
                ]}
            ]}


def load_outline(path: Path) -> dict:
    return parse_outline(path.read_text(encoding='utf-8-sig'))
