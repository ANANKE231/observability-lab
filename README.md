# DevOps Observability Lab

A complete, production-grade observability stack deployed with a single `docker compose up` command.  
Covers **metrics** (Prometheus + Grafana), **logging** (Loki + Promtail), **dashboards**, and **proactive alerting**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Docker network: observability               │
│                                                                     │
│  ┌─────────────┐  scrape /metrics  ┌──────────────┐  PromQL        │
│  │             │ ─────────────────▶│              │ ──────────────▶│
│  │  Demo App   │                   │  Prometheus  │                 │
│  │  :5000      │  stdout (JSON)    │  :9090       │  Alert rule     │
│  │             │ ──────────┐       └──────────────┘  errors>5/min  │
│  └─────────────┘           │               ▲                       │
│                             ▼               │ scrape                │
│                      ┌──────────┐   ┌──────────────┐               │
│                      │ Promtail │   │ Node Exporter│               │
│                      │ :9080    │   │ :9100        │               │
│                      └──────────┘                                   │
│                             │ push logs (LogQL)                     │
│                             ▼                                       │
│                      ┌──────────┐          ┌──────────────┐        │
│                      │  Loki    │  LogQL   │              │        │
│                      │  :3100   │ ────────▶│   Grafana    │        │
│                      └──────────┘          │   :3000      │        │
│                                            └──────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

**Data flow summary**

| Path | Technology | Protocol |
|---|---|---|
| App → Prometheus | Prometheus pull | HTTP scrape every 10 s |
| App stdout → Promtail | Docker socket | File/socket read |
| Promtail → Loki | Loki push API | HTTP POST |
| Prometheus → Grafana | Prometheus datasource | PromQL over HTTP |
| Loki → Grafana | Loki datasource | LogQL over HTTP |
| Node Exporter → Prometheus | Prometheus pull | HTTP scrape every 15 s |

---

## Quick Start

```bash
git clone <your-repo-url>
cd observability-lab
docker compose up --build -d
```

| Service | URL | Credentials |
|---|---|---|
| Demo App | http://localhost:5000 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Loki | http://localhost:3100 | — |
| Node Exporter | http://localhost:9100 | — |

> Grafana auto-provisions both datasources (Prometheus + Loki) and the dashboard on first boot.  
> No manual setup required.

---

## Implementation Details

### Logging Strategy

Logs are emitted in **JSON format** over `stdout` and collected via Promtail's Docker socket discovery:

1. **Demo App** writes structured JSON to `stdout` on every request and error:
   ```json
   {
     "timestamp": "2024-01-15T10:23:45.123456",
     "level": "ERROR",
     "logger": "demo-app",
     "message": "processing error occurred",
     "service": "demo-app",
     "version": "1.0.0",
     "endpoint": "/work"
   }
   ```

2. **Promtail** connects to `/var/run/docker.sock`, automatically discovers containers labelled `service=demo-app`, and ships their logs to Loki.

3. **Promtail pipeline** parses the JSON, promotes `level` and `service` to Loki stream labels, and reuses the app's own timestamp — so log entries arrive in Loki with the correct time even if there's a slight collection delay.

4. **Loki** stores the log streams. Grafana queries them with LogQL (`{service="demo-app"}`).

---

### Custom Metrics Exposed

The app exposes three Prometheus metrics at `GET /metrics`:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `app_requests_total` | Counter | `method`, `endpoint`, `status_code` | Every HTTP request |
| `app_errors_total` | Counter | `endpoint`, `error_type` | Application-level errors |
| `app_request_duration_seconds` | Histogram | `endpoint` | Request latency (p50/p95/p99) |

---

### Triggering the CRITICAL Alert

The alert rule fires when `rate(app_errors_total[1m]) * 60 > 5`
(more than 5 errors per minute, evaluated every 15 seconds).

**To trigger it:**

```bash
# Option 1 — dedicated flood endpoint (generates 20 errors instantly)
curl http://localhost:5000/error-flood

# Option 2 — rapid loop hitting the /work endpoint (10% natural error rate)
for i in $(seq 1 100); do curl -s http://localhost:5000/work > /dev/null; done

# Option 3 — watch it fire in real time
watch -n2 'curl -s http://localhost:9090/api/v1/query \
  --data-urlencode "query=rate(app_errors_total[1m])*60" | python3 -m json.tool'
```

**Where to see the alert in Grafana:**

1. Open http://localhost:3000
2. Navigate to **Alerting → Alert rules**
3. Within ~30 seconds of running the flood, `HighErrorRate` transitions to **Firing**
4. The dashboard gauge panel turns red and exceeds the 5/min threshold line

---

## Evidence (Screenshots)

> Replace the placeholders below with actual screenshots after running the stack.

### Grafana Dashboard — Custom Application Metrics

![Grafana dashboard showing app_requests_total and app_errors_total panels](screenshots/grafana-dashboard.png)

*The dashboard auto-provisions at startup. Open http://localhost:3000 → Dashboards → "Demo App – Observability Dashboard".*

### Log Analysis in Grafana (Loki)

![Grafana Explore view filtered to service=demo-app showing JSON logs](screenshots/grafana-loki-logs.png)

*Open Grafana → Explore → select Loki datasource → run `{service="demo-app"}`.*

### Grafana Alerting Tab — Active Alert Rule

![Grafana Alerting tab showing HighErrorRate rule in Firing state](screenshots/grafana-alert-firing.png)

*After hitting `/error-flood`, the `HighErrorRate` rule transitions to Firing within one evaluation cycle (~15 s).*

---

## Analysis

### Why is JSON-structured logging more efficient than plain text?

Plain text logs are written for humans: `[2024-01-15 10:23:45] ERROR: Request to /work failed with code 500`.
Machines have to *parse* that string — with fragile regex, locale-dependent date formats, and no schema guarantees.

JSON-structured logs treat every field as a first-class typed value:

```json
{"timestamp":"2024-01-15T10:23:45.123Z","level":"ERROR","status_code":500,"endpoint":"/work","latency_ms":42.7}
```

Benefits:

- **Zero-parse ingestion.** Loki, Elasticsearch, and Splunk ingest JSON directly; no extraction rules needed.
- **Reliable filtering.** `{level="ERROR"}` is an exact key lookup, not a text search through log lines.
- **Aggregation without ETL.** You can run `avg(latency_ms)` in LogQL/KQL because the field is already a number, not a substring.
- **Schema evolution.** Adding a new field (e.g. `trace_id`) doesn't break existing queries — unknown keys are simply ignored.
- **Compression efficiency.** Repeated key names across millions of log lines compress very well with columnar stores (Loki's TSDB backend takes advantage of this).

### Fundamental technical difference: Prometheus vs Loki

| Dimension | Prometheus (metrics) | Loki (logs) |
|---|---|---|
| **Data model** | Time-series of *numbers* (float64 samples with a timestamp and label set) | Time-ordered *strings* (arbitrary log lines tagged with stream labels) |
| **Storage** | TSDB — columnar, heavily compressed, indexes every label | Chunks of compressed raw log data; labels indexed, *content is not* |
| **Query language** | PromQL — arithmetic, aggregation, rate calculation over numeric samples | LogQL — label filtering first, then optional metric extraction |
| **Collection model** | **Pull** — Prometheus scrapes targets on a schedule | **Push** — Promtail pushes log entries to Loki as they arrive |
| **Cardinality** | Low — metrics have a bounded, stable label set | High — logs can contain unbounded values (user IDs, request bodies) |
| **Use case** | "Is the system healthy right now? What is the p99 latency?" | "What exactly happened at 10:23:45? What did this request look like?" |

The fundamental difference: Prometheus measures **how much / how fast** (quantitative), Loki records **what happened** (qualitative). They're complementary, not interchangeable.

### Long-term log retention (6 months) without depleting disk

Storing 6 months of application logs naively can consume hundreds of gigabytes. The practical approach combines three techniques:

1. **Compaction + retention policy in Loki**  
   Enable `retention_enabled: true` in the compactor and set `retention_period: 4320h` (180 days). Loki's compactor runs periodically, merges small chunks into larger ones (improving compression by 3-5×), and deletes expired data automatically. This is already scaffolded (commented out) in `loki/loki-config.yml`.

2. **Log sampling / severity gating**  
   Not every log line is equally valuable after 30 days. A common pattern: ship `ERROR` and `WARN` at full fidelity for 180 days, `INFO` for 30 days, and `DEBUG` for 7 days. Promtail pipeline stages can drop `DEBUG` lines before they even reach Loki, reducing ingest volume by 60-80% in typical applications.

3. **Object storage tiering (S3 / GCS)**  
   For serious long-term retention, Loki's storage backend can be swapped from the local filesystem to S3-compatible object storage. Object storage costs ~$0.023/GB/month vs $0.08-0.15/GB/month for SSD. With compaction, a moderately busy application generates roughly 1-5 GB/month of compressed logs — making 6 months easily manageable at under $1/month in storage cost.

---

## Project Structure

```
observability-lab/
├── docker-compose.yml              # Single deploy command
├── app/
│   ├── app.py                      # Flask app with /metrics + JSON logging
│   ├── requirements.txt
│   └── Dockerfile
├── prometheus/
│   ├── prometheus.yml              # Scrape config
│   └── rules/
│       └── alerts.yml              # Alert rules (HighErrorRate, AppDown)
├── grafana/
│   ├── dashboards/
│   │   └── demo-app.json           # Pre-built dashboard
│   └── provisioning/
│       ├── datasources/
│       │   └── datasources.yml     # Prometheus + Loki auto-configured
│       ├── dashboards/
│       │   └── dashboards.yml
│       └── alerting/
│           └── alerts.yml          # Grafana alert rule provisioning
├── loki/
│   └── loki-config.yml             # Loki storage + retention config
└── promtail/
    └── promtail-config.yml         # Docker socket discovery + JSON pipeline
```

---

## Stopping the Stack

```bash
docker compose down          # stop and remove containers
docker compose down -v       # also remove named volumes (clears all data)
```
