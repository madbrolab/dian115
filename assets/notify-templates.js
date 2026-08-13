(() => {
  "use strict";

  const search = document.getElementById("eventSearch");
  const cards = Array.from(document.querySelectorAll(".searchable-event"));
  const filters = Array.from(document.querySelectorAll("[data-filter]"));
  const count = document.getElementById("eventResultCount");
  const empty = document.getElementById("eventEmpty");
  const backTop = document.getElementById("templateBackTop");
  let activeFilter = "all";

  const normalized = (value) =>
    String(value || "")
      .trim()
      .toLocaleLowerCase("zh-CN");

  function applyFilter() {
    const terms = normalized(search?.value).split(/\s+/).filter(Boolean);
    let visible = 0;
    for (const card of cards) {
      const matchesGroup =
        activeFilter === "all" || card.dataset.group === activeFilter;
      const haystack = card.dataset.search || "";
      const matchesSearch = terms.every((term) => haystack.includes(term));
      card.hidden = !(matchesGroup && matchesSearch);
      if (!card.hidden) visible += 1;
    }
    if (count) count.textContent = `显示 ${visible} / ${cards.length}`;
    empty?.classList.toggle("visible", visible === 0);
  }

  search?.addEventListener("input", applyFilter);
  filters.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter || "all";
      filters.forEach((candidate) =>
        candidate.classList.toggle("active", candidate === button),
      );
      applyFilter();
    });
  });

  document.querySelectorAll(".copy-template").forEach((button) => {
    button.addEventListener("click", async () => {
      const text =
        button.closest(".code-block")?.querySelector("code")?.textContent || "";
      const original = button.textContent;
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "已复制";
      } catch {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        button.textContent = document.execCommand("copy")
          ? "已复制"
          : "复制失败";
        textarea.remove();
      }
      button.disabled = true;
      window.setTimeout(() => {
        button.textContent = original;
        button.disabled = false;
      }, 1400);
    });
  });

  const updateBackTop = () =>
    backTop?.classList.toggle("visible", window.scrollY > 700);
  window.addEventListener("scroll", updateBackTop, { passive: true });
  backTop?.addEventListener("click", () =>
    window.scrollTo({ top: 0, behavior: "smooth" }),
  );
  updateBackTop();

  if (location.hash) {
    const target = document.getElementById(location.hash.slice(1));
    if (target?.classList.contains("event-card")) target.open = true;
  }
})();
