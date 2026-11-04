(() => {
  'use strict';
  const root = document.documentElement;
  const hero = document.querySelector('.hero');
  const heroCopy = document.querySelector('.hero-copy');
  const inner = document.querySelector('.orbit-inner');
  const outer = document.querySelector('.orbit-outer');
  const panels = [...document.querySelectorAll('.showcase-panel')];
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  const full = () => root.dataset.motion === 'full';
  const visiblePanels = new Set();
  let heroVisible = true, frame = 0;

  // A single linear scroll clock: no easing, scroll interception or wheel rewriting.
  function updateScene() {
    frame = 0;
    if (!full() || document.hidden) return;
    if (heroVisible) {
      const rect = hero.getBoundingClientRect();
      const progress = Math.max(0, Math.min(1, -rect.top / Math.max(1, rect.height - innerHeight)));
      inner.style.transform = `scale(${1 + progress * .44}) rotate(${-progress * 42}deg)`;
      outer.style.transform = `scale(${1 + progress * .65}) rotate(${progress * 55}deg)`;
      heroCopy.style.opacity = String(1 - progress * .88);
      heroCopy.style.transform = `translateY(${-progress * 35}px)`;
    }
    for (const panel of visiblePanels) {
      const card = panel.querySelector('.showcase-card');
      if (!fine.matches || innerWidth <= 800) { card.style.removeProperty('transform'); continue; }
      const rect = panel.getBoundingClientRect();
      const progress = Math.max(0, Math.min(1, (innerHeight - rect.top) / (innerHeight * .86)));
      card.style.transform = `scale(${.66 + progress * .34})`;
    }
  }
  function requestScene() { if (!frame && full() && !document.hidden) frame = requestAnimationFrame(updateScene); }
  addEventListener('scroll', requestScene, { passive: true });
  addEventListener('resize', requestScene, { passive: true });

  // Animate only the three presentation moments. Never hide content after scrolling past it.
  if ('IntersectionObserver' in window) {
    const reveal = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.remove('pending-reveal');
        reveal.unobserve(entry.target);
      });
    }, { threshold: 0, rootMargin: '0px 0px -25px 0px' });
    document.querySelectorAll('.reveal').forEach(el => {
      if (full() && el.getBoundingClientRect().top > innerHeight) el.classList.add('pending-reveal');
      reveal.observe(el);
    });
    const visibility = new IntersectionObserver(entries => {
      for (const entry of entries) {
        entry.target.classList.toggle('motion-paused', !entry.isIntersecting);
        if (entry.target === hero) heroVisible = entry.isIntersecting;
        if (entry.target.classList.contains('showcase-panel')) {
          if (entry.isIntersecting) visiblePanels.add(entry.target);
          else visiblePanels.delete(entry.target);
        }
      }
      requestScene();
    }, { threshold: 0 });
    document.querySelectorAll('.hero,.chapter,.closing,.type-marquee,.footer-marquee,.showcase-panel').forEach(el => visibility.observe(el));
  } else panels.forEach(el => visiblePanels.add(el));

  function resetSpatialMotion() {
    [inner, outer, heroCopy, ...panels.map(p => p.querySelector('.showcase-card'))].forEach(el => {
      el.style.removeProperty('transform');
      el.style.removeProperty('opacity');
    });
    document.querySelectorAll('.pending-reveal').forEach(el => el.classList.remove('pending-reveal'));
  }
  new MutationObserver(() => { if (!full()) resetSpatialMotion(); else requestScene(); }).observe(root, { attributes: true, attributeFilter: ['data-motion'] });
  document.addEventListener('visibilitychange', () => {
    root.classList.toggle('motion-paused', document.hidden);
    if (document.hidden) { cancelAnimationFrame(frame); frame = 0; }
    else requestScene();
  });
  try {
    if (full() && !sessionStorage.getItem('dian-wiki-intro-cyrclo')) {
      hero.classList.add('intro-on');
      sessionStorage.setItem('dian-wiki-intro-cyrclo', 'seen');
      heroCopy.addEventListener('animationend', () => hero.classList.remove('intro-on'), { once: true });
    }
  } catch { /* Storage restrictions never delay the page. */ }

  // Disclosure is interruptible: each click starts at the currently rendered height.
  const faqStates = new WeakMap();
  document.querySelectorAll('.faq-trigger').forEach(button => {
    const region = document.getElementById(button.getAttribute('aria-controls'));
    const state = { animation: null };
    faqStates.set(region, state);
    region.inert = region.hidden;
    button.addEventListener('click', () => {
      const opening = button.getAttribute('aria-expanded') !== 'true';
      const from = region.hidden ? 0 : region.getBoundingClientRect().height;
      const fromOpacity = region.hidden ? 0 : Number(getComputedStyle(region).opacity);
      state.animation?.cancel();
      button.setAttribute('aria-expanded', String(opening));
      region.hidden = false;
      region.inert = !opening;
      region.style.height = 'auto';
      const to = opening ? region.scrollHeight : 0;
      if (!full()) { region.hidden = !opening; region.style.removeProperty('height'); return; }
      region.style.height = to + 'px';
      const animation = region.animate([
        { height: from + 'px', opacity: fromOpacity },
        { height: to + 'px', opacity: opening ? 1 : 0 },
      ], { duration: opening ? 320 : 220, easing: 'cubic-bezier(.22,1,.36,1)' });
      state.animation = animation;
      animation.onfinish = () => {
        if (state.animation !== animation) return;
        region.hidden = !opening;
        region.style.removeProperty('height');
        state.animation = null;
      };
    });
  });
  new MutationObserver(() => {
    if (full()) return;
    document.querySelectorAll('.faq-answer').forEach(region => {
      const state = faqStates.get(region);
      state.animation?.cancel(); state.animation = null;
      const opening = document.getElementById(region.getAttribute('aria-labelledby')).getAttribute('aria-expanded') === 'true';
      region.hidden = !opening; region.inert = !opening; region.style.removeProperty('height');
    });
  }).observe(root, { attributes: true, attributeFilter: ['data-motion'] });
  // Native horizontal scrolling also supports touch, trackpad, arrows and reduced motion.
  const tour = document.getElementById('tourWindow');
  const tourCards = [...tour.querySelectorAll('.tour-card')];
  const tourPrev = document.getElementById('tourPrev'), tourNext = document.getElementById('tourNext');
  function updateTour() {
    const step = tourCards[0].getBoundingClientRect().width + parseFloat(getComputedStyle(tour).gap);
    const start = Math.round(tour.scrollLeft / step);
    const count = Math.max(1, Math.round(tour.clientWidth / step));
    tourPrev.disabled = tour.scrollLeft <= 2;
    tourNext.disabled = tour.scrollLeft >= tour.scrollWidth - tour.clientWidth - 2;
    document.getElementById('tourStatus').textContent = `${String(start + 1).padStart(2, '0')}–${String(Math.min(start + count, tourCards.length)).padStart(2, '0')} / 04`;
  }
  function moveTour(direction) {
    const step = tourCards[0].getBoundingClientRect().width + parseFloat(getComputedStyle(tour).gap);
    tour.scrollBy({left: direction * step, behavior: full() ? 'smooth' : 'instant'});
  }
  tourPrev.addEventListener('click', () => moveTour(-1));
  tourNext.addEventListener('click', () => moveTour(1));
  tour.addEventListener('scroll', updateTour, {passive:true});
  tour.addEventListener('keydown', e => {if(e.target!==tour || !['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();moveTour(e.key==='ArrowRight'?1:-1);});
  addEventListener('resize', updateTour, {passive:true}); updateTour();
  requestScene();
})();
