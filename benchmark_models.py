"""Blind comparison of writer models on identical scene packets; never touches canonical scenes.

Example: python benchmark_models.py --project demo --models qwen3:8b,qwen3.5:4b --scenes 5
Outputs samples A/B in data/projects/<id>/benchmarks/<timestamp>/ and private answer key.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import random
import time
from pathlib import Path
from novelengine.config import Settings,project_dir
from novelengine.outline import load_outline
from novelengine.pipeline import SYSTEM_WRITER,scene_packet
from novelengine.ai import AI
from novelengine.store import atomic_text


def main():
    p=argparse.ArgumentParser(description='Blind A/B test for local Vietnamese fiction writers.')
    p.add_argument('--project',default='demo')
    p.add_argument('--models',default='qwen3:8b,qwen3.5:4b',help='Comma-separated Ollama models')
    p.add_argument('--scenes',type=int,default=5)
    args=p.parse_args()
    models=[x.strip() for x in args.models.split(',') if x.strip()]
    if len(models)<2 or len(set(models))!=len(models): p.error('Cần ít nhất 2 model khác nhau')
    d=project_dir(args.project)
    outline=load_outline(d/'outline.json')
    scenes=[(c,s) for c in outline['chapters'] for s in c['scenes']][:max(1,min(args.scenes,30))]
    root=d/'benchmarks'/dt.datetime.now().strftime('%Y%m%d_%H%M%S');root.mkdir(parents=True,exist_ok=False)
    s=Settings();ai=AI(s)
    key=[]
    rng=random.Random(457191)
    for i,(ch,sc) in enumerate(scenes,1):
        packet,_=scene_packet(args.project,outline,ch,sc,ai=None,use_embeddings=False)
        order=models[:];rng.shuffle(order)
        for n,model in enumerate(order):
            code=chr(65+n)
            s.model=model
            t0=time.monotonic()
            prose=ai.chat(SYSTEM_WRITER,packet+'\nViết cảnh này dưới dạng văn xuôi tiếng Việt, chỉ xuất bản thảo.',
                          role='writer',temperature=.8,max_tokens=s.tokens)
            duration=round(time.monotonic()-t0,2)
            atomic_text(root/f'canh_{i:02d}_{code}.md',f'# Cảnh {i} — Bản {code}\n\n'+prose+'\n')
            key.append({'scene':i,'label':code,'model':model,'seconds':duration,'words':len(prose.split())})
            print(f'Cảnh {i}, bản {code}: {len(prose.split())} từ, {duration}s')
    atomic_text(root/'DO_DANH_GIA.md', '# Phiếu đọc mù\n\nChấm mỗi bản 1–5 theo: giọng văn tự nhiên, lời thoại, tâm lý, nhân quả, tính mới, bám dàn ý.\n\nĐọc các tệp canh_XX_A/B trước khi mở bang_dap_an_RIENG.json.\n')
    atomic_text(root/'bang_dap_an_RIENG.json',json.dumps(key,ensure_ascii=False,indent=2))
    print('Kết quả:',root)
if __name__=='__main__':main()
