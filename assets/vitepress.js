(() => {
  "use strict";

  const root = document.documentElement;
  const body = document.body;
  const themeToggle = document.querySelector("#themeToggle");
  const nav = document.querySelector(".vp-nav");
  const menuButton = document.querySelector("#menuButton");
  const mobilePanel = document.querySelector("#mobilePanel");
  const searchDialog = document.querySelector("#searchDialog");
  const searchTrigger = document.querySelector("#searchTrigger");
  const searchInput = document.querySelector("#searchInput");
  const searchResults = document.querySelector("#searchResults");
  const lightbox = document.querySelector("#lightbox");
  const lightboxImage = document.querySelector("#lightboxImage");
  const lightboxCaption = document.querySelector("#lightboxCaption");

  const savedTheme = (() => {
    try { return localStorage.getItem("dian115-docs-theme"); } catch { return null; }
  })();
  if (savedTheme === "dark" || (!savedTheme && window.matchMedia?.("(prefers-color-scheme: dark)").matches)) root.classList.add("dark");

  themeToggle?.addEventListener("click", () => {
    const dark = root.classList.toggle("dark");
    themeToggle.textContent = dark ? "☾" : "☼";
    try { localStorage.setItem("dian115-docs-theme", dark ? "dark" : "light"); } catch { /* storage can be unavailable in file previews */ }
  });
  if (root.classList.contains("dark") && themeToggle) themeToggle.textContent = "☾";

  menuButton?.addEventListener("click", () => {
    const open = mobilePanel?.classList.toggle("open") ?? false;
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.textContent = open ? "×" : "☰";
  });
  mobilePanel?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
    mobilePanel.classList.remove("open");
    menuButton?.setAttribute("aria-expanded", "false");
    if (menuButton) menuButton.textContent = "☰";
  }));

  const updateScrollState = () => {
    const max = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
    const percent = Math.round((window.scrollY / max) * 100);
    const progress = document.querySelector("#readingProgress");
    if (progress) progress.style.width = `${percent}%`;
    nav?.classList.toggle("scrolled", window.scrollY > 5);
  };
  window.addEventListener("scroll", updateScrollState, { passive: true });
  updateScrollState();

  const searchable = [...document.querySelectorAll(".guide-card, .module-card, .shot-card, .step-item")].map((element) => ({
    element,
    title: element.querySelector("h3, b")?.textContent?.trim() || "DIAN115 文档",
    text: element.textContent.toLocaleLowerCase("zh-CN"),
    target: element.id || element.closest("section")?.id || "top"
  }));
  const escapeHtml = (value) => value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[character]);
  const renderSearch = (value) => {
    if (!searchResults) return;
    const query = value.trim().toLocaleLowerCase("zh-CN");
    if (!query) { searchResults.innerHTML = ""; return; }
    const terms = query.split(/\s+/).filter(Boolean);
    const matches = searchable.filter((item) => terms.every((term) => item.text.includes(term))).slice(0, 8);
    searchResults.innerHTML = matches.length ? matches.map((item) => `<a class="search-result" href="#${item.target}"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.element.textContent.trim().replace(/\s+/g, " ").slice(0, 82))}</small></a>`).join("") : `<div class="search-empty">没有找到“${escapeHtml(value.trim())}”</div>`;
    searchResults.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => searchDialog?.close()));
  };
  const openSearch = () => {
    if (!searchDialog?.open) searchDialog?.showModal();
    window.setTimeout(() => searchInput?.focus(), 20);
  };
  searchTrigger?.addEventListener("click", openSearch);
  searchInput?.addEventListener("input", () => renderSearch(searchInput.value));
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openSearch(); }
    if (event.key === "/" && document.activeElement !== searchInput && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) { event.preventDefault(); openSearch(); }
  });

  document.querySelectorAll(".copy-button").forEach((button) => button.addEventListener("click", async () => {
    const target = document.querySelector(`#${button.dataset.copy}`);
    const text = target?.textContent || "";
    try { await navigator.clipboard.writeText(text); } catch {
      const helper = document.createElement("textarea"); helper.value = text; helper.style.position = "fixed"; helper.style.opacity = "0"; document.body.appendChild(helper); helper.select(); document.execCommand("copy"); helper.remove();
    }
    const original = button.textContent; button.textContent = "已复制"; button.disabled = true;
    window.setTimeout(() => { button.textContent = original; button.disabled = false; }, 1300);
  }));

  document.querySelectorAll(".gallery-tab").forEach((tab) => tab.addEventListener("click", () => {
    document.querySelectorAll(".gallery-tab").forEach((item) => item.classList.toggle("active", item === tab));
    const filter = tab.dataset.filter;
    document.querySelectorAll(".shot-card").forEach((card) => { card.hidden = filter !== "all" && card.dataset.category !== filter; });
  }));

  document.querySelectorAll(".shot-card").forEach((card) => card.addEventListener("click", () => {
    if (!lightbox || !lightboxImage) return;
    lightboxImage.src = card.dataset.image || "";
    lightboxImage.alt = card.querySelector("img")?.alt || "DIAN115 界面截图";
    if (lightboxCaption) lightboxCaption.textContent = card.dataset.title || "DIAN115 界面截图";
    lightbox.showModal();
  }));
  document.querySelector(".lightbox-close")?.addEventListener("click", () => lightbox?.close());
  lightbox?.addEventListener("click", (event) => { if (event.target === lightbox) lightbox.close(); });
})();
