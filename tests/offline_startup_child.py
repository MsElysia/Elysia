"""Actual restricted-process negative probes; no legacy runtime activation."""
from pathlib import Path
import sys, json, os, socket, subprocess, tempfile, threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from elysia_offline import install_offline_guard, OfflineBoundaryError
with tempfile.TemporaryDirectory(prefix="offline-probe-") as temp:
    workspace=Path(temp)
    denied=install_offline_guard(workspace)
    if sys.argv[1] == "guard":
        probes = [lambda: socket.socket(),
                  lambda: subprocess.Popen([sys.executable, "-V"]),
                  lambda: threading.Thread(target=lambda: None).start(),
                  lambda: open(Path(__file__).resolve().parents[1] / "outside.txt", "w"),
                  lambda: open(Path(__file__).resolve().parents[1] / "config" / "api_keys.json"),
                  lambda: os.listdir(Path(__file__).resolve().parents[2]),
                  lambda: os.rename(workspace / "a", workspace.parent / "escaped"),
                  lambda: __import__("openai")]
        for index, probe in enumerate(probes):
            try:
                probe()
            except OfflineBoundaryError:
                continue
            raise AssertionError(f"guard allowed protected effect {index}")
        assert len(denied) == len(probes)
        print(json.dumps({"guard_probes_denied": len(denied)}))
