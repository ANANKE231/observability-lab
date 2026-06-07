# DevOps Observability Lab

A complete, production-grade observability stack deployed with a single `docker compose up` command.  
Covers **metrics** (Prometheus + Grafana), **logging** (Loki + Promtail), **dashboards**, and **proactive alerting**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Docker network: observability               │
│                                                                     │
│  ┌─────────────┐  scrape /metrics  ┌──────────────┐                │
│  │             │ ─────────────────▶│              │                │
│  │  Demo App   │                   │  Prometheus  │                │
│  │  :5000      │  stdout (JSON)    │  :9090       │                │
│  │             │ ──────────┐       └──────────────┘                │
│  └─────────────┘           │               │                       │
│                             ▼               │ PromQL + Alerts       │
│                      ┌──────────┐           ▼                       │
│                      │ Promtail │   ┌──────────────┐               │
│                      │ :9080    │   │   Grafana    │               │
│                      └──────────┘   │   :3000      │               │
│                             │       └──────────────┘               │
│                             │ push logs      ▲                     │
│                             ▼                │ LogQL               │
│                      ┌──────────┐            │                     │
│                      │  Loki    │ ───────────┘                     │
│                      │  :3100   │                                   │
│                      └──────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Data flow summary**

| Path | Technology | Protocol |
|---|---|---|
| App → Prometheus | Prometheus pull | HTTP scrape every 15s |
| App stdout → Promtail | Docker socket | File/socket read |
| Promtail → Loki | Loki push API | HTTP POST |
| Prometheus → Grafana | Prometheus datasource | PromQL over HTTP |
| Loki → Grafana | Loki datasource | LogQL over HTTP |

---

## Quick Start

```bash
git clone https://github.com/ANANKE231/observability-lab.git
cd observability-lab
docker compose up --build -d
```

| Service | URL | Credentials |
|---|---|---|
| Demo App | http://localhost:5000 | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |
| Loki | http://localhost:3100 | — |

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

2. **Promtail** connects to `/var/run/docker.sock`, automatically discovers containers labelled `observability=true`, and ships their logs to Loki.

3. **Promtail pipeline** parses the JSON and promotes `level` to a Loki stream label, enabling fast filtering by log severity.

4. **Loki** stores the log streams. Grafana queries them with LogQL (`{container="demo-app"}`).

---

### Custom Metrics Exposed

The app exposes Prometheus metrics at `GET /metrics`:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `app_requests_total` | Counter | `method`, `endpoint`, `status_code` | Every HTTP request |
| `app_errors_total` | Counter | `endpoint`, `error_type` | Application-level errors |
| `app_request_duration_seconds` | Histogram | `endpoint` | Request latency |

---

### Triggering the CRITICAL Alert

The alert rule fires when `rate(app_errors_total[1m]) * 60 > 5` — more than 5 errors per minute.

**Windows (PowerShell):**
```powershell
Invoke-WebRequest -Uri http://localhost:5000/error-flood -UseBasicParsing
```

**Linux/Mac:**
```bash
curl http://localhost:5000/error-flood
```

After ~30 seconds, go to **Grafana → Alerting → Alert rules** — the `HighErrorRate` rule will show as **Firing**.

---

## Evidence (Screenshots)

### 1. Grafana Dashboard — App Metrics

The dashboard auto-provisions on startup showing total requests, error counts, request rate, and the CRITICAL alert threshold as a red dashed line.

![Grafana Dashboard](https://private-user-images.githubusercontent.com/181968734/603969178-cd5a3ef7-589f-49ad-aeed-ef77cd57a7df.jpg?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODA3NjcwNjksIm5iZiI6MTc4MDc2Njc2OSwicGF0aCI6Ii8xODE5Njg3MzQvNjAzOTY5MTc4LWNkNWEzZWY3LTU4OWYtNDlhZC1hZWVkLWVmNzdjZDU3YTdkZi5qcGc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwNjA2JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDYwNlQxNzI2MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1kM2E1NWRkOWFhZjNmY2JjNmJmMDA5OWEyZWJiNmZhNTg0NWYxMmRhZDY5NTljOGUxZDUyOTcwZWE0ZjBmNjBhJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9aW1hZ2UlMkZqcGVnIn0.JiRKG3dpk_aEEpbjPMExr0yamwM7UUO93EVE_o6mzGY)

### 2. Alerting Tab — CRITICAL Alert Firing

After hitting `/error-flood`, the `HighErrorRate` rule moves to **Firing** state within 30 seconds.

![Alert Firing](https://private-user-images.githubusercontent.com/181968734/603456173-c88d1df3-1b45-43a5-93e2-8bed84413adc.jpg?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODA3NjcwNjksIm5iZiI6MTc4MDc2Njc2OSwicGF0aCI6Ii8xODE5Njg3MzQvNjAzNDU2MTczLWM4OGQxZGYzLTFiNDUtNDNhNS05M2UyLThiZWQ4NDQxM2FkYy5qcGc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwNjA2JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDYwNlQxNzI2MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT05NzkxYmM4YTk2YWE5ZTlkZTRkMDY5MzcwMTQ4YjAxYjk0MjNiNjFiZTNhNjhhZTc5YTMxYzEwM2VjZjA0NzM5JlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9aW1hZ2UlMkZqcGVnIn0.Xas6636BwB91SJSQhcXEMIgYWmOernsx97gRs1x52Dw)

### 3. Log Analysis — JSON Logs in Grafana (Loki)

Grafana Explore with Loki datasource showing structured JSON logs with level, message, path, method, status_code, and duration_ms fields.

![Loki Logs](https://private-user-images.githubusercontent.com/181968734/603469599-375b32d8-1885-45ca-a736-726900950a98.jpg?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODA3NjcwNjksIm5iZiI6MTc4MDc2Njc2OSwicGF0aCI6Ii8xODE5Njg3MzQvNjAzNDY5NTk5LTM3NWIzMmQ4LTE4ODUtNDVjYS1hNzM2LTcyNjkwMDk1MGE5OC5qcGc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwNjA2JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDYwNlQxNzI2MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT04YzY1YTJkODdhNThjMDdhNjQzMDQwMGRkYWU3MDgyMTAzNDRhZjU3Y2M5ZDg0MWY5YTI0NzdjM2M0ZGFlMmM2JlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9aW1hZ2UlMkZqcGVnIn0.vyqqHTrADHMBWQEvAGJOj8vU7s2HvGFKlJ0usrhEzf4)

---

## Analysis

### Why is JSON-structured logging more efficient than plain text?

Plain text logs are written for humans and require fragile regex to parse. JSON-structured logs treat every field as a typed key-value pair:

```json
{"timestamp":"2024-01-15T10:23:45Z","level":"ERROR","status_code":500,"endpoint":"/work","latency_ms":42.7}
```

Benefits:
- **Zero-parse ingestion** — Loki and Elasticsearch ingest JSON directly with no extraction rules
- **Reliable filtering** — `{level="ERROR"}` is an exact key lookup, not a text search
- **Aggregation without ETL** — fields like `latency_ms` are already numbers, queryable directly
- **Schema evolution** — adding a new field doesn't break existing queries
- **Better compression** — repeated key names compress efficiently in columnar stores

### Fundamental difference: Prometheus vs Loki

| Dimension | Prometheus (metrics) | Loki (logs) |
|---|---|---|
| **Data model** | Numeric time-series (float64 + timestamp + labels) | Raw log streams (string + timestamp + labels) |
| **Storage** | TSDB — indexes every label value | Compressed chunks — labels indexed, content is not |
| **Query language** | PromQL — math and aggregation on numbers | LogQL — label filtering + optional metric extraction |
| **Collection** | **Pull** — scrapes `/metrics` on a schedule | **Push** — Promtail ships logs as they arrive |
| **Use case** | "Is the system healthy? What is p99 latency?" | "What exactly happened at 10:23:45?" |

Prometheus tells you **that** something is wrong. Loki tells you **why**.

### Long-term log retention (6 months) without depleting disk

Three techniques working together:

1. **Compaction + retention policy** — set `retention_period: 4320h` (180 days) in Loki's compactor. It merges small chunks into larger ones (3-5× better compression) and deletes expired data automatically.

2. **Severity-based sampling** — keep `ERROR`/`WARN` for 180 days, `INFO` for 30 days, drop `DEBUG` entirely via Promtail pipeline stages. This cuts ingest volume by 60-80%.

3. **Object storage tiering** — move Loki's storage backend from local filesystem to S3/MinIO. At ~$0.023/GB/month vs $0.10+/GB for SSD, a typical app generating 2-5 GB/month of compressed logs costs under $1/month for 6 months.

---

## Project Structure

```
observability-lab/
├── docker-compose.yml
├── app/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
├── prometheus/
│   ├── prometheus.yml
│   └── rules/alerts.yml
├── grafana/
│   ├── dashboards/
│   └── provisioning/
│       ├── datasources/datasources.yml
│       ├── dashboards/dashboards.yml
│       └── alerting/alerts.yml
├── loki/
│   └── loki-config.yml
└── promtail/
    └── promtail-config.yml
```

---

## Teardown

```bash
docker compose down          # stop containers
docker compose down -v       # stop and remove all data volumes
```
