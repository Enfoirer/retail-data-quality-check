"""Build an explicit, hashed submission package without copying local working files."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def package(root, destination):
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    manifest = json.loads((root / 'submission_manifest.json').read_text(encoding='utf-8'))
    names = manifest['files']
    if manifest.get('schema_version') != 1 or not isinstance(names, list) or not names:
        raise ValueError('Invalid or empty submission manifest.')
    files = []
    seen = set()
    for name in names:
        if not isinstance(name, str):
            raise ValueError('Manifest entries must be relative file names.')
        relative = PurePosixPath(name)
        forbidden = ('.git', 'outputs', 'tmp', '__pycache__', '.venv', 'venv')
        if (relative.is_absolute() or relative.as_posix() != name or name == 'CONTENTS.json'
                or any(part in ('..', '.', '') for part in relative.parts)
                or any(part in forbidden or part.startswith('.env') for part in relative.parts)
                or name.startswith('data/private/') or name.endswith('data_reconciliation_quality_framework.md')
                or '\\' in name or name in seen):
            raise ValueError(f'Unsafe, excluded, or duplicate manifest path: {name}')
        seen.add(name)
        path = root / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Manifest file is missing, a symlink, or outside the project: {name}')
        if path.resolve() == destination:
            raise ValueError('Package destination cannot overwrite an included source file.')
        files.append((name, path.read_bytes()))
    contents = {name: hashlib.sha256(data).hexdigest() for name, data in files}
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwrite so a previously reviewed submission stays available.
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in files:
            archive.writestr('retail-sql-reconciliation/' + name, data)
        archive.writestr('retail-sql-reconciliation/CONTENTS.json', json.dumps(contents, indent=2) + '\n')
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip():
            raise ValueError('Package integrity check failed.')
        for name, expected in contents.items():
            if hashlib.sha256(archive.read('retail-sql-reconciliation/' + name)).hexdigest() != expected:
                raise ValueError(f'Package content verification failed: {name}')
    audit = {'file_count': len(files), 'files': sorted(contents), 'file_sha256': contents,
             'archive_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
             'selection': 'Explicit manifest only; unlisted working files are excluded.', 'verified': True}
    (destination.parent / 'package-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/submission/retail-reconciliation-source.zip')
    args = parser.parse_args()
    try:
        audit = package(ROOT, args.output)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.exit(2, f'PACKAGE ERROR: {error}\n')
    print(f'Source package: {args.output.resolve()}')
    print(f'Verified {audit["file_count"]} explicitly selected files; audit: {args.output.parent / "package-audit.json"}')


if __name__ == '__main__':
    main()
