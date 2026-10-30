"""Runs the two cheating helpers one after the other, printing a prompt line before the second, so one terminal scene can show both."""
import subprocess, sys
PY = sys.executable
def run(pack):
    subprocess.run([PY, "-m", "bridge", "run", f"examples/packs/{pack}", "--vault", "examples/vault-library.json", "--types", "note,contact"], check=False)
run("exfil-kit")
print("", flush=True)
print("$ bridge run examples/packs/data-thief --vault examples/vault-library.json --types note,contact", flush=True)
run("data-thief")
