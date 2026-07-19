# FreeRTOS Task & Concurrency Design

Applies to the definitive firmware (Phase 3 onward).

---

## 1. Execution contexts

There are **three** contexts, not two. The third is easy to overlook and is
where the Espressif example's race lives.

```
┌──────────────────────────────────────────────────────────────┐
│ (C) Wi-Fi event task          — owned by ESP-IDF, not us     │
│     WIFI_EVENT_FTM_REPORT arrives here                       │
│     Must do almost nothing: copy, signal, return             │
└───────────────────────────┬──────────────────────────────────┘
                            │ event group / semaphore
┌───────────────────────────▼──────────────────────────────────┐
│ (A) Measurement task       — "ftm_meas"                      │
│     round-robin anchors, run FTM session, build a snapshot   │
└───────────────────────────┬──────────────────────────────────┘
                            │ QueueHandle_t  (snapshots BY VALUE)
┌───────────────────────────▼──────────────────────────────────┐
│ (B) Telemetry task         — "ftm_tx"                        │
│     serialise snapshot -> bytes -> write to host             │
└──────────────────────────────────────────────────────────────┘
```

## 2. Why two tasks — and the measured reason

The two-task split is correct, and not merely for tidiness. **We hit the exact
failure it prevents during hardware evaluation.**

Writes to the built-in USB-Serial-JTAG **block, and eventually time out, when
nothing on the host is reading** (`HARDWARE_FINDINGS.md` §1). A single-task
design that measures and then writes would stall the measurement loop whenever
the operator closes the serial monitor. Measurement cadence would then depend on
whether someone happens to have a terminal open — an invisible, maddening
coupling.

Splitting them makes the property explicit and enforceable:

> **The measurement task must never block on transmission.**

Secondary benefits: the two have genuinely different cadences (~0.66 Hz
measurement vs. bursty transmission), different failure modes, and different
priorities.

## 3. Task specifications

| | (A) `ftm_meas` | (B) `ftm_tx` |
| --- | --- | --- |
| Priority | 5 | 4 (lower than A) |
| Stack | 4096 B (measure and trim) | 3072 B |
| Blocks on | FTM event group, with timeout | Queue receive, `portMAX_DELAY` |
| Never blocks on | The telemetry queue | — |
| Core | Any (ESP32-C3 is single core) | Any |

Both priorities sit **below** the Wi-Fi stack's. Starving Wi-Fi to emit
telemetry would corrupt the very measurements being reported.

### (C) The Wi-Fi event handler

Runs in ESP-IDF's event task. Treat it with ISR-like discipline:

- Copy the report fields out, set an event group bit, return.
- **No** logging, no serialisation, no queue sends that could block, no
  allocation.
- It must still call `esp_wifi_ftm_get_report()` on **every** path, including
  failure — the upstream example leaks here (`HARDWARE_FINDINGS.md` §9).

## 4. The queue carries snapshots by value

```c
typedef struct {           /* domain/types — no ESP-IDF types */
    ftm_snapshot_kind_t kind;   /* RANGE | STATUS | POSITION | ANCHOR_CFG */
    uint32_t            msg_seq;    /* assigned AT ENQUEUE — see §5.1 */
    uint32_t            cycle_seq;
    uint32_t            uptime_ms;
    union {
        ftm_range_snapshot_t    range;
        ftm_status_snapshot_t   status;
        ftm_position_snapshot_t position;
        ftm_anchor_cfg_t        anchor;
    } u;
} ftm_snapshot_t;
```

`msg_seq` lives in the snapshot rather than in the frame header so that it is
**format-independent**: any serialiser, including a future protobuf one, carries
it without the framing having to know about queue behaviour.

**By value, never by pointer.** Passing pointers into shared state is precisely
the defect pattern in the Espressif example, where `s_rtt_est` / `s_dist_est` are
written by the event task and read by another with no synchronisation
(`HARDWARE_FINDINGS.md` §9). A copied snapshot is immutable once queued and
needs no lock.

The snapshot is a **domain type**. It contains no `esp_*` types, which is what
lets the serialiser and the whole consumer side be host-tested with no hardware.

Queue depth: **4** — see §5.3 for why shallow is correct here.

## 5. Overflow policy — freshest data wins

> **Producer sends with timeout 0. On a full queue it discards the OLDEST
> entry, enqueues the new one, and increments a drop counter.**

**This is a navigation system, so latency is error.** A backlog of stale
positions is not a valuable record — it means the consumer is acting on where
the node used to be. Given a choice between an old sample and a new one, the new
one is always the more useful, and the old one is actively misleading.

- **Never block the producer.** That would reintroduce exactly the coupling the
  two-task split exists to remove.
- **Drop the oldest.** Navigate on current data.
- **Never silently lose the fact that data was lost** — see §5.1.

### 5.1 Loss is observable, without keeping the data

Two independent diagnostics, both cheap:

1. **A monotonic `msg_seq` on every message**, assigned by the telemetry layer
   **at enqueue time**. A gap in the sequence tells the consumer exactly how
   many messages were lost and where.
2. **A running `dropped_total`** in `NAV-STATUS`, for a consumer that joined the
   stream mid-way and has no earlier sequence to compare against.

`msg_seq` must be assigned **at enqueue, not at serialisation**. Assigned later,
a dropped message would never have been numbered, and the gap would not appear —
the diagnostic would silently fail in exactly the case it exists for.

These two are complementary: the sequence gap is precise and local; the counter
is a durable total that survives a consumer restart. Both are **diagnostic
only** — navigation uses the current data and nothing else.

This is the same principle as transmitting failed measurements rather than
omitting them (`docs/PROTOCOL.md` §1): a gap must be visible in the data,
because a silent gap is indistinguishable from "nothing happened".

### 5.2 Implementation

FreeRTOS has no drop-oldest primitive for a queue deeper than one, so:

```c
if (xQueueSend(q, &snap, 0) != pdTRUE) {
    ftm_snapshot_t discard;
    (void)xQueueReceive(q, &discard, 0);   /* make room */
    (void)xQueueSend(q, &snap, 0);
    s_dropped_total++;
}
```

Only the producer ever discards. If the consumer happens to dequeue between the
two calls the queue is merely non-full, and the send succeeds — no corruption
either way.

### 5.3 Depth bounds staleness

With drop-oldest, **queue depth directly bounds the age of the oldest entry**:

```
max staleness = depth x measurement period
```

**Depth 4** at ~1.5 s per session (`HARDWARE_FINDINGS.md` §2) gives ~6 s worst
case. A deep queue would be actively harmful here — it would only mean more
stale data to work through before reaching the present. The queue exists to
absorb transient scheduling jitter, **not** to buffer through a host stall; if
the host stalls, the correct behaviour is to drop.

## 6. Startup and shutdown

- Queue created **before** either task starts. A producer racing a null queue
  handle is a classic init-order bug.
- `ftm_tx` starts first, so `MON-VERSION` and `CFG-ANCHOR` are transmitted before
  the first measurement lands.
- Task creation failure is fatal and loud — never continue in a half-started
  state.
- Clean stop: signal, then join with a timeout. No `vTaskDelete` on a task that
  might hold a resource.

## 7. Watchdog

- Both tasks subscribe to the task watchdog.
- `ftm_meas` blocks on the FTM event group with a **finite timeout** — an FTM
  session that never reports must surface as a timeout, not a watchdog reset.
- `ftm_tx` blocking indefinitely on an empty queue is normal and must not trip
  the watchdog; feed it around the blocking receive.

## 8. Testability

All of this is designed to be testable without hardware:

- Snapshot types are pure domain types → the consumer side is host-testable.
- The queue is behind a thin interface, so host tests substitute a simple
  in-memory implementation and drive overflow deterministically.
- `ftm_meas` depends on the **driver interface**, not the implementation, so
  CMock can inject FTM failures, timeouts and clamped sessions.

Required cases are in `docs/TESTING.md` §4.9.
