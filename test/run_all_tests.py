import sys, os, subprocess
root = os.path.dirname(os.path.abspath(__file__))
r = subprocess.run([sys.executable, "_run_all.py"], timeout=120, capture_output=True, text=True, cwd=root)
print(r.stdout)
if r.stderr: print("ERR:", r.stderr[:300])
print(f"Exit: {r.returncode}")
