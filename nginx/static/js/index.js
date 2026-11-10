const $ = (id) => document.getElementById(id);

function showMain(me) {
  $("enter").hidden = true;
  $("main").hidden = false;
  $("who").textContent = `${me.nickname}님`;
}

$("enter-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("enter-error").textContent = "";
  try {
    const me = await api("/api/enter", {
      method: "POST",
      body: { nickname: $("nickname").value },
    });
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