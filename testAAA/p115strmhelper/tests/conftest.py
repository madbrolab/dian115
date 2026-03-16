import sys
from pathlib import Path


plugin_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(plugin_dir))
