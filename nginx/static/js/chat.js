const $ = (id) => document.getElementById(id);
const itemId = Number(new URLSearchParams(location.search).get("id"));
let myId = null;

function fmtTime(epoch) {
  return new Date(epoch * 1000).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
}

function addMessage(m) {
  const li = document.createElement("li");
  li.className = m.guest_id === myId ? "mine" : "theirs";
  li.innerHTML = `
    <span class="who">${escapeHtml(m.nickname)}</span>
    <span class="bubble">${escapeHtml(m.content)}</span>
    <span class="time">${fmtTime(m.created_at)}</span>`;
  $("messages").appendChild(li);
  li.scrollIntoView({ block: "end" });
}

async function load() {
  const data = await api(`/api/items/${itemId}/messages`);   // 권한 없으면 여기서 오류
  myId = data.me.id;
  $("chat").hidden = false;
  $("back").href = `/item.html?id=${itemId}`;
  $("title").textContent = data.item.title;
  $("partner").textContent = `${data.me.role}로 참여 중 · 상대: ${data.partner}`;
  $("notice").textContent =
    `경매 종료 ${data.cleanup_after_min}분 후 대화와 경매 기록이 자동 삭제됩니다.`;
  $("messages").innerHTML = "";
  data.messages.forEach(addMessage);
}

// ---------- 실시간 ----------
const socket = io({ autoConnect: false });

socket.on("connect", () => {
  socket.emit("join_chat", { item_id: itemId }, (res) => {
    if (!res.ok) $("chat-msg").textContent = res.reason;
  });
});

socket.on("connect_error", (err) => {
  $("chat-msg").textContent = `실시간 연결 실패: ${err.message}`;
});

socket.on("chat_message", (m) => {
  if (m.item_id === itemId) addMessage(m);
});

$("chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const content = $("content").value.trim();
  if (!content) return;
  $("send").disabled = true;

  socket.timeout(5000).emit("chat_message", { item_id: itemId, content }, (err, res) => {
    $("send").disabled = false;
    if (err) { $("chat-msg").textContent = "응답이 없습니다. 다시 시도해 주세요."; return; }
    if (res.ok) { $("content").value = ""; $("chat-msg").textContent = ""; }
    else $("chat-msg").textContent = res.reason;
  });
});

// ---------- 시작 ----------
(async () => {
  const me = await getMe();
  if (!me) { location.href = "/"; return; }
  $("who").textContent = `${me.nickname}님`;
  if (!itemId) { $("error").textContent = "잘못된 주소입니다."; return; }

  try {
    await load();
    socket.connect();          // 권한이 확인된 경우에만 소켓 연결
  } catch (err) {
    $("error").textContent = err.message;   // 제3자: "판매자와 낙찰자만 이용할 수 있는 채팅입니다."
  }
})();