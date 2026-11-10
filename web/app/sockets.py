from flask_socketio import ConnectionRefusedError, join_room

from . import socketio
from .auction import close_expired, place_bid
from .db import get_db
from .routes import current_guest


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