const $ = (id) => document.getElementById(id);
let items = [];

function showMain(me) {
  $("enter").hidden = true;
  $("main").hidden = false;
  $("who").textContent = `${me.nickname}님`;
  loadItems();
  setInterval(loadItems, 10000);   // 10초마다 목록 새로고침
  setInterval(tick, 1000);         // 1초마다 남은 시간 갱신
}

async function loadItems() {
  try {
    const data = await api("/api/items");
    syncServerTime(data.server_now);
    items = data.items;
    render();
  } catch (err) {
    $("items").innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
  }
}

function render() {
  if (items.length === 0) {
    $("items").innerHTML = "<p>아직 등록된 경매가 없습니다.</p>";
    return;
  }
  $("items").innerHTML = items.map((it) => `
    <a class="card ${it.status !== "OPEN" ? "ended" : ""}" href="/item.html?id=${it.id}">
      <img src="${escapeHtml(it.image_url)}" alt="">
      <div class="info">
        <strong>${escapeHtml(it.title)}</strong>
        <span class="price">${won(it.current_price)}</span>
        <span class="badge ${it.status}">${STATUS_LABEL[it.status]}</span>
        <span class="left" data-end="${it.end_at}" data-status="${it.status}"></span>
      </div>
    </a>`).join("");
  tick();
}

function tick() {
  document.querySelectorAll(".left").forEach((el) => {
    if (el.dataset.status !== "OPEN") { el.textContent = ""; return; }
    const sec = secondsLeft(Number(el.dataset.end));
    el.textContent = sec > 0 ? `남은 시간 ${fmtLeft(sec)}` : "마감 처리 중...";
  });
}

$("enter-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("enter-error").textContent = "";
  try {
    const me = await api("/api/enter", { method: "POST", body: { nickname: $("nickname").value } });
    showMain(me);
  } catch (err) {
    $("enter-error").textContent = err.message;
  }
});

(async () => {
  const me = await getMe();
  if (me) showMain(me);
  else $("enter").hidden = false;
})();