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

Several readings are cumulative counters that only mean something as a rate,
so the sample carries the change since the previous one: swap pages in and
out, major faults, and the disk's busy milliseconds. The first sample of a
session has nothing to subtract from and records those as missing.

The CPU throttle count is kept as an absolute, because what matters is whether
it moved at all. A temperature says the part was hot; the counter says the
firmware responded by taking speed away. It is absent on hardware without
Intel's `thermal_throttle` interface, which reads as missing rather than zero.

Disk figures come from the whole device holding the root filesystem, resolved
once at startup by walking from the mounted partition to its parent in sysfs.
A root on LVM or device-mapper does not resolve that way and reads as missing.

NVMe error counters are deliberately absent: reading them needs root, and the
kernel log already carries the controller timeouts and resets that matter.

## Compatibility

The first private deployment used `runtelenexus_*` field names. The public
schema uses `tracked_*` names at the same column positions, so the dashboard
can continue reading earlier files.

New columns are appended, never inserted, for the same reason. A file written
by an older collector simply stops short of the newest columns, and the
dashboard reads the absent ones as missing data.

## Container samples

`freeze-monitor` invokes the standard-library-only `container_probe.py` every
third host sample. It uses read-only GET requests to the local Docker Unix
socket (`containers/json?all=1`, per-container `stats?stream=false&one-shot=true`,
inspect and top). Docker CLI context inspection only resolves the endpoint;
no container exec, logs, full argv, environment or writes to Docker are used.
TCP/SSH endpoints are unavailable by design; they cannot describe local PIDs.

The cooperative total budget is 6 seconds; individual socket operations time
out after at most 0.5 seconds. The shell kills a helper that exceeds 8 seconds
(with a 1-second kill grace). At most 32 overview containers and 8 deep
containers are selected each round. Deep candidates rotate by 30-second time
buckets and take priority. Remaining overview slots walk the entire sorted
container list from a persistent cursor, skipping only candidates already
selected for deep sampling. This prevents stopped/OOM containers from being
permanently excluded when the priority set is stable. The cursor is stored
as reserved metadata in the counter cache and resets with that cache.
Oversized responses are rejected above 2 MB. A slow stream can exceed the
cooperative budget, but the outer process limit still protects host sampling.
This is a maximum latency bound, not a measured production overhead guarantee.

Deep sampling asks Docker top for `pid,stat,pcpu,pmem,comm`. It keeps the union
of the top 5 CPU, top 5 memory, and first 5 D-state processes, at most 15.
Counts describe the full returned process list; selected entries are not a
complete process inventory. CPU is ps lifetime average; memory percentage is
relative to host RAM. Container CPU is a delta of total CPU/system counters
multiplied by online CPU count: 100% means one core. Container memory uses
raw usage and limit (including cache, unlike the Docker CLI's adjusted view).

Block read/write counters sum Read/Write device entries in
`blkio_stats.io_service_bytes_recursive`; empty accounting is unknown, not zero.
The rate is a difference divided by elapsed sample epoch seconds. ID and
StartedAt must match the previous sample, counters must not decrease, and time
must advance. A missing sample resets the baseline. Listing failure, outer helper timeout, cache write failure and collector restart also invalidate it; recovery starts with unknown rates. The 0600 atomic
`docker-counters.json` cache stores only counters/identity, not process data.

Evidence is appended to `docker-*.tsv` after the original 11 fields, including
ID, Compose project/service, health, bytes/rates, D count, bounded JSON process
sample, and status/reason codes. All evidence therefore participates in the
existing daily rotation, 14-day compression and 90-day archive expiry. Old
files render the absent fields as unknown. Empty or unavailable snapshots have
an empty container name to prevent resurrecting old containers in the UI.
The listing includes running containers and stopped containers of selected projects. Inspect precedes stats so OOM/restart/state evidence survives stats failure; stopped containers are not queried for stats/top. The original host container/task totals count only running rows. Partial overview samples explicitly report `partial`. Query failures do not
stop host metrics. Docker anomaly events retain OOM/restart/Z detection and
add unhealthy/D-state conditions.

The dashboard reads at most 2 MB of the matching Docker TSV. Each expanded
container offers at most 60 saved samples from that file, selected by full
container ID (name fallback for legacy records). It aligns each sample with
the most recent host metric at or before its timestamp within 45 seconds;
otherwise it marks a gap. History is bounded to the available file tail, does
not promise an uninterrupted 30-minute history, and does not cross file
rotation or transparently decompress archives. The last container sample time
is visible and gaps above 60 seconds relative to host samples are labelled.
A stopped collector can be recognized from that timestamp. OOM, unhealthy,
nonzero restart, D or Z counts are warnings; unknown values never trigger a
normal-state claim. These are correlations rather than automatic diagnoses.
