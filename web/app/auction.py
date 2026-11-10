from .db import now


def close_expired(db):
    """마감 시각이 지난 OPEN 경매를 낙찰(CLOSED) 또는 유찰(FAILED)로 바꾼다.
    바뀐 경매 목록을 돌려준다 (T2-3에서 실시간 알림에 사용)."""
    t = now()
    rows = db.execute(
        "SELECT id, top_bidder_id, current_price FROM items "
        "WHERE status = 'OPEN' AND end_at <= ?",
        (t,),
    ).fetchall()

    closed = []
    for row in rows:
        status = "CLOSED" if row["top_bidder_id"] else "FAILED"
        # status='OPEN' 조건으로 다른 요청이 먼저 바꾼 경우 중복 처리 방지
        cur = db.execute(
            "UPDATE items SET status = ? WHERE id = ? AND status = 'OPEN'",
            (status, row["id"]),
        )
        if cur.rowcount == 1:
            closed.append({"id": row["id"], "status": status,
                           "winner_id": row["top_bidder_id"],
                           "final_price": row["current_price"]})
    return closed