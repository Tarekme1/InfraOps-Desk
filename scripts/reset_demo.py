"""Local-only reset of the demo database. Nothing is deleted without operator running this script."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import Store

if __name__ == '__main__':
    path = Path(__file__).resolve().parents[1] / 'data' / 'infraops.sqlite'
    answer = input(f'Reset fictional local demo database at {path}? Type RESET: ')
    if answer == 'RESET':
        path.unlink(missing_ok=True)
        Store(path)
        print('Fictional demo reset completed.')
    else:
        print('No changes made.')
