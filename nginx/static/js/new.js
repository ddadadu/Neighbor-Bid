const $ = (id) => document.getElementById(id);

(async () => {
  const me = await getMe();
  if (!me) { location.href = "/"; return; }   // 입장하지 않았으면 메인으로
  $("who").textContent = `${me.nickname}님`;
})();

// 사진 미리보기
$("image").addEventListener("change", () => {
  const f = $("image").files[0];
  if (!f) { $("preview").hidden = true; return; }
  $("preview").src = URL.createObjectURL(f);
  $("preview").hidden = false;
});

$("item-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("error").textContent = "";

  const f = $("image").files[0];
  if (f && f.size > 5 * 1024 * 1024) {          // 서버에 보내기 전에 빠르게 안내
    $("error").textContent = "사진은 5MB 이하만 가능합니다.";
    return;
  }

  $("submit").disabled = true;
  try {
    const res = await api("/api/items", { method: "POST", body: new FormData(e.target) });
    location.href = `/item.html?id=${res.id}`;   // T1-4에서 상세 화면 구현
  } catch (err) {
    $("error").textContent = err.message;
  } finally {
    $("submit").disabled = false;
  }
});