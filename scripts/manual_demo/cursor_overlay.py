"""Visible mouse cursor overlay for Playwright video recordings.

Playwright does not capture the OS cursor in ``record_video_*``. This module
injects a fixed DOM cursor that follows ``mousemove`` / click events and helpers
for slower, human-like moves (``mouse.move`` with steps + short pauses).

Re-injects after full navigations (``add_init_script`` + ``framenavigated``) and
after HTMX/body swaps (MutationObserver).
"""

from __future__ import annotations

# Injected on every new document. Idempotent; self-heals if the node is removed.
CURSOR_INIT_JS = r"""
(() => {
  const STYLE_ID = 'cogito-pw-cursor-style';
  const CURSOR_ID = 'cogito-pw-cursor';

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      #cogito-pw-cursor {
        position: fixed;
        left: 0;
        top: 0;
        width: 22px;
        height: 22px;
        margin: 0;
        padding: 0;
        border: 2.5px solid #111;
        border-radius: 50%;
        background: rgba(255, 220, 40, 0.92);
        box-shadow:
          0 0 0 1px rgba(255,255,255,0.9),
          0 2px 8px rgba(0,0,0,0.35);
        transform: translate(-50%, -50%);
        pointer-events: none;
        z-index: 2147483647;
        opacity: 0.95;
        transition: transform 0.06s ease-out, background 0.08s ease-out, box-shadow 0.08s ease-out;
        will-change: left, top, transform;
      }
      #cogito-pw-cursor.cogito-pw-cursor--click {
        transform: translate(-50%, -50%) scale(0.72);
        background: rgba(255, 120, 40, 0.95);
        box-shadow:
          0 0 0 3px rgba(255, 140, 40, 0.45),
          0 2px 10px rgba(0,0,0,0.4);
      }
      #cogito-pw-cursor::after {
        content: '';
        position: absolute;
        left: 50%;
        top: 50%;
        width: 4px;
        height: 4px;
        margin: -2px 0 0 -2px;
        border-radius: 50%;
        background: #111;
      }
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function ensureCursor() {
    ensureStyle();
    let el = document.getElementById(CURSOR_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = CURSOR_ID;
      el.setAttribute('aria-hidden', 'true');
      const root = document.body || document.documentElement;
      root.appendChild(el);
    } else if (document.body && el.parentElement !== document.body) {
      document.body.appendChild(el);
    }
    return el;
  }

  window.__cogitoCursorLastX = window.__cogitoCursorLastX
    || Math.round(window.innerWidth / 2);
  window.__cogitoCursorLastY = window.__cogitoCursorLastY
    || Math.round(window.innerHeight / 3);

  function place(x, y) {
    window.__cogitoCursorLastX = x;
    window.__cogitoCursorLastY = y;
    const el = ensureCursor();
    el.style.left = x + 'px';
    el.style.top = y + 'px';
  }

  // Always restore DOM nodes (HTMX may wipe body children).
  place(window.__cogitoCursorLastX, window.__cogitoCursorLastY);

  if (window.__cogitoCursorListeners) return;
  window.__cogitoCursorListeners = true;

  function onMove(e) {
    place(e.clientX, e.clientY);
  }
  function onDown() {
    ensureCursor().classList.add('cogito-pw-cursor--click');
  }
  function onUp() {
    ensureCursor().classList.remove('cogito-pw-cursor--click');
  }

  document.addEventListener('mousemove', onMove, true);
  document.addEventListener('mousedown', onDown, true);
  document.addEventListener('mouseup', onUp, true);
  window.addEventListener('blur', onUp);

  const mo = new MutationObserver(() => {
    if (!document.getElementById(CURSOR_ID)) {
      place(window.__cogitoCursorLastX, window.__cogitoCursorLastY);
    }
  });
  const startMo = () => {
    const root = document.documentElement;
    if (root) mo.observe(root, { childList: true, subtree: true });
  };
  if (document.body) startMo();
  else document.addEventListener('DOMContentLoaded', startMo, { once: true });
})();
"""


DEFAULT_MOVE_STEPS = 28
DEFAULT_PAUSE_BEFORE_MS = 350
DEFAULT_PAUSE_AFTER_MS = 550


def install_cursor(page) -> None:
    """Install cursor overlay for this page and all future navigations."""
    # Signal shared auth helpers to use human_move/click (videos only).
    setattr(page.context, "_cogito_visible_cursor", True)
    page.add_init_script(CURSOR_INIT_JS)

    def _reinject(_frame=None) -> None:
        try:
            # Only main frame; avoid iframes.
            if _frame is not None and _frame != page.main_frame:
                return
            page.evaluate(CURSOR_INIT_JS)
        except Exception:
            pass

    page.on("framenavigated", _reinject)
    _reinject()
    # Start near upper-middle so the cursor is visible before first move.
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        page.mouse.move(vp["width"] // 2, vp["height"] // 3, steps=1)
    except Exception:
        pass


def cursor_enabled(page) -> bool:
    return bool(getattr(page.context, "_cogito_visible_cursor", False))


def _pause(page, ms: int) -> None:
    if ms > 0:
        page.wait_for_timeout(ms)


def _center_of(locator) -> tuple[float, float] | None:
    try:
        if not locator.count():
            return None
        box = locator.bounding_box()
        if not box:
            return None
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    except Exception:
        return None


def human_move_to(
    page,
    locator,
    *,
    steps: int = DEFAULT_MOVE_STEPS,
    scroll: bool = True,
) -> bool:
    """Scroll into view and move the mouse to the locator center with steps."""
    try:
        if not locator.count():
            return False
        target = locator.first
        if scroll:
            try:
                target.scroll_into_view_if_needed(timeout=5000)
            except Exception:
                pass
            _pause(page, 200)
        point = _center_of(target)
        if not point:
            return False
        page.mouse.move(point[0], point[1], steps=max(1, steps))
        return True
    except Exception:
        return False


def human_click(
    page,
    locator,
    *,
    steps: int = DEFAULT_MOVE_STEPS,
    pause_before_ms: int = DEFAULT_PAUSE_BEFORE_MS,
    pause_after_ms: int = DEFAULT_PAUSE_AFTER_MS,
    wait_network: bool = False,
) -> bool:
    """Move to element, pause, click with visible press, pause after."""
    try:
        if not locator.count() or not locator.first.is_visible():
            return False
        if not human_move_to(page, locator, steps=steps):
            # Fallback: Playwright click still moves mouse (few steps).
            locator.first.click()
        else:
            _pause(page, pause_before_ms)
            page.mouse.down()
            _pause(page, 90)
            page.mouse.up()
        if wait_network:
            try:
                page.wait_for_load_state("networkidle")
            except Exception:
                pass
        _pause(page, pause_after_ms)
        return True
    except Exception:
        return False


def human_fill(
    page,
    locator,
    value: str,
    *,
    steps: int = DEFAULT_MOVE_STEPS,
    pause_after_ms: int = 600,
) -> bool:
    """Hover/click into a field then fill (cursor visible on focus)."""
    try:
        if not locator.count() or not locator.first.is_visible():
            return False
        human_move_to(page, locator, steps=steps)
        _pause(page, 200)
        locator.first.click()
        _pause(page, 150)
        locator.first.fill(value)
        _pause(page, pause_after_ms)
        return True
    except Exception:
        return False


def human_select_option(
    page,
    locator,
    value: str,
    *,
    steps: int = DEFAULT_MOVE_STEPS,
    pause_after_ms: int = 800,
) -> bool:
    """Move to select, open interaction, choose option."""
    try:
        if not locator.count() or not locator.first.is_visible():
            return False
        human_move_to(page, locator, steps=steps)
        _pause(page, DEFAULT_PAUSE_BEFORE_MS)
        locator.first.select_option(value)
        _pause(page, pause_after_ms)
        return True
    except Exception:
        return False


def human_hover(
    page,
    locator,
    *,
    steps: int = DEFAULT_MOVE_STEPS,
    pause_ms: int = 900,
) -> bool:
    """Slow move to element and linger (for callouts without clicking)."""
    if not human_move_to(page, locator, steps=steps):
        return False
    _pause(page, pause_ms)
    return True


def human_wheel(
    page,
    delta_y: int,
    *,
    steps: int = 4,
    pause_ms: int = 400,
) -> None:
    """Scroll in small chunks so the cursor stays visible on screen."""
    chunk = max(1, abs(delta_y) // max(1, steps))
    direction = 1 if delta_y >= 0 else -1
    remaining = abs(delta_y)
    while remaining > 0:
        step = min(chunk, remaining)
        page.mouse.wheel(0, direction * step)
        remaining -= step
        _pause(page, pause_ms)


def ensure_cursor_alive(page) -> None:
    """Re-run inject after HTMX swaps or soft navigations if needed."""
    try:
        page.evaluate(CURSOR_INIT_JS)
    except Exception:
        pass
