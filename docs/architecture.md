# Architecture

Freeze Watch has three deliberately small processes:

1. `freeze-monitor` samples Linux metrics every 10 seconds and Docker details
   every third sample.
2. `freeze-monitor-maintain` compresses raw TSV logs after 14 days and removes
   compressed archives after 90 days.
3. `freeze_watch.py` is the GTK4 dashboard and StatusNotifierItem tray process.

The GUI reads the collector's append-only TSV files. It does not repeatedly call
Docker itself, so opening the dashboard does not add container-engine load.

It reads them twice over. Live, it shows the newest file. In review, it shows
the window before a chosen incident: a freeze names the file it was cut off
from, a stall is matched to the file whose samples span it, and the container
sample beside either is one substitution away, since both files are named from
the same stamp. The tray is left on live readings throughout, because a review
is something the reader asked for and the indicator is not.

## Data flow

```text
/proc + /sys + Docker
        |
        v
  freeze-monitor
        |
        +-- metrics-*.tsv
        +-- docker-*.tsv
        +-- events.log
                |
                v
       GTK4 dashboard + tray
```

All files live below `${XDG_STATE_HOME:-~/.local/state}/freeze-monitor`.
No daemon runs as root.

## Incidents

The collector is read after the fact, so it has to say where an incident was.

Each session writes `START` on entry and `STOP` on a clean exit. A session that
never wrote `STOP` was cut off, and the next session says so: `FREEZE` when the
boot id changed, meaning the machine went down without shutting down, and
`INTERRUPTED` when it did not, meaning only the collector died. Both name the
last sample that reached disk.

`GAP` records a sample that arrived later than three intervals. It answers a
question the metrics cannot: if samples kept arriving through a reported
freeze, the kernel was scheduling this loop and the desktop is what stopped
responding.

Samples are buffered and flushed every third one, except while any reading is
elevated, when each sample is written through. The thresholds for that sit
below the ones that raise a warning, so the evidence is already durable before
anything is worth warning about. `FLUSH` marks each transition.

## Kernel evidence

Metrics describe load; they do not say that the GPU driver reset or that a task
blocked for two minutes. `KERNEL` events carry those lines, matched against a
list confined to what explains a machine that stopped responding: hung tasks,
RCU stalls, DRM and GPU hangs, NVMe and ATA timeouts, machine checks, OOM
kills, thermal throttling, and filesystem I/O errors.

Reading goes through `journalctl` rather than `/dev/kmsg`, because it honours
group membership and can reach the boot before this one. Each scan resumes from
a cursor, so no line is reported twice, and output is capped per scan: one
failing device can emit thousands of near-identical lines, and a log that
scrolls past the freeze is no better than no log. A match also switches the
collector to write-through.

The previous boot is read only when the machine went down without shutting
down, which is the one time those lines are worth replaying.

Users outside the `adm` and `systemd-journal` groups cannot read the kernel
log. The collector says so once at startup and carries on. `/sys/fs/pstore`,
where a panic leaves its remnants, is root-only on every distribution checked,
so it is not consulted.

## Signals

Linux pressure accounting reports two figures per resource. `some` counts time
where at least one task was stalled; `full` counts time where every task was,
which is what a freeze is from the kernel's point of view. Both are recorded,
and `full` carries the lower alerting threshold of the two.

Processes in uninterruptible sleep are counted for the same reason. That state
is where a task waits on a device, so a pile-up points at storage rather than
at the CPU, and it raises the load average without consuming any CPU at all.

## Compatibility

The first private deployment used `runtelenexus_*` field names. The public
schema uses `tracked_*` names at the same column positions, so the dashboard
can continue reading earlier files.

New columns are appended, never inserted, for the same reason. A file written
by an older collector simply stops short of the newest columns, and the
dashboard reads the absent ones as missing data.
