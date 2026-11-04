(() => {
  'use strict';
  const root = document.documentElement;
  const hero = document.getElementById('top');
  const videos = [...hero.querySelectorAll('.trailer-video')];
  const rect = hero.getBoundingClientRect();
  let visible = rect.bottom > 0 && rect.top < innerHeight;
  function synchronize() {
    const active = visible && !document.hidden && root.dataset.motion === 'full';
    for (const video of videos) {
      if (!active) { video.pause(); continue; }
      if (!video.getAttribute('src')) { video.src = video.dataset.src; video.load(); }
      video.muted = true;
      const promise = video.play();
      if (promise) promise.catch(() => { /* Keep the local backdrop if autoplay is unavailable. */ });
    }
  }
  for (const video of videos) {
    const panel = video.closest('.trailer-clip');
    video.addEventListener('playing', () => {
      panel.classList.add('is-playing'); panel.dataset.videoState = 'playing';
      if (!visible || document.hidden || root.dataset.motion !== 'full') video.pause();
    });
    video.addEventListener('pause', () => { panel.dataset.videoState = 'paused'; });
    video.addEventListener('error', () => { panel.classList.remove('is-playing'); panel.dataset.videoState = 'fallback'; });
  }
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => { visible = entries[0].isIntersecting; synchronize(); }, {threshold:0}).observe(hero);
  }
  document.addEventListener('visibilitychange', synchronize);
  new MutationObserver(synchronize).observe(root, {attributes:true,attributeFilter:['data-motion']});
  synchronize();
})();
