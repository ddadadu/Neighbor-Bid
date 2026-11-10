import os

from . import r
from .db import get_db, now
from .lock import LockBusy, item_lock

MIN_STEP = 500
CLEANUP_AFTER_MIN = int(os.environ.get("CLEANUP_AFTER_MIN", "30"))
GUEST_IDLE_SEC = 24 * 3600   # 1일 (쿠키 유효기간과 동일)


# ---------- 마감 ----------

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
        # status='OPEN' 조건으로 다른 요청이 먼저 바꾼 경우 중복 처리 방지
        cur = db.execute("UPDATE items SET status = ? WHERE id = ? AND status = 'OPEN'",
                         (status, row["id"]))
        if cur.rowcount == 1:
            closed.append({"id": row["id"], "status": status,
                           "final_price": row["current_price"]})
    return closed


# ---------- 입찰 (Redis 락 + 조건부 UPDATE 2중 보호) ----------

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
                # 최종 판정: 조건이 맞을 때만 갱신 (락이 없어도 중복 낙찰이 생기지 않음)
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


# ---------- 1:1 채팅 권한 ----------

CHAT_ERRORS = {
    "not_found": "종료되어 삭제되었거나 없는 경매입니다.",
    "forbidden": "판매자와 낙찰자만 이용할 수 있는 채팅입니다.",
}


def chat_access(db, item_id, guest_id):
    """1:1 채팅 권한 확인. (item_row, 'ok' | 'not_found' | 'forbidden')"""
    row = db.execute(
        "SELECT id, title, status, seller_id, top_bidder_id, end_at FROM items WHERE id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        return None, "not_found"
    if row["status"] != "CLOSED" or guest_id not in (row["seller_id"], row["top_bidder_id"]):
        return row, "forbidden"
    return row, "ok"


# ---------- 자동 정리 ----------

def cleanup_expired(db):
    """종료 후 유예 시간이 지난 경매를 DB에서 삭제하고, 지울 사진 키 목록을 돌려준다.
    사진 삭제는 커밋 이후에 호출한 쪽에서 한다."""
    cutoff = now() - CLEANUP_AFTER_MIN * 60
    rows = db.execute(
        "SELECT id, image_key FROM items WHERE status != 'OPEN' AND end_at <= ?",
        (cutoff,),
    ).fetchall()
    if not rows:
        return []
    ids = [row["id"] for row in rows]
    placeholders = ",".join("?" * len(ids))
    # bids, messages는 ON DELETE CASCADE로 함께 삭제됨
    db.execute(f"DELETE FROM items WHERE id IN ({placeholders})", ids)
    return [{"id": row["id"], "image_key": row["image_key"]} for row in rows]


def cleanup_idle_guests(db):
    """기록이 없고, (나가기를 눌렀거나 1일 이상 활동이 없는) 게스트 삭제 → 닉네임 반납"""
    cutoff = now() - GUEST_IDLE_SEC
    cur = db.execute(
        """DELETE FROM guests
           WHERE (left_at IS NOT NULL OR COALESCE(last_seen, created_at) <= ?)
             AND id NOT IN (SELECT seller_id FROM items)
             AND id NOT IN (SELECT top_bidder_id FROM items WHERE top_bidder_id IS NOT NULL)
             AND id NOT IN (SELECT guest_id FROM bids)
             AND id NOT IN (SELECT guest_id FROM messages)""",
        (cutoff,),
    )
    return cur.rowcount