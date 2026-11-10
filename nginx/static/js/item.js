const $ = (id) => document.getElementById(id);
const itemId = Number(new URLSearchParams(location.search).get("id"));
let item = null;

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
  $("bid-msg").textContent = item.is_seller && open ? "본인 물품에는 입찰할 수 없습니다." : "";

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
  if (sec === 0) setTimeout(load, 1500);   // 마감되면 다시 불러와 결과 표시
}

$("bid-form").addEventListener("submit", (e) => {
  e.preventDefault();
  $("bid-msg").textContent = "실시간 입찰은 다음 단계(T2-2)에서 연결됩니다.";
});

(async () => {
  const me = await getMe();
  if (me) $("who").textContent = `${me.nickname}님`;
  if (!itemId) { $("error").textContent = "잘못된 주소입니다."; return; }
  await load();
  setInterval(tick, 1000);
})();