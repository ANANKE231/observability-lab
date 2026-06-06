import time
import random
import logging
import json
import os
from flask import Flask, jsonify, request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ── JSON structured logging ──────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f"),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
            "service":   "demo-app",
            "version":   "1.0.0",
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        return json.dumps(log_entry)

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.root.setLevel(logging.INFO)
logging.root.handlers = [handler]
logger = logging.getLogger("demo-app")

# ── Prometheus metrics ───────────────────────────────────────────────────────
REQUEST_COUNTER = Counter(
    "app_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"],
)
ERROR_COUNTER = Counter(
    "app_errors_total",
    "Total number of application errors",
    ["endpoint", "error_type"],
)
REQUEST_LATENCY = Histogram(
    "app_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
)

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.before_request
def start_timer():
    request._start_time = time.time()

@app.after_request
def record_metrics(response):
    latency = time.time() - request._start_time
    endpoint = request.path
    REQUEST_COUNTER.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency)
    logger.info(
        "request handled",
        extra={
            "extra": {
                "method":      request.method,
                "path":        endpoint,
                "status_code": response.status_code,
                "latency_ms":  round(latency * 1000, 2),
                "remote_addr": request.remote_addr,
            }
        },
    )
    return response

# ── Routes ───────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return jsonify({"status": "ok", "service": "demo-app", "version": "1.0.0"})

@app.route("/healthy")
def healthy():
    return jsonify({"status": "healthy"})

@app.route("/work")
def work():
    """Simulate normal work — 10 % chance of error."""
    time.sleep(random.uniform(0.01, 0.1))
    if random.random() < 0.10:
        ERROR_COUNTER.labels(endpoint="/work", error_type="processing_error").inc()
        logger.error("processing error occurred", extra={"extra": {"endpoint": "/work"}})
        return jsonify({"error": "processing failed"}), 500
    return jsonify({"result": "success", "processed": True})

@app.route("/error-flood")
def error_flood():
    """
    Trigger endpoint — generates ~20 errors in quick succession so the
    Prometheus alert rule (>5 errors/min) fires within seconds.
    """
    errors_generated = 0
    for _ in range(20):
        ERROR_COUNTER.labels(endpoint="/error-flood", error_type="simulated_critical").inc()
        logger.error(
            "simulated critical error",
            extra={"extra": {"endpoint": "/error-flood", "simulated": True}},
        )
        errors_generated += 1
        time.sleep(0.05)
    logger.warning("error flood complete", extra={"extra": {"errors_generated": errors_generated}})
    return jsonify({"message": "error flood complete", "errors_generated": errors_generated}), 200

@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("starting demo-app", extra={"extra": {"port": port}})
    app.run(host="0.0.0.0", port=port)
