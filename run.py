import os, sys
from igscraper.server import run
if __name__ == '__main__':
    if sys.stdout is None: sys.stdout = open(os.devnull, 'w', encoding='utf-8')   # windowed exe
    if sys.stderr is None: sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    port = int(os.environ['IGS_PORT']) if os.environ.get('IGS_PORT') else None
    sys.exit(run(open_browser=os.environ.get('IGS_NO_BROWSER') != '1', port=port))
