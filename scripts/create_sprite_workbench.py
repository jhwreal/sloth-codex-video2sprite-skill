#!/usr/bin/env python3
"""Install the instant editor beside a project's production-plan.json; no media writes."""
import argparse
import json
from pathlib import Path
import shutil

TEMPLATE = Path(__file__).resolve().parents[1] / 'assets/sprite-edit-workbench/instant'
FILES = ('index.html', 'app.js', 'editor-model.mjs')


def create(output: Path) -> None:
    output = output.resolve()
    plan = json.loads((output / 'production-plan.json').read_text(encoding='utf-8'))
    actions = plan.get('actions')
    if not isinstance(actions, list) or not actions:
        raise ValueError('production-plan.json needs a nonempty actions list')
    ids = set()
    for action in actions:
        key = action.get('action')
        if not isinstance(key, str) or not key or key in ids:
            raise ValueError('Each action needs a unique nonempty action ID')
        ids.add(key)
        if not action.get('candidates') and not action.get('frames'):
            raise ValueError('Each action needs candidates or reference frames')
        for candidate in action.get('candidates', []):
            if not isinstance(candidate.get('manifest'), str) or not candidate['manifest']:
                raise ValueError('Each candidate needs a manifest path')
    # Preflight every destination before any write; never overwrite a project instance.
    if any((output / name).exists() or (output / name).is_symlink() for name in FILES):
        raise ValueError('Editor files already exist; adapt the existing instance without overwriting it')
    for name in FILES:
        shutil.copyfile(TEMPLATE / name, output / name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='Existing workbench directory containing production-plan.json')
    args = parser.parse_args()
    try:
        create(args.output_dir)
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        # Do not echo potentially private plan content or filesystem paths.
        print(json.dumps({'ok': False, 'error': type(exc).__name__,
                          'hint': 'Check the plan schema and ensure editor files do not already exist.'}))
        return 2
    print(json.dumps({'ok': True, 'files': list(FILES), 'preview_mode': 'frames-and-audio'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
