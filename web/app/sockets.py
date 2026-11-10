from flask_socketio import ConnectionRefusedError, join_room

from . import socketio
from .auction import (CHAT_ERRORS, chat_access, cleanup_expired, cleanup_idle_guests,
                      close_expired, place_bid)
from .db import get_db, now
from .routes import current_guest
from .storage import delete_image


# ---------- 공통 ----------

def auction_room(item_id):
    return f"auction:{item_id}"


def chat_room(item_id):
    return f"chat:{item_id}"


def emit_closed(closed):
    for c in closed:
        socketio.emit("auction_end", c, to=auction_room(c["id"]))


# ---------- 연결 ----------

@socketio.on("connect")
def on_connect(auth=None):
    ensure_background_loop()
    # 세션 쿠키가 소켓 연결에도 함께 전송된다 → 입장하지 않았거나 나간 사용자는 거부
    if current_guest() is None:
        raise ConnectionRefusedError("먼저 닉네임으로 입장해 주세요.")


# ---------- 실시간 입찰 ----------

@socketio.on("join_auction")
def on_join_auction(data):
    try:
        item_id = int(data.get("item_id"))
    except (TypeError, ValueError, AttributeError):
        return {"ok": False, "reason": "잘못된 요청입니다."}
    join_room(auction_room(item_id))
    return {"ok": True}


@socketio.on("place_bid")
def on_place_bid(data):
    guest = current_guest()
    if guest is None:
        return {"ok": False, "reason": "먼저 닉네임으로 입장해 주세요."}
    try:
        item_id = int(data.get("item_id"))
        amount = int(data.get("amount"))
    except (TypeError, ValueError, AttributeError):
        return {"ok": False, "reason": "입찰 금액을 확인해 주세요."}

    ok, reason, payload, closed = place_bid(guest, item_id, amount)
    emit_closed(closed)
    if ok:
        # 커밋이 끝난 뒤에 경매방 전체에 전송
        socketio.emit("new_bid", payload, to=auction_room(item_id))
    return {"ok": ok, "reason": reason}


# ---------- 1:1 채팅 ----------

@socketio.on("join_chat")
def on_join_chat(data):
    guest = current_guest()
    if guest is None:
        return {"ok": False, "reason": "먼저 닉네임으로 입장해 주세요."}
    try:
        item_id = int(data.get("item_id"))
    except (TypeError, ValueError, AttributeError):
        return {"ok": False, "reason": "잘못된 요청입니다."}

    with get_db() as db:
        _, status = chat_access(db, item_id, guest["id"])
    if status != "ok":
        return {"ok": False, "reason": CHAT_ERRORS[status]}

    join_room(chat_room(item_id))
    return {"ok": True}


@socketio.on("chat_message")
def on_chat_message(data):
    guest = current_guest()
    if guest is None:
        return {"ok": False, "reason": "먼저 닉네임으로 입장해 주세요."}
    try:
        item_id = int(data.get("item_id"))
        content = str(data.get("content", "")).strip()
    except (TypeError, ValueError, AttributeError):
        return {"ok": False, "reason": "잘못된 요청입니다."}

    if not content:
        return {"ok": False, "reason": "메시지를 입력해 주세요."}
    if len(content) > 200:
        return {"ok": False, "reason": "메시지는 200자 이하로 입력해 주세요."}

    with get_db() as db:
        # room에 들어와 있더라도 보낼 때마다 다시 확인
        _, status = chat_access(db, item_id, guest["id"])
        if status != "ok":
            return {"ok": False, "reason": CHAT_ERRORS[status]}
        t = now()
        cur = db.execute(
            "INSERT INTO messages (item_id, guest_id, content, created_at) VALUES (?, ?, ?, ?)",
            (item_id, guest["id"], content, t),
        )
        msg_id = cur.lastrowid

    socketio.emit("chat_message", {
        "id": msg_id, "item_id": item_id, "guest_id": guest["id"],
        "nickname": guest["nickname"], "content": content, "created_at": t,
    }, to=chat_room(item_id))
    return {"ok": True}


# ---------- 마감·정리 백그라운드 루프 ----------

def _closer_loop():
    """1초마다 마감 처리, 10초마다 종료된 경매 정리 + 닉네임 반납 (워커 1개라 한 번만 실행)."""
    print("[closer] loop running", flush=True)
    tick = 0
    while True:
        socketio.sleep(1)
        tick += 1
        try:
            with get_db() as db:
                closed = close_expired(db)
            emit_closed(closed)

            if tick % 10 == 0:
                # 종료된 경매 정리 (블록이 끝나며 커밋 → 그 다음 사진 삭제)
                with get_db() as db:
                    removed = cleanup_expired(db)
                for it in removed:
                    delete_image(it["image_key"])
                    payload = {"id": it["id"]}
                    socketio.emit("auction_deleted", payload, to=auction_room(it["id"]))
                    socketio.emit("auction_deleted", payload, to=chat_room(it["id"]))
                if removed:
                    print(f"[cleanup] removed items {[it['id'] for it in removed]}", flush=True)

                # 기록이 사라진 닉네임 반납 (경매 정리 바로 뒤라 즉시 반영)
                with get_db() as db:
                    n = cleanup_idle_guests(db)
                if n:
                    print(f"[cleanup] released {n} nicknames", flush=True)
        except Exception as e:
            print(f"[closer] {e!r}", flush=True)


_loop_started = False


def ensure_background_loop():
    """루프를 한 번만 시작한다 (첫 HTTP 요청이나 첫 소켓 연결 때 호출)."""
    global _loop_started
    if not _loop_started:
        _loop_started = True
        socketio.start_background_task(_closer_loop)
        print("[closer] background loop started", flush=True)