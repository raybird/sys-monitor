# Architecture

Freeze Watch has three deliberately small processes:

1. `freeze-monitor` samples Linux metrics every 10 seconds and Docker details
   every third sample.
2. `freeze-monitor-maintain` compresses raw TSV logs after 14 days and removes
   compressed archives after 90 days.
3. `freeze_watch.py` is the GTK4 dashboard and StatusNotifierItem tray process.

The GUI reads the collector's append-only TSV files. It does not repeatedly call
Docker itself, so opening the dashboard does not add container-engine load.

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

## Compatibility

The first private deployment used `runtelenexus_*` field names. The public
schema uses `tracked_*` names at the same column positions, so the dashboard
can continue reading earlier files.
