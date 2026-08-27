// 批量抓取：提交 → 轮询任务状态 → 渲染结果与逐批入库
const form = document.getElementById('crawl-form');
const btn = document.getElementById('crawl-btn');
const statusEl = document.getElementById('crawl-status');
const resultsEl = document.getElementById('crawl-results');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = document.getElementById('crawl-query').value.trim();
  if (!query) return;
  btn.disabled = true;
  statusEl.textContent = '抓取中，请稍候…';
  resultsEl.innerHTML = '';
  try {
    const r = await fetch('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        source: document.getElementById('crawl-source').value,
        limit: parseInt(document.getElementById('crawl-limit').value, 10),
        location: document.getElementById('crawl-location').value.trim(),
      }),
    });
    if (!r.ok) {
      const msg = await r.json().catch(() => ({}));
      statusEl.textContent = `提交失败（${r.status}）${msg.detail || ''}`;
      btn.disabled = false;
      return;
    }
    const { job_id } = await r.json();
    poll(job_id, 60);
  } catch {
    statusEl.textContent = '网络异常，请重试。';
    btn.disabled = false;
  }
});

async function poll(jid, left) {
  if (left <= 0) {
    statusEl.textContent = '抓取超时（图库网络慢？），请稍后重试。';
    btn.disabled = false;
    return;
  }
  setTimeout(async () => {
    try {
      const st = await (await fetch(`/api/crawl/status/${jid}`)).json();
      if (!st.done) return poll(jid, left - 1);
      render(st);
    } catch {
      poll(jid, left - 1);
      return;
    }
    btn.disabled = false;
  }, 2000);
}

function render(st) {
  const parts = [`完成：成功 ${st.added} 张。`]
    .concat((st.logs || []).map((l) => `<div class="hint">${l}</div>`));
  statusEl.innerHTML = parts.join('');
  if (!st.rows.length) return;
  const table = ['<table class="crawl-tb"><tr><th>标题</th><th>许可</th>',
    '<th>来源</th></tr>'];
  for (const row of st.rows) {
    table.push(
      `<tr><td>${row.title}</td><td>${row.license}</td>` +
      `<td><a href="${row.source_url}" target="_blank" rel="noopener">详情</a></td></tr>`);
  }
  table.push('</table>');
  const pids = st.rows.map((r) => r.photo_id);
  resultsEl.innerHTML =
    table.join('') +
    `<button class="chip" id="ingest-all">全部入库（后台管线）</button>` +
    `<span class="hint" id="ingest-note"></span>`;
  document.getElementById('ingest-all').addEventListener('click',
    async () => {
      const note = document.getElementById('ingest-note');
      note.textContent = '已提交入库任务…';
      const resp = await fetch('/api/ingest-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pids }),
      });
      if (resp.ok) {
        note.textContent = `已排队 ${pids.length} 张；完成请刷新首页查看` +
          `(日志 data/logs/)`;
      } else {
        const msg = await resp.json().catch(() => ({}));
        note.textContent = `提交失败：${msg.detail || resp.status}`;
      }
    });
}
