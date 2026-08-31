function i(r){return`data:image/svg+xml;charset=UTF-8,${encodeURIComponent(r)}`}const l=i(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300" role="img" aria-label="No poster">
  <defs>
    <linearGradient id="poster-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#252b35"/>
      <stop offset="0.52" stop-color="#171c24"/>
      <stop offset="1" stop-color="#10141b"/>
    </linearGradient>
    <linearGradient id="poster-mark" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#6c7687"/>
      <stop offset="1" stop-color="#3d4656"/>
    </linearGradient>
  </defs>
  <rect width="200" height="300" rx="16" fill="url(#poster-bg)"/>
  <rect x="22" y="24" width="156" height="252" rx="12" fill="none" stroke="#394353" stroke-width="2"/>
  <g opacity=".46" fill="#566172">
    <rect x="34" y="46" width="12" height="18" rx="3"/>
    <rect x="34" y="84" width="12" height="18" rx="3"/>
    <rect x="34" y="122" width="12" height="18" rx="3"/>
    <rect x="34" y="160" width="12" height="18" rx="3"/>
    <rect x="34" y="198" width="12" height="18" rx="3"/>
    <rect x="154" y="46" width="12" height="18" rx="3"/>
    <rect x="154" y="84" width="12" height="18" rx="3"/>
    <rect x="154" y="122" width="12" height="18" rx="3"/>
    <rect x="154" y="160" width="12" height="18" rx="3"/>
    <rect x="154" y="198" width="12" height="18" rx="3"/>
  </g>
  <g transform="translate(100 146)">
    <circle r="39" fill="#222936" stroke="#465163" stroke-width="2"/>
    <path d="M-13-18v36l32-18z" fill="url(#poster-mark)"/>
  </g>
  <path d="M56 235h88" stroke="#424c5e" stroke-width="8" stroke-linecap="round"/>
  <path d="M70 255h60" stroke="#333d4d" stroke-width="7" stroke-linecap="round"/>
</svg>
`),a=i(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-label="No avatar">
  <defs>
    <linearGradient id="avatar-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2a3340"/>
      <stop offset="1" stop-color="#151b24"/>
    </linearGradient>
  </defs>
  <rect width="96" height="96" rx="48" fill="url(#avatar-bg)"/>
  <circle cx="48" cy="36" r="16" fill="#667285"/>
  <path d="M22 80c3.8-16.4 13.2-25 26-25s22.2 8.6 26 25" fill="#586476"/>
  <circle cx="48" cy="48" r="45" fill="none" stroke="#3b4656" stroke-width="3"/>
</svg>
`),o=i(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 120" role="img" aria-label="No image">
  <defs>
    <linearGradient id="image-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#252d39"/>
      <stop offset="1" stop-color="#141922"/>
    </linearGradient>
  </defs>
  <rect width="160" height="120" rx="12" fill="url(#image-bg)"/>
  <rect x="18" y="18" width="124" height="84" rx="8" fill="none" stroke="#465163" stroke-width="3"/>
  <circle cx="55" cy="48" r="11" fill="#657184"/>
  <path d="M29 91l33-31 20 18 17-15 33 28z" fill="#4d596b"/>
</svg>
`);function c(r,e=o){return String(r??"").trim()||e}function h(r,e=o){const t=r.target;!t||(t.getAttribute("src")||"")===e||t.src===e||(t.style.removeProperty("display"),t.src=e)}export{h as a,a as b,c as i,l as p};
