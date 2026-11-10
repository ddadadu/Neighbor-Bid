import time
import uuid
from contextlib import contextmanager

# 내가 건 락일 때만 지운다 (다른 요청의 락을 실수로 지우지 않도록)
RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


class LockBusy(Exception):
    pass


@contextmanager
def item_lock(r, item_id, ttl_ms=3000, wait_sec=1.0, retry_sec=0.05):
    """물품별 Redis 락. with item_lock(r, 1): ... 안에서는 같은 물품의 입찰이 한 번에 하나만 처리된다."""
    key = f"lock:item:{item_id}"
    token = uuid.uuid4().hex
    deadline = time.monotonic() + wait_sec

    while not r.set(key, token, nx=True, px=ttl_ms):   # NX: 없을 때만 설정, PX: 자동 만료
        if time.monotonic() >= deadline:
            raise LockBusy()
        time.sleep(retry_sec)          # eventlet이 패치해서 다른 요청을 막지 않음

    try:
        yield
    finally:
        r.eval(RELEASE_LUA, 1, key, token)