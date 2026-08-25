// 问答页 SSE 流式渲染（原生 JS，无框架）
const form = document.getElementById("ask-form");
const log = document.getElementById("chat-log");
const input = document.getElementById("ask-q");

function bubble(cls, html) {
  const div = document.createElement("div");
  div.className = `msg ${cls}`;
  div.innerHTML = html;
  log.appendChild(div);
  return div;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (!q) return;
  input.value = "";
  bubble("user", q);
  const box = bubble("ai", "<span class='hint'>讲解员思考中…</span>");
  let text = "";

  const resp = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ q }),
  });
  if (!resp.ok || !resp.body) {
    box.textContent = "服务暂不可用，请稍后再试。";
    return;
  }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "", meta = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (!line.startsWith("data:")) continue;
      const ev = JSON.parse(line.slice(5));
      if (ev.type === "delta") {
        text += ev.text;
        box.textContent = text;
      } else if (ev.type === "done") {
        meta = ev;
      }
    }
  }
  if (meta && !meta.refused && meta.photo_ids?.length) {
    const photos = document.createElement("div");
    photos.className = "msg ai photos";
    photos.innerHTML = meta.photo_ids
      .map((p) => `<a href="/photo/${p}"><img src="/media/${p}/restored.jpg"
        onerror="this.style.display='none'"></a>`).join("");
    log.appendChild(photos);
  }
});
