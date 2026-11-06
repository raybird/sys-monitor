import csv, json, sys
from pathlib import Path
sys.path.insert(0, '/home/kevin/Documents/RCodes/sys-monitor/src')
import container_probe as probe
calls = Path(sys.argv[4]) / 'qa-calls'
n = int(calls.read_text()) + 1 if calls.exists() else 1
calls.write_text(str(n))
def row(**kw):
    r = dict.fromkeys(probe.FIELDS, 'NA')
    r.update(timestamp=sys.argv[1], epoch=sys.argv[2], zombies=0, oom_killed='false', health='healthy',
             sample_status='ok', process_status='ok', container_state='running', tasks=12, processes=6)
    r.update(kw)
    return [r[k] for k in probe.FIELDS]
procs = json.dumps([dict(pid='4242', state='R', cpu=38.5, memory=2.1, name='node'),
                    dict(pid='4300', state='D', cpu=1.2, memory=0.4, name='sqlite')], ensure_ascii=False)
print('ok')
w = csv.writer(sys.stdout, delimiter='\t', lineterminator='\n')
w.writerow(row(container='runwukong-schedulerd-1', container_id='w1', project='runwukong', service='schedulerd',
               is_tracked_project=1, cpu_pct=154.2, memory_usage='812MiB / 4GiB', restart_count=1 if n < 2 else 2,
               dstate=1, read_bytes=1048576 * n, write_bytes=4096 * n, read_bps=2048.0, write_bps=512.0,
               process_sample=procs))
w.writerow(row(container='runtelenexus-memoria-1', container_id='t1', project='runtelenexus', service='memoria',
               is_tracked_project=1, cpu_pct=12.0, memory_usage='300MiB / 2GiB', restart_count=0, dstate=0,
               read_bytes=0, write_bytes=8192 * n, read_bps=0.0, write_bps=1950.5, process_sample='[]'))
w.writerow(row(container='runtelenexus-worker-1', container_id='t2', project='runtelenexus', service='worker',
               is_tracked_project=1, cpu_pct='NA', memory_usage='NA', restart_count=0, dstate='NA',
               sample_status='unavailable_or_timeout', process_status='budget_or_limit'))
w.writerow(row(container='portainer', container_id='p1', project='NA', service='NA', is_tracked_project=0,
               cpu_pct=0.3, memory_usage='40MiB / 15GiB', restart_count=7, dstate=0, oom_killed='true',
               process_status='not_tracked'))
