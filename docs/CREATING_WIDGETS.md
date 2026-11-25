# Creating a Custom StartHub Widget

Adding a brand-new widget to StartHub takes three small steps — no Win32 boilerplate required.

> **Quickest route (zero fork needed):** If your widget only displays metrics or status rows, use the built-in **[Custom JSON](../examples/custom_json/README.md)** widget (`columns`, `hero`, or `list`) with a 20-line Python script.

---

## Step 1 — Create a Data Provider (`starthub/providers/my_widget.py`)

Providers run on daemon threads, keep thread-safe state behind a `threading.Lock`, and call `on_change()` only when data actually changes.

```python
from __future__ import annotations
import threading
import time
from typing import Any, Callable, Dict, Optional

class MyWidgetProvider:
    def __init__(self, config: Dict[str, Any], on_change: Optional[Callable[[], None]] = None):
        self.config = config
        self.on_change = on_change
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._visible = threading.Event()
        self._state: Dict[str, Any] = {"value": "—"}

    def set_visible(self, visible: bool) -> None:
        self._visible.set() if visible else self._visible.clear()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def start(self) -> None:
        if self.config.get("enabled", False):
            threading.Thread(target=self._loop, name="starthub-my-widget", daemon=True).start()

    def stop(self) -> None:
        self._stopped.set()

    def _loop(self) -> None:
        while not self._stopped.wait(2.0):
            if not self._visible.is_set():
                continue
            with self._lock:
                self._state = {"value": "42%"}
            if self.on_change:
                self.on_change()
```

## Step 2 — Create a Pure PIL Renderer (`starthub/widgets/my_widget.py`)

All widgets draw onto a 2× supersampled RGBA `RenderContext` using semantic `ctx.theme.role(...)` colors so both `multi_accent` and `single_accent` themes work automatically:

```python
from __future__ import annotations
from typing import Any, Dict
from . import Box, RenderContext, draw_card_surface

def draw_my_widget(ctx: RenderContext, box: Box, state: Dict[str, Any]) -> None:
    S = ctx.scale
    x1, y1, x2, y2 = box
    draw_card_surface(ctx, box)
    accent = ctx.theme.role("primary")
    ctx.draw.text(((x1 + 14) * S, (y1 + 12) * S), "My Widget", font=ctx.font(14, "bold"), fill=ctx.theme.text_primary)
    ctx.draw.text(((x1 + 14) * S, (y1 + 36) * S), str(state.get("value", "—")), font=ctx.font(22, "bold"), fill=(*accent, 255))
```

Clickable regions are registered via `ctx.add_spot(x1, y1, x2, y2, left_cb, right_cb, "unique_hover_id")`.

## Step 3 — Register in 4 Places

1. `starthub/config.py` — add default widget config and add the ID to `ALL_WIDGET_IDS`.
2. `starthub/providers/__init__.py` — instantiate inside `ProviderHub` + add synthetic demo data in `build_demo_snapshot()`.
3. `starthub/renderer.py` — add a `CardSpec` in `build_wing_specs()` and dispatch in `render_wing()`.
4. `starthub/settings_ui.py` — add `(Title, Tier, cfg_key)` to `WIDGET_META` so users can toggle and reorder it in GUI Settings.

Finally, add a headless render test in `tests/` and run:

```powershell
python tools/scan_private.py
pytest -v
```
