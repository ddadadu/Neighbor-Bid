const $ = (id) => document.getElementById(id);
const itemId = Number(new URLSearchParams(location.search).get("id"));
let item = null;

// ---------- 데이터 불러오기·그리기 ----------
async function load() {
  try {
    item = await api(`/api/items/${itemId}`);
    syncServerTime(item.server_now);
    render();
  } catch (err) {
    $("detail").hidden = true;
    $("error").textContent = err.message;
  }
}

function render() {
  $("detail").hidden = false;
  $("image").src = item.image_url;
  $("title").textContent = item.title;
  $("seller").textContent = `판매자: ${item.seller_nickname}`;
  $("description").textContent = item.description;
  $("price").textContent = won(item.current_price);
  $("status").textContent = STATUS_LABEL[item.status];
  $("status").className = `badge ${item.status}`;

  const open = item.status === "OPEN";
  $("amount").min = item.current_price + 500;
  $("amount").value = item.current_price + 500;
  $("bid-btn").disabled = !open || item.is_seller;
  if (item.is_seller && open) $("bid-msg").textContent = "본인 물품에는 입찰할 수 없습니다.";

  $("winner").textContent =
    item.status === "CLOSED" ? `낙찰자: ${item.top_bidder_nickname} (${won(item.current_price)})`
    : item.status === "FAILED" ? "입찰자가 없어 유찰되었습니다." : "";

  $("chat-link").hidden = !(item.status === "CLOSED" && (item.is_seller || item.is_winner));
  $("chat-link").href = `/chat.html?id=${item.id}`;

  $("bids").innerHTML = item.bids.length
    ? item.bids.map((b) => `<li>${escapeHtml(b.nickname)} · ${won(b.amount)}</li>`).join("")
    : "<li class='muted'>아직 입찰이 없습니다.</li>";
  tick();
}

function tick() {
  if (!item || item.status !== "OPEN") { $("left").textContent = ""; return; }
  const sec = secondsLeft(item.end_at);
  $("left").textContent = sec > 0 ? `남은 시간 ${fmtLeft(sec)}` : "마감 처리 중...";
  // 마감 결과는 서버의 auction_end 이벤트로 받음
}

function flash() {
  $("price").classList.remove("flash");
  void $("price").offsetWidth;      // 애니메이션 재시작
  $("price").classList.add("flash");
}

// ---------- 실시간 연결 ----------
const socket = io();   // 같은 주소의 /socket.io 로 연결 (세션 쿠키 자동 전송)

socket.on("connect", () => {
  socket.emit("join_auction", { item_id: itemId });
});

socket.on("connect_error", (err) => {
  $("bid-msg").textContent = `실시간 연결 실패: ${err.message}`;
});

socket.on("new_bid", (d) => {
  if (!item || d.item_id !== item.id) return;
  item.current_price = d.current_price;
  item.top_bidder_nickname = d.nickname;
  item.bids.unshift({ nickname: d.nickname, amount: d.current_price, created_at: d.time });
  item.bids = item.bids.slice(0, 20);
  render();
  flash();
});

socket.on("auction_end", (d) => {
  if (item && d.id === item.id) load();   // 낙찰자, 채팅 버튼까지 다시 불러옴
});

// ---------- 입찰 ----------
$("bid-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const amount = Number($("amount").value);
  $("bid-btn").disabled = true;
  $("bid-msg").textContent = "입찰 중...";

  socket.timeout(5000).emit("place_bid", { item_id: itemId, amount }, (err, res) => {
    $("bid-btn").disabled = item.status !== "OPEN" || item.is_seller;
    if (err) { $("bid-msg").textContent = "응답이 없습니다. 다시 시도해 주세요."; return; }
    $("bid-msg").textContent = res.ok ? `${won(amount)} 입찰 성공!` : res.reason;
  });
});

socket.on("auction_deleted", (d) => {
  if (d.id !== itemId) return;
  $("detail").hidden = true;
  $("error").textContent = "종료되어 삭제된 경매입니다.";
});

// ---------- 시작 ----------
(async () => {
  const me = await getMe();
  if (!me) { location.href = "/"; return; }   // 입찰은 입장한 사용자만
  $("who").textContent = `${me.nickname}님`;
  if (!itemId) { $("error").textContent = "잘못된 주소입니다."; return; }
  await load();
  setInterval(tick, 1000);
})();