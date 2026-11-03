"""Copy only the public policy/school YAML into a backend service's build root."""
import shutil
from pathlib import Path


def package(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    for relative in ("sources.yaml", "schools/penn.yaml"):
        destination = root / "backend" / "config" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / "config" / relative, destination)


if __name__ == "__main__":
    package()
