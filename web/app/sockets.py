from flask_socketio import ConnectionRefusedError, join_room

from . import socketio
from .auction import close_expired, place_bid
from .db import get_db
from .routes import current_guest
from .auction import CHAT_ERRORS, chat_access, close_expired, place_bid
from .db import get_db, now

def auction_room(item_id):
    return f"auction:{item_id}"


def emit_closed(closed):
    for c in closed:
        socketio.emit("auction_end", c, to=auction_room(c["id"]))


@socketio.on("connect")
def on_connect(auth=None):
    # 세션 쿠키가 소켓 연결에도 함께 전송된다 → 입장하지 않았으면 연결 거부
    if current_guest() is None:
        raise ConnectionRefusedError("먼저 닉네임으로 입장해 주세요.")


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
        # ④ 커밋이 끝난 뒤에 경매방 전체에 전송
        socketio.emit("new_bid", payload, to=auction_room(item_id))
    return {"ok": ok, "reason": reason}

# ---------- 1:1 채팅 ----------

def chat_room(item_id):
    return f"chat:{item_id}"


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

def _closer_loop():
    """1초마다 마감된 경매를 정리하고 경매방에 알린다 (워커 1개라 한 번만 실행됨)."""
    while True:
        socketio.sleep(1)
        try:
            with get_db() as db:
                closed = close_expired(db)
            emit_closed(closed)
        except Exception as e:
            print(f"[closer] {e!r}", flush=True)


socketio.start_background_task(_closer_loop)