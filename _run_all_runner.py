import sys, os, subprocess
root = os.path.dirname(os.path.abspath(__file__))
env = os.environ.copy()
env["PYTHONPATH"] = os.path.join(root, "src")
r = subprocess.run([sys.executable, os.path.join(root, "_run_all.py")], timeout=120, capture_output=True, text=True, env=env)
print(r.stdout)
if r.stderr: print("ERR:", r.stderr[:300])
print(f"Exit: {r.returncode}")
