"""List the newest files after scanning a directory tree completely."""

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys

from .finder import RESULT_LIMIT, UPDATED_FILENAME, UPDATED_SECONDS, Finder


def result_limit(value):
    try:
        limit = int(value)
        if limit >= 0:
            return limit
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('limit must be a nonnegative integer (0 means all files)')


def scan_timeout(value):
    try:
        seconds = float(value)
        if math.isfinite(seconds) and seconds > 0:
            return seconds
    except ValueError:
        pass
    raise argparse.ArgumentTypeError('timeout must be a positive finite number')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='docserve-recent', description=__doc__)
    parser.add_argument('directory', nargs='?', default='.',
                        help='directory to search recursively (default: current directory)')
    parser.add_argument('--query', default='', help='fuzzy query against relative paths')
    parser.add_argument('--include', action='store_true', help='include hidden and ignored files')
    parser.add_argument('--filename', default=UPDATED_FILENAME,
                        help='include filename regex (default: \\.(html|md)$); use an empty value for all files')
    parser.add_argument('--exclude-filename', default='', help='exclude filename regex')
    parser.add_argument('--limit', type=result_limit, default=RESULT_LIMIT,
                        help=f'maximum files to return; 0 returns all (default: {RESULT_LIMIT})')
    parser.add_argument('--timeout', type=scan_timeout, default=UPDATED_SECONDS, metavar='SECONDS',
                        help=f'whole-scan deadline (default: {UPDATED_SECONDS} seconds)')
    parser.add_argument('--json', action='store_true', help='emit root, results, truncated, and scan_complete as JSON')
    parser.epilog = ('Uses fd when available, with a Python fallback. '
                     'Exit codes: 0 complete scan, 1 error, 2 usage error, 3 scan timeout.')
    args = parser.parse_args(argv)
    try:
        root = Path(args.directory).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f'Not a directory: {root}')
        result = Finder(root).search(mode='updated', q=args.query, include=args.include,
                                     filename=args.filename, exclude_filename=args.exclude_filename,
                                     limit=args.limit, timeout=args.timeout)
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
    if not result['scan_complete']:
        print(f'docserve-recent: {result["message"]} Increase --timeout to allow a longer scan.', file=sys.stderr)
    return 0 if result['scan_complete'] else 3


if __name__ == '__main__':
    sys.exit(main())
