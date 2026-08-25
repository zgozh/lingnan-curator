// 详情页：上色对比滑块 + 文创生成
const slider = document.querySelector('.slider input');
if (slider) {
  const top = document.querySelector('.layer.top');
  const setClip = () => {
    top.style.clipPath = `inset(0 0 0 ${slider.value}%)`;
  };
  slider.addEventListener('input', setClip);
  setClip();
}

document.querySelectorAll('.chip').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const out = document.getElementById('copy-out');
    out.textContent = '生成中…';
    try {
      const resp = await fetch(`/api/create/${btn.dataset.pid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: btn.dataset.type }),
      });
      if (!resp.ok) {
        out.textContent = `生成失败（${resp.status}）`;
        return;
      }
      const data = await resp.json();
      out.innerHTML = `<strong>${data.copy.title}</strong><br>${data.copy.body}`;
    } catch {
      out.textContent = '网络异常，请重试。';
    }
  });
});
