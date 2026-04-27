(function () {
  const STORAGE_KEY = "cogitomedica.unfold.sidebarScrollTop";
  const RESTORE_DELAYS_MS = [0, 80, 200, 400, 800];

  function readStoredScrollTop() {
    try {
      const value = sessionStorage.getItem(STORAGE_KEY);
      if (!value) {
        return null;
      }
      const top = Number.parseInt(value, 10);
      return Number.isNaN(top) ? null : top;
    } catch (_error) {
      return null;
    }
  }

  function writeStoredScrollTop(scrollTop) {
    try {
      sessionStorage.setItem(STORAGE_KEY, String(scrollTop || 0));
    } catch (_error) {
      // Ignore storage failures; the sidebar should still work normally.
    }
  }

  function resolveSidebarState() {
    const sidebarNav = document.getElementById("nav-sidebar-apps");
    if (sidebarNav && window.SimpleBar && window.SimpleBar.instances) {
      const instance = window.SimpleBar.instances.get(sidebarNav);
      if (instance) {
        return {
          navElement: sidebarNav,
          scrollElement: instance.getScrollElement(),
        };
      }
    }

    const fallbackScrollElement = document.querySelector(
      "#nav-sidebar .simplebar-content-wrapper, #nav-sidebar"
    );
    if (!fallbackScrollElement) {
      return null;
    }
    return {
      navElement: document.getElementById("nav-sidebar") || fallbackScrollElement,
      scrollElement: fallbackScrollElement,
    };
  }

  function persistScroll(state) {
    if (!state || !state.scrollElement) {
      return;
    }
    writeStoredScrollTop(state.scrollElement.scrollTop);
  }

  function restoreScroll() {
    const top = readStoredScrollTop();
    if (top === null) {
      return;
    }

    RESTORE_DELAYS_MS.forEach(function (delay) {
      window.setTimeout(function () {
        const state = resolveSidebarState();
        if (!state || !state.scrollElement) {
          return;
        }
        state.scrollElement.scrollTop = top;
      }, delay);
    });
  }

  function init() {
    restoreScroll();

    const state = resolveSidebarState();
    if (!state || !state.scrollElement) {
      window.setTimeout(init, 150);
      return;
    }

    const scrollElement = state.scrollElement;
    const navElement = state.navElement || scrollElement;

    window.addEventListener("pagehide", function () {
      persistScroll(resolveSidebarState() || state);
    });
    window.addEventListener("beforeunload", function () {
      persistScroll(resolveSidebarState() || state);
    });
    window.addEventListener("load", restoreScroll);

    scrollElement.addEventListener(
      "scroll",
      function () {
        persistScroll(resolveSidebarState() || state);
      },
      { passive: true }
    );

    navElement.addEventListener(
      "click",
      function (event) {
        if (event.target && event.target.closest("a")) {
          persistScroll(resolveSidebarState() || state);
        }
      },
      true
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
