import eventlet
eventlet.monkey_patch()

import os
import redis
from flask import Flask, jsonify
from flask_socketio import SocketIO

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

socketio = SocketIO(app, async_mode="eventlet")

r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"),
                         decode_responses=True)


@app.get("/api/health")
def health():
    try:
        redis_ok = r.ping()
    except redis.RedisError:
        redis_ok = False
    status = "ok" if redis_ok else "degraded"
    return jsonify(status=status, redis=redis_ok), (200 if redis_ok else 503)