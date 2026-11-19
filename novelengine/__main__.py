"""python -m novelengine: launch UI or run maintenance commands."""
import argparse
from pathlib import Path
from .config import Settings,project_dir
from .store import bootstrap,create_project,projects,story_db,export_chapter
from .outline import load_outline
from .server import serve


def main():
    p=argparse.ArgumentParser(description='Novel Engine Hybrid V4 Preview')
    sub=p.add_subparsers(dest='cmd')
    sub.add_parser('serve')
    x=sub.add_parser('create');x.add_argument('title');x.add_argument('--id',default='')
    sub.add_parser('projects')
    e=sub.add_parser('export');e.add_argument('project');e.add_argument('--chapter',default='')
    s=sub.add_parser('secrets')
    args=p.parse_args()
    bootstrap()
    if args.cmd in (None,'serve'):serve()
    elif args.cmd=='create':print(create_project(args.title,args.id))
    elif args.cmd=='projects':print(*projects(),sep='\n')
    elif args.cmd=='secrets':
        x=Settings();print('Web token:',x.browser_token);print('Gateway API key:',x.gateway_token)
    elif args.cmd=='export':
        outline=load_outline(project_dir(args.project)/'outline.json')
        for ch in outline['chapters']:
            if not args.chapter or args.chapter==ch['id']:print(export_chapter(args.project,ch))
if __name__=='__main__':main()
