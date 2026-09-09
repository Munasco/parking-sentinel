"""Launch the Node video backend locally through the existing CLI command."""
import os
from pathlib import Path
import subprocess


def serve(port=8765):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, PORT=str(port))
    try:
        subprocess.run(["node", "--env-file-if-exists=.env.local", "scripts/serve.mjs"], cwd=root, env=environment, check=True)
    except KeyboardInterrupt:
        pass
