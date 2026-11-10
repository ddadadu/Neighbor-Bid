var $ = (id) => document.getElementById(id);
var items = [];

function showMain(me) {
  $("enter").hidden = true;
  $("main").hidden = false;
  $("leave").hidden = false;
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

// ---------- 입장 ----------
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

// ---------- 나가기 ----------
$("leave").addEventListener("click", async () => {
  const me = await getMe();
  if (me && me.active_count > 0) {
    const ok = confirm(
      `진행 중인 경매나 낙찰 채팅이 ${me.active_count}건 있습니다.\n` +
      "나가면 이 닉네임으로 다시 들어올 수 없어 경매와 채팅에 참여할 수 없습니다.\n" +
      "닉네임은 경매 기록이 정리된 뒤(종료 30분 후) 다시 사용할 수 있습니다.\n\n" +
      "정말 나가시겠어요?"
    );
    if (!ok) return;
  } else if (me && me.has_records) {
    const ok = confirm("이 닉네임은 남은 기록이 정리될 때까지 사용할 수 없습니다.\n나가시겠어요?");
    if (!ok) return;
  }
  await api("/api/leave", { method: "POST" });
  location.reload();
});

// ---------- 시작 ----------
(async () => {
  const me = await getMe();
  if (me) showMain(me);
  else $("enter").hidden = false;
})();