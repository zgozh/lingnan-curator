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
      const c = data.copy || {};
      let html = `<strong>${c.title}</strong><br>${c.body}`;
      // 实物化产物：明信片双面 / 标语海报（渲染失败时 API 不带 artifact）
      const a = data.artifact;
      if (a && a.front && a.back) {
        html += `<div class="artifact-grid">`
          + `<figure><img src="${a.front}" alt="明信片正面">`
          + `<figcaption>正面 · <a href="${a.front}" download>下载原图</a></figcaption></figure>`
          + `<figure><img src="${a.back}" alt="明信片背面">`
          + `<figcaption>背面 · <a href="${a.back}" download>下载原图</a></figcaption></figure>`
          + `</div>`;
      } else if (a && a.image) {
        html += `<figure class="artifact-poster"><img src="${a.image}" alt="标语海报">`
          + `<figcaption><a href="${a.image}" download>下载海报</a></figcaption></figure>`;
      }
      out.innerHTML = html;
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
      // 生成完成：刷新页面展示新生成的故事 + 旁白 + 音频
      // （详情页只读幂等缓存，刷新秒开；音频 src 已由 has_narration 命中）
      status.textContent = '生成完成，正在刷新…';
      setTimeout(() => window.location.reload(), 500);
    } catch {
      status.textContent = '网络异常，请重试';
    } finally {
      gen.disabled = false;
    }
  });
}
