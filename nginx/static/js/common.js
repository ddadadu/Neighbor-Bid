// 공통 fetch 헬퍼: JSON 응답과 오류 메시지를 한 번에 처리
async function api(path, options = {}) {
  const opts = { credentials: "same-origin", ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data;
}

async function getMe() {
  try { return await api("/api/me"); } catch { return null; }
}

function won(n) {
  return Number(n).toLocaleString("ko-KR") + "원";
}