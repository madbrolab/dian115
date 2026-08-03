(() => {
  "use strict";

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
  const escapeHtml = (value) => value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  })[character]);

  const body = document.body;
  const menuButton = $("#menuButton");
  const mobileSearchButton = $("#mobileSearchButton");
  const navMask = $("#navMask");
  const searchInput = $("#wikiSearch");
  const searchResults = $("#searchResults");
  const tocList = $("#tocList");
  const readPercent = $("#readPercent");
  const progressBar = $("#progressBar");
  const backTop = $("#backTop");
  const lightbox = $("#lightbox");
  const lightboxImage = $("#lightboxImage");

  const setNavigationOpen = (open) => {
    body.classList.toggle("nav-open", open);
    menuButton?.setAttribute("aria-expanded", String(open));
    menuButton?.setAttribute("aria-label", open ? "关闭目录" : "打开目录");
  };

  const closeSearch = () => {
    searchResults?.classList.remove("open");
    searchInput?.setAttribute("aria-expanded", "false");
  };

  const focusSearch = () => {
    if (window.innerWidth <= 900) {
      setNavigationOpen(true);
    }
    window.setTimeout(() => {
      searchInput?.focus({ preventScroll: true });
      searchInput?.select();
      if (searchInput?.value.trim()) {
        renderSearch(searchInput.value);
      }
    }, window.innerWidth <= 900 ? 230 : 0);
  };

  menuButton?.addEventListener("click", () => {
    setNavigationOpen(!body.classList.contains("nav-open"));
  });
  navMask?.addEventListener("click", () => setNavigationOpen(false));
  mobileSearchButton?.addEventListener("click", focusSearch);

  $$(".left-rail a[href^='#']").forEach((link) => {
    link.addEventListener("click", () => {
      if (window.innerWidth <= 900) {
        setNavigationOpen(false);
      }
      closeSearch();
    });
  });

  // Build a concise in-page outline from the document's real headings.
  const tocHeadings = $$(".page-main h2, .page-main h3");
  const usedIds = new Set($$("[id]").map((element) => element.id));
  tocHeadings.forEach((heading, index) => {
    if (!heading.id) {
      let id = `wiki-heading-${index + 1}`;
      while (usedIds.has(id)) id += "-x";
      heading.id = id;
      usedIds.add(id);
    }

    const link = document.createElement("a");
    link.href = `#${heading.id}`;
    link.dataset.level = heading.tagName.slice(1);
    link.textContent = heading.textContent.trim();
    tocList?.appendChild(link);
  });

  const activateLinks = (links, id) => {
    links.forEach((link) => {
      const active = link.getAttribute("href") === `#${id}`;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
  };

  const navLinks = $$(".nav-link[href^='#']");
  const tocLinks = $$(".toc-list a[href^='#']");

  const createSectionObserver = (links, targets) => {
    if (!("IntersectionObserver" in window) || targets.length === 0) return;
    const visible = new Map();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) visible.set(entry.target.id, entry.boundingClientRect.top);
        else visible.delete(entry.target.id);
      });

      if (visible.size > 0) {
        const current = [...visible.entries()].sort((a, b) => Math.abs(a[1] - 110) - Math.abs(b[1] - 110))[0][0];
        activateLinks(links, current);
      }
    }, { rootMargin: "-8% 0px -78% 0px", threshold: [0, 1] });
    targets.forEach((target) => observer.observe(target));
  };

  const navTargets = navLinks
    .map((link) => document.getElementById(decodeURIComponent(link.hash.slice(1))))
    .filter(Boolean);
  createSectionObserver(navLinks, navTargets);
  createSectionObserver(tocLinks, tocHeadings);

  const searchableItems = $$(".searchable[data-search-title]").map((element) => ({
    element,
    id: element.id || element.closest("[id]")?.id || "top",
    title: element.dataset.searchTitle.trim(),
    haystack: `${element.dataset.searchTitle} ${element.textContent}`.toLocaleLowerCase("zh-CN")
  }));

  function renderSearch(rawQuery) {
    if (!searchResults || !searchInput) return;
    const query = rawQuery.trim().toLocaleLowerCase("zh-CN");
    if (!query) {
      closeSearch();
      searchResults.innerHTML = "";
      return;
    }

    const terms = query.split(/\s+/).filter(Boolean);
    const matches = searchableItems
      .filter((item) => terms.every((term) => item.haystack.includes(term)))
      .slice(0, 10);

    if (matches.length === 0) {
      searchResults.innerHTML = `<div class="search-empty">没有找到“${escapeHtml(rawQuery.trim())}”</div>`;
    } else {
      searchResults.innerHTML = matches.map((item) => {
        const heading = $("h2, h3", item.element)?.textContent.trim() || item.title.split(" ").slice(0, 4).join(" ");
        return `<a class="search-result" href="#${encodeURIComponent(item.id)}" role="option"><b>${escapeHtml(heading)}</b><small>${escapeHtml(item.title)}</small></a>`;
      }).join("");
    }

    searchResults.classList.add("open");
    searchInput.setAttribute("aria-expanded", "true");
  }

  searchInput?.setAttribute("aria-controls", "searchResults");
  searchInput?.setAttribute("aria-expanded", "false");
  searchInput?.addEventListener("input", (event) => renderSearch(event.target.value));
  searchInput?.addEventListener("focus", () => {
    if (searchInput.value.trim()) renderSearch(searchInput.value);
  });
  searchResults?.addEventListener("click", (event) => {
    if (event.target.closest(".search-result")) {
      closeSearch();
      searchInput.value = "";
      if (window.innerWidth <= 900) setNavigationOpen(false);
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(".search-box") && !event.target.closest("#searchResults") && !event.target.closest("#mobileSearchButton")) {
      closeSearch();
    }
  });

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const editing = target.matches?.("input, textarea, select") || target.isContentEditable;
    if (event.key === "/" && !editing && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      focusSearch();
    }
    if (event.key === "Escape") {
      closeSearch();
      setNavigationOpen(false);
      closeLightbox();
      if (document.activeElement === searchInput) searchInput.blur();
    }
  });

  const fallbackCopy = (text) => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const successful = document.execCommand("copy");
    textarea.remove();
    return successful;
  };

  $$(".copy-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      const code = button.closest(".code-block")?.querySelector("code")?.textContent || "";
      let copied = false;
      try {
        if (navigator.clipboard?.writeText && window.isSecureContext) {
          await navigator.clipboard.writeText(code);
          copied = true;
        } else {
          copied = fallbackCopy(code);
        }
      } catch {
        copied = fallbackCopy(code);
      }

      const original = button.textContent;
      button.textContent = copied ? "已复制" : "复制失败";
      button.disabled = true;
      window.setTimeout(() => {
        button.textContent = original;
        button.disabled = false;
      }, 1500);
    });
  });

  const openLightbox = (source, alt) => {
    if (!lightbox || !lightboxImage) return;
    lightboxImage.src = source;
    lightboxImage.alt = alt ? `放大预览：${alt}` : "放大的界面截图";
    lightbox.classList.add("open");
    body.dataset.previousOverflow = body.style.overflow;
    body.style.overflow = "hidden";
    $(".lightbox-close", lightbox)?.focus();
  };

  function closeLightbox() {
    if (!lightbox?.classList.contains("open")) return;
    lightbox.classList.remove("open");
    lightboxImage.src = "";
    body.style.overflow = body.dataset.previousOverflow || "";
    delete body.dataset.previousOverflow;
  }

  $$('[data-lightbox]').forEach((button) => {
    button.addEventListener("click", () => {
      openLightbox(button.dataset.lightbox, $("img", button)?.alt || "");
    });
  });
  $(".lightbox-close", lightbox)?.addEventListener("click", closeLightbox);
  lightbox?.addEventListener("click", (event) => {
    if (event.target === lightbox) closeLightbox();
  });

  const updateReadingState = () => {
    const root = document.documentElement;
    const maximum = Math.max(root.scrollHeight - window.innerHeight, 1);
    const ratio = Math.min(Math.max(window.scrollY / maximum, 0), 1);
    const percent = Math.round(ratio * 100);
    if (readPercent) readPercent.textContent = `${percent}%`;
    if (progressBar) progressBar.style.width = `${percent}%`;
    backTop?.classList.toggle("visible", window.scrollY > 640);
  };

  let ticking = false;
  window.addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(() => {
      updateReadingState();
      ticking = false;
    });
  }, { passive: true });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) setNavigationOpen(false);
    updateReadingState();
  });
  backTop?.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  updateReadingState();
})();
