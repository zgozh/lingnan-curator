// 上传：提交 FormData → 轮询入库状态 → 跳详情页
const form = document.getElementById('up-form');
const btn = document.getElementById('up-btn');
const status = document.getElementById('up-status');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(form);
  btn.disabled = true;
  status.textContent = '上传中…';
  try {
    const resp = await fetch('/api/upload', { method: 'POST', body: fd });
    if (!resp.ok) {
      const msg = await resp.json().catch(() => ({}));
      status.textContent = `提交失败（${resp.status}）${msg.detail || ''}`;
      btn.disabled = false;
      return;
    }
    const data = await resp.json();
    status.textContent = `已提交（${data.photo_id}），后台入库中，请勿关闭页面…`;
    poll(data.status_url, data.photo_id, 60);
  } catch {
    status.textContent = '网络异常，请重试。';
    btn.disabled = false;
  }
});

function poll(url, pid, left) {
  if (left <= 0) {
    status.textContent = '入库超时，可稍后刷新照片墙查看；日志见 data/logs/。';
    return;
  }
  setTimeout(async () => {
    try {
      const r = await fetch(url);
      const d = await r.json();
      if (d.stored) {
        window.location.href = `/photo/${pid}`;
        return;
      }
    } catch { /* 忽略单次轮询失败 */ }
    poll(url, pid, left - 1);
  }, 5000);
}
