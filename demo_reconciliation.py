"""Run two synthetic corrections, retaining before/after evidence and unchanged-source hashes."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.job_config import JobError, load_job
from src.reconcile import run_reconciliation
from src.sql_runner import write_report

ROOT = Path(__file__).resolve().parent


def source_hashes(job_path):
    job = load_job(job_path)
    return {str((job_path.parent / source['csv']).resolve()): hashlib.sha256(
        (job_path.parent / source['csv']).read_bytes()).hexdigest() for source in job['sources']}


def run_demo(output_dir):
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    cases = [('filter_mismatch', 'job-fixed-filter.json'), ('join_fanout', 'job-fixed.json')]
    results = []
    for name, corrected_name in cases:
        base = ROOT / 'samples/reconciliation' / name
        before_job, after_job = base / 'job.json', base / corrected_name
        original = source_hashes(before_job)
        same_inputs = original == source_hashes(after_job)
        before = run_reconciliation(before_job, output_dir / f'{name}-before')
        after = run_reconciliation(after_job, output_dir / f'{name}-after')
        unchanged = same_inputs and original == source_hashes(before_job) == source_hashes(after_job)
        before_detail = before.get('checkpoints', [{}])[-1].get('query_scope', {})
        after_detail = after.get('checkpoints', [{}])[-1].get('query_scope', {})
        verified = unchanged and before['status'] in ('DIFFERENT', 'AMBIGUOUS') and after['status'] == 'MATCH'
        item = {'case': name, 'verified': verified, 'source_files_unchanged': unchanged,
                'source_sha256': original,
                'before': {'status': before['status'], 'difference_cents': before_detail.get('difference_cents'),
                           'report': before['human_report']},
                'after': {'status': after['status'], 'difference_cents': after_detail.get('difference_cents'),
                          'report': after['human_report']}}
        results.append(item)
        print(f'{name}: {before["status"]} -> {after["status"]}; '
              f'difference {item["before"]["difference_cents"]} -> {item["after"]["difference_cents"]} cents; '
              f'source files unchanged={unchanged}')
    summary = {'data': 'synthetic', 'verified': all(item['verified'] for item in results), 'cases': results}
    write_report(output_dir / 'demo-summary.json', summary)
    print(f'Demo summary: {output_dir / "demo-summary.json"}')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    output = args.output_dir or ROOT / 'outputs' / ('correction-demo-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    try:
        summary = run_demo(output)
    except (OSError, JobError) as error:
        print(f'DEMO ERROR: {error}', file=sys.stderr)
        return 2
    return 0 if summary['verified'] else 2


if __name__ == '__main__':
    sys.exit(main())
