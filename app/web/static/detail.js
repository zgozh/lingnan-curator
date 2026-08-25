// 详情页：上色对比滑块 + 文创生成 + 讲解音频音色切换
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

// 粤语讲解：选音色 → 重合成 → 刷新音频
const gen = document.getElementById('tts-gen');
if (gen) {
  gen.addEventListener('click', async () => {
    const status = document.getElementById('tts-status');
    const voice = document.getElementById('tts-voice').value;
    gen.disabled = true;
    status.textContent = '合成中…（约 10 秒）';
    try {
      const resp = await fetch(`/api/narrate/${gen.dataset.pid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice }),
      });
      if (!resp.ok) {
        const msg = await resp.json().catch(() => ({}));
        status.textContent = `失败（${resp.status}）${msg.detail || ''}`;
        return;
      }
      const data = await resp.json();
      const audio = document.getElementById('narration-audio');
      if (audio && !data.has_video) {
        audio.src = `/media/${gen.dataset.pid}/narration.wav?v=${Date.now()}`;
        audio.hidden = false;
        status.textContent = '已完成，点击播放试听';
      } else {
        status.textContent = '音频已更新；口播视频需重跑预生成后刷新页面';
      }
    } catch {
      status.textContent = '网络异常，请重试';
    } finally {
      gen.disabled = false;
    }
  });
}
