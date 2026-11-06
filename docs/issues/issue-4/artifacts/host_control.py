"""issue 4 主機對照組：已知負載的程序，走 process_sample 讀真實 /proc。"""
import importlib.util, subprocess, sys, time
from pathlib import Path
spec = importlib.util.spec_from_file_location('container_probe', Path(sys.argv[1]) / 'src/container_probe.py')
probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
child = subprocess.Popen([sys.executable, '-c', 'import time\ntime.sleep(10)\nend = time.monotonic() + 15\nwhile time.monotonic() < end: pass'])
def top():
    out = subprocess.run(['ps', '-o', 'pid=,stat=,pcpu=,pmem=,comm=', '-p', str(child.pid)], capture_output=True, text=True).stdout.split()
    return {'Titles': ['PID', 'STAT', '%CPU', '%MEM', 'COMMAND'], 'Processes': [out[:5]]}
try:
    time.sleep(12)  # 10 s idle + 2 s busy
    first, *_, snapshot = probe.process_sample(top())
    print('first :', first[0])
    time.sleep(5)   # fully busy
    second, *_, _ = probe.process_sample(top(), snapshot)
    print('second:', second[0])
    print(f"clk_tck={probe.CLK_TCK} elapsed≈5s")
finally:
    child.kill()
