(() => {
  "use strict";

  const root = document.documentElement;
  const themeToggle = document.querySelector("#themeToggle");
  const nav = document.querySelector(".vp-nav");
  const menuButton = document.querySelector("#menuButton");
  const mobilePanel = document.querySelector("#mobilePanel");
  const sidebar = document.querySelector("#docsSidebar");
  const sidebarToggle = document.querySelector("#sidebarToggle");
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
  if (root.classList.contains("dark") && themeToggle) themeToggle.textContent = "☾";
  themeToggle?.addEventListener("click", () => {
    const dark = root.classList.toggle("dark");
    themeToggle.textContent = dark ? "☾" : "☼";
    try { localStorage.setItem("dian115-docs-theme", dark ? "dark" : "light"); } catch { /* storage can be unavailable */ }
  });

  const closeMobile = () => {
    mobilePanel?.classList.remove("open");
    sidebar?.classList.remove("open");
    menuButton?.setAttribute("aria-expanded", "false");
    sidebarToggle?.setAttribute("aria-expanded", "false");
    if (menuButton) menuButton.textContent = "☰";
  };
  menuButton?.addEventListener("click", () => {
    const open = mobilePanel?.classList.toggle("open") ?? false;
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.textContent = open ? "×" : "☰";
  });
  sidebarToggle?.addEventListener("click", () => {
    const open = sidebar?.classList.toggle("open") ?? false;
    sidebarToggle.setAttribute("aria-expanded", String(open));
    sidebarToggle.textContent = open ? "× 关闭目录" : "☰ 文档目录";
  });
  document.querySelectorAll(".mobile-panel a, .docs-sidebar a").forEach((link) => link.addEventListener("click", closeMobile));

  const updateScrollState = () => {
    const max = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
    const progress = document.querySelector("#readingProgress");
    if (progress) progress.style.width = `${Math.round((window.scrollY / max) * 100)}%`;
    nav?.classList.toggle("scrolled", window.scrollY > 5);
  };
  window.addEventListener("scroll", updateScrollState, { passive: true });
  updateScrollState();

  const docs = [
    ["Wiki 首页", "从部署、配置到日常使用的入口", "index.html"],
    ["快速开始", "推荐阅读顺序与系统架构", "guide.html"],
    ["部署指南", "Docker、Compose、端口与首次验收", "deploy.html"],
    ["路径与配置", "115、CloudDrive2、Emby 与目录规范", "configure.html"],
    ["功能总览", "探索、订阅、整理、播放代理与插件", "features.html"],
    ["资源与插件", "文件管理、账号池、PT 站点、12 个插件和卫星发布树", "integrations.html"],
    ["运维与扩展", "容器更新、缓存、门户、音乐、AI 和常用能力", "operations.html"],
    ["界面截图", "DIAN115 各模块真实界面预览", "screenshots.html"],
    ["参考手册", "端口、路径、环境变量与维护命令", "reference.html"],
    ["问题排查", "常见故障、日志与升级建议", "support.html"],
    ["通知模板", "Telegram 通知事件与变量参考", "notification-templates.html"],
  ];
  const localEntries = [...document.querySelectorAll(".guide-card, .module-card, .shot-card, .step-item")].map((element) => ({
    title: element.querySelector("h3, b")?.textContent?.trim() || "DIAN115 文档",
    text: element.textContent.toLocaleLowerCase("zh-CN"),
    href: `#${element.id || element.closest("section")?.id || "top"}`,
    excerpt: element.textContent.trim().replace(/\s+/g, " ").slice(0, 88),
  }));
  const entries = [...docs.map(([title, excerpt, href]) => ({ title, text: `${title} ${excerpt}`.toLocaleLowerCase("zh-CN"), href, excerpt })), ...localEntries];
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[character]));
  const renderSearch = (value) => {
    if (!searchResults) return;
    const query = value.trim().toLocaleLowerCase("zh-CN");
    if (!query) { searchResults.innerHTML = "<div class=\"search-empty\">输入关键词，搜索所有文档页面</div>"; return; }
    const terms = query.split(/\s+/).filter(Boolean);
    const matches = entries.filter((item) => terms.every((term) => item.text.includes(term))).slice(0, 10);
    searchResults.innerHTML = matches.length ? matches.map((item) => `<a class="search-result" href="${escapeHtml(item.href)}"><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.excerpt)}</small></a>`).join("") : `<div class="search-empty">没有找到“${escapeHtml(value.trim())}”</div>`;
    searchResults.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => searchDialog?.close()));
  };
  const openSearch = () => {
    if (!searchDialog?.open) searchDialog?.showModal();
    renderSearch(searchInput?.value || "");
    window.setTimeout(() => searchInput?.focus(), 20);
  };
  searchTrigger?.addEventListener("click", openSearch);
  searchInput?.addEventListener("input", () => renderSearch(searchInput.value));
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openSearch(); }
    if (event.key === "/" && document.activeElement !== searchInput && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) { event.preventDefault(); openSearch(); }
  });

  document.querySelectorAll(".docs-copy, .copy-button").forEach((button) => button.addEventListener("click", async () => {
    const target = document.querySelector(`#${button.dataset.copy}`) || button.closest(".docs-code, .code-card")?.querySelector("pre");
    const text = target?.textContent || "";
    try { await navigator.clipboard.writeText(text); } catch {
      const helper = document.createElement("textarea"); helper.value = text; helper.style.position = "fixed"; helper.style.opacity = "0"; document.body.appendChild(helper); helper.select(); document.execCommand("copy"); helper.remove();
    }
    const original = button.textContent; button.textContent = "已复制"; button.disabled = true;
    window.setTimeout(() => { button.textContent = original; button.disabled = false; }, 1300);
  }));

  const headings = [...document.querySelectorAll(".docs-content h2, .docs-content section > h3")];
  const toc = document.querySelector(".toc-list");
  if (toc && headings.length) {
    headings.forEach((heading, index) => {
      if (!heading.id) heading.id = `section-${index + 1}`;
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = `#${heading.id}`; link.textContent = heading.textContent;
      if (heading.tagName === "H3") link.className = "toc-h3";
      item.append(link); toc.append(item);
    });
    const observer = new IntersectionObserver((observations) => {
      const current = observations.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
      if (!current) return;
      toc.querySelectorAll("a").forEach((link) => link.classList.toggle("active", link.getAttribute("href") === `#${current.target.id}`));
    }, { rootMargin: "-90px 0px -65% 0px", threshold: 0 });
    headings.forEach((heading) => observer.observe(heading));
  }

  document.querySelectorAll(".gallery-tab").forEach((tab) => tab.addEventListener("click", () => {
    document.querySelectorAll(".gallery-tab").forEach((item) => item.classList.toggle("active", item === tab));
    const filter = tab.dataset.filter;
    document.querySelectorAll(".shot-card, .docs-shot").forEach((card) => { card.hidden = filter !== "all" && card.dataset.category !== filter; });
  }));
  document.querySelectorAll(".shot-card, .docs-shot").forEach((card) => card.addEventListener("click", () => {
    if (!lightbox || !lightboxImage) return;
    lightboxImage.src = card.dataset.image || card.querySelector("img")?.src || "";
    lightboxImage.alt = card.querySelector("img")?.alt || "DIAN115 界面截图";
    if (lightboxCaption) lightboxCaption.textContent = card.dataset.title || card.querySelector("b")?.textContent || "DIAN115 界面截图";
    lightbox.showModal();
  }));
  document.querySelector(".lightbox-close")?.addEventListener("click", () => lightbox?.close());
  lightbox?.addEventListener("click", (event) => { if (event.target === lightbox) lightbox.close(); });
})();
