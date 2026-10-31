#!/usr/bin/env python3
"""Explicit work-session timer; no third-party dependencies."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.work_timer.json'
LOG = ROOT / 'docs' / 'WORK_LOG.md'
TZ = timezone(timedelta(hours=8))


def cell(text):
    return text.replace('|', '/').replace('\n', ' ')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('note', nargs='?', default='Development')
    args = parser.parse_args()
    now = datetime.now(TZ)
    state = json.loads(STATE.read_text()) if STATE.exists() else None
    if args.action == 'start':
        if state:
            parser.exit(1, 'A session is already running. Stop it first.\n')
        STATE.write_text(json.dumps({'start': now.isoformat(), 'activity': args.note}))
        print(f'Started: {now.isoformat(timespec="seconds")} — {args.note}')
    elif args.action == 'status':
        if not state:
            print('No active session.')
            return
        minutes = (now - datetime.fromisoformat(state['start'])).total_seconds() / 60
        print(f'Active: {state["activity"]}; {minutes:.1f} minutes since {state["start"]}')
    else:
        if not state:
            parser.exit(1, 'No active session.\n')
        start = datetime.fromisoformat(state['start'])
        minutes = (now - start).total_seconds() / 60
        with LOG.open('a') as out:
            out.write(f'| {start.isoformat(timespec="seconds")} | {now.isoformat(timespec="seconds")} | {minutes:.1f} | {cell(state["activity"])} | {cell(args.note)} |\n')
        STATE.unlink()
        print(f'Logged {minutes:.1f} minutes.')


if __name__ == '__main__':
    main()
