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

// 서버 시계 기준 남은 시간 계산 (PC 시계가 틀려도 정확하도록)
let serverOffset = 0;   // 서버시각 - 내PC시각 (초)
function syncServerTime(serverNow) {
  serverOffset = serverNow - Date.now() / 1000;
}
function secondsLeft(endAt) {
  return Math.max(0, Math.floor(endAt - (Date.now() / 1000 + serverOffset)));
}
function fmtLeft(sec) {
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}
const STATUS_LABEL = { OPEN: "진행 중", CLOSED: "낙찰", FAILED: "유찰" };

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}