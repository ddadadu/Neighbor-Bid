import sqlite3
import uuid
from functools import wraps

from flask import Blueprint, jsonify, request, session

from .db import get_db, now

bp = Blueprint("api", __name__, url_prefix="/api")


def current_guest():
    """세션 쿠키의 guest_id로 현재 사용자 조회. 없으면 None."""
    gid = session.get("guest_id")
    if not gid:
        return None
    with get_db() as db:
        row = db.execute("SELECT id, nickname FROM guests WHERE id = ?", (gid,)).fetchone()
    return dict(row) if row else None


def login_required(f):
    """입장한 사용자만 호출할 수 있는 API에 붙이는 데코레이터 (T1-3부터 사용)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        guest = current_guest()
        if guest is None:
            return jsonify(error="먼저 닉네임으로 입장해 주세요."), 401
        return f(guest, *args, **kwargs)
    return wrapper


@bp.post("/enter")
def enter():
    data = request.get_json(silent=True) or {}
    nickname = (data.get("nickname") or "").strip()

    if not (2 <= len(nickname) <= 12):
        return jsonify(error="닉네임은 2~12자로 입력해 주세요."), 400

    # 이미 입장한 브라우저면 기존 정보 반환
    me = current_guest()
    if me:
        return jsonify(me)

    gid = str(uuid.uuid4())
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO guests (id, nickname, created_at) VALUES (?, ?, ?)",
                (gid, nickname, now()),
            )
    except sqlite3.IntegrityError:
        return jsonify(error="이미 사용 중인 닉네임입니다."), 409

    session.permanent = True          # 7일 유지 (PERMANENT_SESSION_LIFETIME)
    session["guest_id"] = gid
    return jsonify(id=gid, nickname=nickname), 201


@bp.get("/me")
def me():
    guest = current_guest()
    if guest is None:
        return jsonify(error="입장 정보가 없습니다."), 401
    return jsonify(guest)


@bp.post("/leave")
def leave():
    session.clear()
    return jsonify(ok=True)