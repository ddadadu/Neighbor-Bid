import eventlet
eventlet.monkey_patch()

import os
from datetime import timedelta

import redis
from flask import Flask, jsonify
from flask_socketio import SocketIO

from .db import init_db, get_db

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    SESSION_COOKIE_HTTPONLY=True,       # JS에서 쿠키 접근 차단
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

socketio = SocketIO(app, async_mode="eventlet")

r = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"),
                         decode_responses=True)

init_db()

from .routes import bp as api_bp   # noqa: E402  (app 생성 후 import)
app.register_blueprint(api_bp)


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

MAX_CONTENT_LENGTH=6 * 1024 * 1024,   # 요청 전체 6MB 제한
@app.errorhandler(413)
def too_large(_e):
    return jsonify(error="사진은 5MB 이하만 가능합니다."), 413