import os
import sqlite3
import uuid
from functools import wraps
from .auction import close_expired

from flask import Blueprint, jsonify, request, send_from_directory, session

from .db import get_db, now
from .storage import LOCAL_DIR, UploadError, delete_image, save_image

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

# ---------- 물품 등록 ----------

DURATIONS = {5, 10, 30}   # 분


@bp.post("/items")
@login_required
def create_item(guest):
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    try:
        start_price = int(request.form.get("start_price", ""))
        duration = int(request.form.get("duration", ""))
    except ValueError:
        return jsonify(error="시작가와 경매 시간을 확인해 주세요."), 400

    if not (2 <= len(title) <= 40):
        return jsonify(error="물품명은 2~40자로 입력해 주세요."), 400
    if len(description) > 500:
        return jsonify(error="설명은 500자 이하로 입력해 주세요."), 400
    if start_price < 1000 or start_price % 500 != 0:
        return jsonify(error="시작가는 1,000원 이상, 500원 단위로 입력해 주세요."), 400
    if duration not in DURATIONS:
        return jsonify(error="경매 시간은 5, 10, 30분 중에서 선택해 주세요."), 400

    file = request.files.get("image")
    if file is None:
        return jsonify(error="사진을 선택해 주세요."), 400

    try:
        image_key, image_url = save_image(file)
    except UploadError as e:
        return jsonify(error=str(e)), 400

    t = now()
    try:
        with get_db() as db:
            cur = db.execute(
                """INSERT INTO items (seller_id, title, description, image_key, image_url,
                                      start_price, current_price, status, end_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)""",
                (guest["id"], title, description, image_key, image_url,
                 start_price, start_price, t + duration * 60, t),
            )
            item_id = cur.lastrowid
    except Exception:
        delete_image(image_key)          # DB 저장 실패 시 올린 사진 정리
        raise

    return jsonify(id=item_id, image_url=image_url), 201


# 로컬 저장 모드에서만 사진 제공 (S3 모드에서는 S3 URL을 직접 사용)
@bp.get("/uploads/<path:key>")
def local_upload(key):
    return send_from_directory(LOCAL_DIR, key)

# ---------- 목록·상세 ----------

ITEM_SELECT = """
SELECT i.*, s.nickname AS seller_nickname, b.nickname AS top_bidder_nickname
FROM items i
JOIN guests s ON s.id = i.seller_id
LEFT JOIN guests b ON b.id = i.top_bidder_id
"""


def item_json(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "image_url": row["image_url"],
        "start_price": row["start_price"],
        "current_price": row["current_price"],
        "status": row["status"],
        "end_at": row["end_at"],
        "seller_id": row["seller_id"],
        "seller_nickname": row["seller_nickname"],
        "top_bidder_nickname": row["top_bidder_nickname"],
    }


@bp.get("/items")
def list_items():
    with get_db() as db:
        close_expired(db)
        rows = db.execute(
            ITEM_SELECT +
            " ORDER BY (i.status = 'OPEN') DESC, "       # 진행 중 먼저
            " CASE WHEN i.status = 'OPEN' THEN i.end_at END ASC, "   # 마감 임박 순
            " i.end_at DESC"                              # 종료된 것은 최근 순
        ).fetchall()
    return jsonify(items=[item_json(r) for r in rows], server_now=now())


@bp.get("/items/<int:item_id>")
def get_item(item_id):
    me = current_guest()
    with get_db() as db:
        close_expired(db)
        row = db.execute(ITEM_SELECT + " WHERE i.id = ?", (item_id,)).fetchone()
        if row is None:
            return jsonify(error="종료되어 삭제되었거나 없는 경매입니다."), 404
        bids = db.execute(
            """SELECT b.amount, b.created_at, g.nickname
               FROM bids b JOIN guests g ON g.id = b.guest_id
               WHERE b.item_id = ? ORDER BY b.id DESC LIMIT 20""",
            (item_id,),
        ).fetchall()

    data = item_json(row)
    data["bids"] = [dict(b) for b in bids]
    data["is_seller"] = bool(me and me["id"] == row["seller_id"])
    data["is_winner"] = bool(me and row["status"] == "CLOSED"
                             and me["id"] == row["top_bidder_id"])
    data["server_now"] = now()
    return jsonify(data)