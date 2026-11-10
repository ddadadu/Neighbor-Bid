from . import r
from .db import get_db, now
from .lock import LockBusy, item_lock

MIN_STEP = 500


def close_expired(db):
    """마감 시각이 지난 OPEN 경매를 낙찰(CLOSED) 또는 유찰(FAILED)로 바꾸고, 바뀐 목록을 돌려준다."""
    t = now()
    rows = db.execute(
        "SELECT id, top_bidder_id, current_price FROM items WHERE status = 'OPEN' AND end_at <= ?",
        (t,),
    ).fetchall()
    closed = []
    for row in rows:
        status = "CLOSED" if row["top_bidder_id"] else "FAILED"
        cur = db.execute("UPDATE items SET status = ? WHERE id = ? AND status = 'OPEN'",
                         (status, row["id"]))
        if cur.rowcount == 1:
            closed.append({"id": row["id"], "status": status,
                           "final_price": row["current_price"]})
    return closed


def place_bid(guest, item_id, amount):
    """입찰 처리. (ok, reason, payload, closed) 를 돌려준다."""
    if amount % MIN_STEP != 0:
        return False, f"입찰은 {MIN_STEP}원 단위로 가능합니다.", None, []

    try:
        with item_lock(r, item_id):                      # ① Redis 락
            with get_db() as db:                         # ② DB 트랜잭션
                closed = close_expired(db)
                item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

                if item is None:
                    return False, "없는 경매입니다.", None, closed
                if item["status"] != "OPEN":
                    return False, "이미 마감된 경매입니다.", None, closed
                if item["seller_id"] == guest["id"]:
                    return False, "본인 물품에는 입찰할 수 없습니다.", None, closed
                if item["top_bidder_id"] == guest["id"]:
                    return False, "이미 최고 입찰자입니다.", None, closed
                if amount < item["current_price"] + MIN_STEP:
                    return False, f"현재가보다 {MIN_STEP}원 이상 높게 입찰해 주세요.", None, closed

                t = now()
                # 최종 판정: 조건이 맞을 때만 갱신 (락이 없어도 중복 낙찰이 생기지 않는 2중 보호)
                cur = db.execute(
                    """UPDATE items SET current_price = ?, top_bidder_id = ?
                       WHERE id = ? AND status = 'OPEN' AND end_at > ?
                         AND current_price + ? <= ?""",
                    (amount, guest["id"], item_id, t, MIN_STEP, amount),
                )
                if cur.rowcount != 1:
                    return False, "다른 입찰이 먼저 처리되었습니다. 다시 시도해 주세요.", None, closed

                db.execute(
                    "INSERT INTO bids (item_id, guest_id, amount, created_at) VALUES (?, ?, ?, ?)",
                    (item_id, guest["id"], amount, t),
                )
            # with get_db() 블록이 끝나면서 커밋됨
    except LockBusy:
        return False, "입찰이 몰리고 있습니다. 잠시 후 다시 시도해 주세요.", None, []

    payload = {"item_id": item_id, "current_price": amount,
               "nickname": guest["nickname"], "time": t}
    return True, "", payload, closed