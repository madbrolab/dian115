(() => {
  'use strict';
  const root = document.documentElement;
  const $ = s => document.querySelector(s);
  const scene = $('#heroArt');
  const posters = [...document.querySelectorAll('.cinema-poster')];
  const caption = $('.scene-caption');
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  const films = [
    {title:'银翼杀手 2049',meta:'BLADE RUNNER 2049 / 2017 · 科幻',color:'#d48b67'},
    {title:'降临',meta:'ARRIVAL / 2016 · 科幻 · 剧情',color:'#90acb4'},
    {title:'星际穿越',meta:'INTERSTELLAR / 2014 · 科幻 · 冒险',color:'#83aadd'},
    {title:'沙丘 2',meta:'DUNE: PART TWO / 2024 · 科幻',color:'#d2a16f'},
    {title:'盗梦空间',meta:'INCEPTION / 2010 · 科幻 · 悬疑',color:'#749cbf'}
  ];
  let active = 2, timer, inHero = true, hovered = false, focused = false;
  const full = () => root.dataset.motion === 'full';
  const canRotate = () => full() && inHero && !hovered && !focused && !document.hidden && !document.querySelector('dialog[open]');
  const restartTimeline = () => {
    const bar = $('.scene-timeline span');
    bar.style.animation = 'none';
    void bar.offsetWidth;
    bar.style.animation = '';
    bar.style.animationPlayState = canRotate() ? 'running' : 'paused';
  };
  function schedule() {
    clearTimeout(timer);
    if (canRotate()) timer = setTimeout(() => { select(active + 1); }, 7000);
    restartTimeline();
  }
  function select(index, animate = true) {
    active = (index + films.length) % films.length;
    posters.forEach((poster, i) => {
      let slot = (i - active + films.length) % films.length;
      if (slot > 2) slot -= films.length;
      poster.style.setProperty('--slot', slot);
      poster.style.setProperty('--depth', Math.abs(slot));
      poster.classList.toggle('active', i === active);
      poster.setAttribute('aria-pressed', String(i === active));
    });
    caption.classList.remove('changing');
    $('#posterTitle').textContent = films[active].title;
    $('#posterMeta').textContent = films[active].meta;
    $('#posterCount').textContent = '0' + (active + 1) + ' / 05';
    scene.style.setProperty('--scene-accent', films[active].color);
    if (animate && full()) { void caption.offsetWidth; caption.classList.add('changing'); }
    schedule();
  }
  posters.forEach((poster, i) => {
    poster.addEventListener('click', () => select(i));
    // A shared overlay follows whichever poster is in the spotlight.
    if (!poster.querySelector('.poster-play')) poster.append($('.poster-play').cloneNode(true));
  });
  $('#posterPrev').addEventListener('click', () => select(active - 1));
  $('#posterNext').addEventListener('click', () => select(active + 1));
  scene.addEventListener('keydown', e => {
    if (!e.target.closest('.cinema-poster') || !['ArrowLeft','ArrowRight'].includes(e.key)) return;
    e.preventDefault(); select(active + (e.key === 'ArrowRight' ? 1 : -1)); posters[active].focus();
  });
  scene.addEventListener('pointerenter', e => { if(e.pointerType !== 'touch') { hovered = true; schedule(); } });
  scene.addEventListener('pointerleave', () => {
    hovered = false;
    scene.style.setProperty('--rx', '0deg'); scene.style.setProperty('--ry', '0deg');
    scene.style.setProperty('--light-x', '50%'); scene.style.setProperty('--light-y', '50%');
    schedule();
  });
  scene.addEventListener('focusin', () => { focused = true; schedule(); });
  scene.addEventListener('focusout', e => { if(!scene.contains(e.relatedTarget)) { focused = false; schedule(); } });
  scene.addEventListener('pointermove', e => {
    if (!full() || !fine.matches) return;
    const r = scene.getBoundingClientRect(), x = (e.clientX-r.left)/r.width, y = (e.clientY-r.top)/r.height;
    scene.style.setProperty('--rx', ((y-.5)*-9).toFixed(2)+'deg');
    scene.style.setProperty('--ry', ((x-.5)*13).toFixed(2)+'deg');
    scene.style.setProperty('--light-x', (x*100).toFixed(1)+'%');
    scene.style.setProperty('--light-y', (y*100).toFixed(1)+'%');
  });
  const ribbon = $('#ribbonTrack');
  const duplicate = ribbon.firstElementChild.cloneNode(true);
  duplicate.setAttribute('aria-hidden', 'true'); ribbon.append(duplicate);

  const personal = $('.personal-art');
  let pending = false;
  function scrollScene() {
    pending = false;
    if(!full()) return;
    const r = personal.getBoundingClientRect();
    const p = Math.max(0, Math.min(1, (innerHeight-r.top)/(innerHeight+r.height)));
    scene.style.setProperty('--scroll-shift', (-Math.min(scrollY/650,1)*38).toFixed(1)+'px');
    personal.style.setProperty('--personal-shift', ((p-.5)*-38).toFixed(1)+'px');
    personal.style.setProperty('--personal-rotate', (-12+p*19).toFixed(1)+'deg');
  }
  addEventListener('scroll', () => { if (!pending && full()) { pending = true; requestAnimationFrame(scrollScene); } }, {passive:true});
  addEventListener('resize', scrollScene, {passive:true});
  const observer = new IntersectionObserver(entries => {
    for(const e of entries) {
      if(e.target.id === 'top') {
        inHero = e.isIntersecting; root.dataset.offscreen = String(!inHero); schedule();
      } else {
        e.target.classList.toggle('motion-paused', !e.isIntersecting);
        if(e.isIntersecting) e.target.classList.add('scene-visible');
      }
    }
  }, {threshold:0,rootMargin:'30px'});
  observer.observe($('#top'));
  document.querySelectorAll('.chapter,.media-ribbon,.closing').forEach(el => observer.observe(el));
  new MutationObserver(() => {
    if(!full()) {
      scene.style.setProperty('--rx','0deg'); scene.style.setProperty('--ry','0deg');
      document.querySelectorAll('.magnetic').forEach(el => el.style.translate = '0 0');
    }
    schedule(); scrollScene();
  }).observe(root, {attributes:true,attributeFilter:['data-motion']});
  new MutationObserver(schedule).observe(document.body, {subtree:true,attributes:true,attributeFilter:['open']});
  document.addEventListener('visibilitychange', () => { root.classList.toggle('motion-paused',document.hidden); schedule(); });
  select(active,false); scrollScene();
})();
