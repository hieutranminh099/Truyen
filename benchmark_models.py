"""Blind Vietnamese fiction benchmark with human scoring and JSON/CSV reports."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import platform
import random
import re
import statistics
import time
from pathlib import Path
from urllib.request import urlopen

from novelengine.ai import AI
from novelengine.config import Settings, project_dir
from novelengine.outline import load_outline
from novelengine.pipeline import SYSTEM_WRITER, scene_packet
from novelengine.store import atomic_text

CRITERIA = ('tieng_viet', 'loi_thoai', 'tam_ly', 'nhan_qua', 'sang_tao', 'bam_dan_y', 'tranh_lap_sao_ngu')
TEMPERATURE = .8


def write_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def loaded_vram(base, model):
    try:
        with urlopen(base + '/api/ps', timeout=3) as response:
            models = json.load(response)['models']
        return next((row.get('size_vram') for row in models if row.get('name') == model), None)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def run_benchmark(project, models, count, seed, mock=False, output=None):
    directory = project_dir(project)
    outline = load_outline(directory / 'outline.json')
    scenes = [(chapter, scene) for chapter in outline['chapters'] for scene in chapter['scenes']]
    root = (output or directory / 'benchmarks') / dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    root.mkdir(parents=True, exist_ok=False)
    settings = Settings()
    settings.seed = seed
    ai = AI(settings)
    order = models[:]
    random.Random(seed).shuffle(order)
    masks = re.compile('|'.join(re.escape(model) for model in sorted(models, key=len, reverse=True)), re.I)
    samples, sheets = [], []
    for index, (chapter, scene) in enumerate(scenes[:count], 1):
        packet, _ = scene_packet(project, outline, chapter, scene)
        prompt = packet + '\nViết cảnh này dưới dạng văn xuôi tiếng Việt, chỉ xuất bản thảo.'
        digest = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
        rotation = (index - 1) % len(order)
        for position, model in enumerate(order[rotation:] + order[:rotation]):
            label = chr(65 + position)
            settings.model = model
            start = time.monotonic()
            if mock:
                prose = 'Dữ liệu mô phỏng cho kiểm tra định dạng. An đứng im bên bến đò.'
            else:
                prose = ai.chat(SYSTEM_WRITER, prompt, role='writer',
                                temperature=TEMPERATURE, max_tokens=settings.tokens)
            seconds = round(time.monotonic() - start, 4)
            draft = masks.sub('[tên mô hình đã ẩn]', prose)
            atomic_text(root / f'canh_{index:02d}_{label}.md', f'# Cảnh {index} — Bản {label}\n\n{draft}\n')
            samples.append({'scene': index, 'label': label, 'model': model,
                            'chapter_id': chapter['id'], 'scene_id': scene['id'], 'prompt_sha256': digest,
                            'seconds': seconds, 'words': len(prose.split()),
                            'vram_bytes': None if mock else loaded_vram(settings.ollama_url, model)})
            sheets.append({'scene': index, 'label': label, 'rater': '',
                           **dict.fromkeys(CRITERIA, '')})
    metadata = {'mode': 'mock' if mock else 'ollama', 'platform': platform.platform(),
                'python': platform.python_version(), 'seed': seed, 'temperature': TEMPERATURE,
                'context': settings.ctx, 'max_tokens': settings.tokens, 'samples': samples}
    atomic_text(root / 'bang_dap_an_RIENG.json', json.dumps(metadata, ensure_ascii=False, indent=2))
    write_csv(root / 'samples_RIENG.csv', list(samples[0]), samples)
    write_csv(root / 'scores.csv', ['scene', 'label', 'rater', *CRITERIA], sheets)
    atomic_text(root / 'DO_DANH_GIA.md',
                '# Phiếu đọc mù\n\nChấm 1–5 trong scores.csv theo docs/MODEL_BENCHMARK.md. '
                'Chỉ gửi tệp cảnh và phiếu điểm cho người đọc. Giữ riêng các tệp có chữ RIENG.\n')
    return root


def summarize(folder, scores_path):
    key = json.loads((folder / 'bang_dap_an_RIENG.json').read_text(encoding='utf-8'))
    models = {(row['scene'], row['label']): row['model'] for row in key['samples']}
    scene_scores = {}
    seen = set()
    with scores_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not set(['scene', 'label', 'rater', *CRITERIA]).issubset(reader.fieldnames or []):
            raise ValueError('Phiếu điểm thiếu cột bắt buộc')
        for line, row in enumerate(reader, 2):
            values = [(row[name] or '').strip() for name in CRITERIA]
            if not any(values):
                continue
            try:
                scene, label = int(row['scene']), row['label'].strip()
                rater = (row['rater'] or '').strip()
                model = models[(scene, label)]
                points = [int(value) for value in values]
                if not rater or not all(1 <= point <= 5 for point in points):
                    raise ValueError
            except (KeyError, AttributeError, TypeError, ValueError):
                raise ValueError(f'Phiếu điểm không hợp lệ ở dòng {line}') from None
            if (scene, label, rater) in seen:
                raise ValueError(f'Phiếu điểm trùng ở dòng {line}')
            seen.add((scene, label, rater))
            scene_scores.setdefault((model, scene), []).append(points)
    if not scene_scores:
        raise ValueError('Chưa có điểm do người đọc nhập')
    common = set.intersection(*(
        {scene for candidate, scene in scene_scores if candidate == model}
        for model in sorted(set(models.values()))
    ))
    if not common:
        raise ValueError('Cần chấm ít nhất một cảnh chung cho mọi mô hình')
    rows = []
    for model in sorted(set(models.values())):
        samples = [scene_scores[model, scene] for scene in sorted(common)]
        for index, criterion in enumerate(CRITERIA):
            points = [statistics.mean(scores[index] for scores in scene) for scene in samples]
            rows.append({'model': model, 'criterion': criterion, 'scenes': len(points),
                         'ratings': sum(map(len, samples)), 'mean': round(statistics.mean(points), 4),
                         'stdev': round(statistics.stdev(points), 4) if len(points) > 1 else None})
    atomic_text(folder / 'summary_RIENG.json', json.dumps(
        {'mode': key['mode'], 'score_source': 'human', 'paired_scenes': sorted(common), 'results': rows},
        ensure_ascii=False, indent=2,
    ))
    write_csv(folder / 'summary_RIENG.csv', list(rows[0]), rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='demo')
    parser.add_argument('--models', default='qwen3:8b,qwen3.5:4b')
    parser.add_argument('--scenes', type=int, default=5)
    parser.add_argument('--seed', type=int, default=457191)
    parser.add_argument('--mock', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--summarize', type=Path, metavar='RUN_DIR')
    parser.add_argument('--scores', type=Path, help='CSV đã chấm, mặc định RUN_DIR/scores.csv')
    args = parser.parse_args()
    try:
        if args.summarize:
            summarize(args.summarize, args.scores or args.summarize / 'scores.csv')
            print(args.summarize / 'summary_RIENG.json')
            return
        models = [value.strip() for value in args.models.split(',') if value.strip()]
        if not 2 <= len(models) <= 26 or len({m.casefold() for m in models}) != len(models):
            raise ValueError('Cần 2–26 mô hình khác nhau')
        if not 1 <= args.scenes <= 20000 or not 0 <= args.seed <= 2_147_483_647:
            raise ValueError('Số cảnh hoặc seed ngoài phạm vi')
        print(run_benchmark(args.project, models, args.scenes, args.seed, args.mock, args.output))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f'Benchmark chưa hoàn tất ({type(exc).__name__}): {exc}\n')


if __name__ == '__main__':
    main()
