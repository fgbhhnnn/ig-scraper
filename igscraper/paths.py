import os, sys
def data_dir():
    """Data dir: next to exe when frozen, else project root. Override with IGS_DATA_DIR."""
    d = os.environ.get('IGS_DATA_DIR')
    if not d:
        base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        d = os.path.join(base, 'igs_data')
    os.makedirs(d, exist_ok=True)
    return d
def static_dir():
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'igscraper', 'static')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
