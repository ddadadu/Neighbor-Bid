import eventlet
eventlet.monkey_patch()

import os
import redis
from flask import Flask, jsonify
from flask_socketio import SocketIO

from .db import init_db, get_db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

socketio = SocketIO(app, async_mode="eventlet")

r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"),
                         decode_responses=True)

init_db()   # 앱 시작 시 테이블 생성 (이미 있으면 그대로)


@app.get("/api/health")
def health():
    try:
        redis_ok = r.ping()
    except redis.RedisError:
        redis_ok = False

    try:
        with get_db() as db:
            db.execute("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    ok = redis_ok and db_ok
    return jsonify(status="ok" if ok else "degraded",
                   redis=redis_ok, db=db_ok), (200 if ok else 503)