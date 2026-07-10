import sys, os, subprocess
root = os.path.dirname(os.path.abspath(__file__))
test_script = os.path.join(root, "test", "run_tc17_to_tc23.py")
r = subprocess.run([sys.executable, test_script], timeout=120, capture_output=True, text=True, cwd=root)
print(r.stdout)
if r.stderr: print("ERR:", r.stderr[:300])
print(f"Exit: {r.returncode}")
