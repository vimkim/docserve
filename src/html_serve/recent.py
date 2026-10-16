"""List recently updated files with the same bounded search as docserve's finder."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .finder import ENTRY_LIMIT, RESULT_LIMIT, SCAN_SECONDS, Finder


def main(argv=None):
    parser = argparse.ArgumentParser(prog='docserve-recent', description=__doc__)
    parser.add_argument('directory', nargs='?', default='.',
                        help='directory to search recursively (default: current directory)')
    parser.add_argument('--query', default='', help='fuzzy query against relative paths')
    parser.add_argument('--include', action='store_true', help='include hidden and ignored files')
    parser.add_argument('--filename', default=r'\.(html|md)$',
                        help='include filename regex (default: \\.(html|md)$); use an empty value for all files')
    parser.add_argument('--exclude-filename', default='', help='exclude filename regex')
    parser.add_argument('--json', action='store_true', help='emit root, results, and truncated as JSON')
    parser.epilog = (f'Scans at most {ENTRY_LIMIT:,} entries and returns at most {RESULT_LIMIT} files. '
                     f'Tree scanning and filtering/metadata each have a {SCAN_SECONDS}-second budget. '
                     'Exit codes: 0 complete, 1 error, 2 usage error, 3 limited results.')
    args = parser.parse_args(argv)
    try:
        root = Path(args.directory).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f'Not a directory: {root}')
        result = Finder(root).search(mode='updated', q=args.query, include=args.include,
                                     filename=args.filename, exclude_filename=args.exclude_filename)
    except (OSError, RuntimeError, ValueError) as error:
        print(f'docserve-recent: {error}', file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({'root': str(root), **result}))
    else:
        for entry in result['results']:
            modified = entry['modified_at']
            timestamp = (datetime.fromisoformat(modified).astimezone().strftime('%Y-%m-%d %H:%M')
                         if modified else 'Unavailable')
            name = str(root / entry['path'])
            name = name.replace('\\', '\\\\').replace('\n', r'\n').replace('\r', r'\r').replace('\t', r'\t')
            print(f'{timestamp}  {name}')
        if result['truncated']:
            print('docserve-recent: Results are limited. The scan may be incomplete. '
                  'Search a narrower directory.', file=sys.stderr)
    return 3 if result['truncated'] else 0


if __name__ == '__main__':
    sys.exit(main())
