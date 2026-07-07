import sys
from pathlib import Path
# Permite `import stillholds` sin instalar (pytest lee pythonpath del pyproject,
# but this conftest also guarantees it when running pytest directly).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
