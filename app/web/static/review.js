// 比稿评审：启用/撤下候选，即时刷新
document.querySelectorAll('.review-enable').forEach((btn) => {
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '启用中…';
    try {
      const resp = await fetch(`/api/review/${btn.dataset.pid}/enable`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: btn.dataset.file }),
      });
      if (!resp.ok) {
        const msg = await resp.json().catch(() => ({}));
        alert(`启用失败（${resp.status}）${msg.detail || ''}`);
        btn.disabled = false;
        return;
      }
      window.location.reload();
    } catch {
      alert('网络异常，请重试');
      btn.disabled = false;
    }
  });
});

document.querySelectorAll('.review-withdraw').forEach((btn) => {
  btn.addEventListener('click', async () => {
    if (!confirm('撤下后将回退到原 DDColor 上色图，确认？')) return;
    btn.disabled = true;
    try {
      const resp = await fetch(`/api/review/${btn.dataset.pid}/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!resp.ok) {
        const msg = await resp.json().catch(() => ({}));
        alert(`撤下失败（${resp.status}）${msg.detail || ''}`);
        btn.disabled = false;
        return;
      }
      window.location.reload();
    } catch {
      alert('网络异常，请重试');
      btn.disabled = false;
    }
  });
});
