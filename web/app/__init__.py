import eventlet
eventlet.monkey_patch()  # 반드시 다른 import보다 먼저

import os
from datetime import timedelta

import redis
from flask import Flask, jsonify
from flask_socketio import SocketIO

from .db import get_db, init_db

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    SESSION_COOKIE_HTTPONLY=True,          # JS에서 쿠키 접근 차단
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(days=1),   # 닉네임 미접속 반납 기준과 동일
    MAX_CONTENT_LENGTH=6 * 1024 * 1024,    # 요청 전체 6MB 제한
)

# Redis: Socket.IO 메시지 큐(서버 확장 대비) + 입찰 락
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

socketio = SocketIO(app, async_mode="eventlet", message_queue=REDIS_URL)

r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

init_db()

# app, socketio, r 생성 이후에 import (routes·sockets·auction이 이 객체들을 사용)
from .routes import bp as api_bp    # noqa: E402
app.register_blueprint(api_bp)

from . import sockets                # noqa: E402  (소켓 이벤트 등록)


@app.before_request
def _start_loop():
    sockets.ensure_background_loop()   # 마감·정리 루프를 첫 요청 때 한 번 시작


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


@app.errorhandler(413)
def too_large(_e):
    return jsonify(error="사진은 5MB 이하만 가능합니다."), 413