"""Self-contained HTML report for reviewing duplicate groups."""

from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path
from typing import List

from PIL import Image
from tqdm import tqdm

from .models import DuplicateGroup, PhotoFile

_THUMB_MAX = 320
_THUMB_QUALITY = 78


def _thumb_data_uri(path: str) -> str:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((_THUMB_MAX, _THUMB_MAX), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=_THUMB_QUALITY, optimize=True)
            data = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{data}"
    except Exception:
        return ""


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    units = ["KB", "MB", "GB"]
    val = n / 1024
    for unit in units:
        if val < 1024:
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} TB"


def _photo_card_html(photo: PhotoFile, group_id: str, suggested_keep: bool) -> str:
    thumb = _thumb_data_uri(photo.path)
    suggested = " suggested-keep" if suggested_keep else ""
    badge = '<span class="badge keep">suggested keep</span>' if suggested_keep else ""
    sharp = f"{photo.sharpness:.1f}" if photo.sharpness is not None else "—"
    quality = f"{photo.quality_rank:.3f}" if photo.quality_rank is not None else "—"
    safe_path = html.escape(photo.path)
    safe_name = html.escape(photo.filename)
    checked = "" if suggested_keep else " checked"
    return f"""
        <label class="photo{suggested}">
          <input type="checkbox" class="remove-cb"
                 data-group="{html.escape(group_id)}"
                 data-path="{safe_path}"{checked} />
          <div class="thumb-wrap">
            <img loading="lazy" src="{thumb}" alt="{safe_name}" />
            {badge}
          </div>
          <div class="meta">
            <div class="filename" title="{safe_path}">{safe_name}</div>
            <div class="info">
              {photo.width}×{photo.height} · {_format_size(photo.size_bytes)}<br/>
              sharp {sharp} · quality {quality}
            </div>
          </div>
        </label>
    """


def _group_html(group: DuplicateGroup) -> str:
    detection = html.escape(group.detection_type)
    sim = f"{group.max_similarity:.3f}"
    cards = "\n".join(
        _photo_card_html(p, group.group_id, p.path == group.suggested_keep_path)
        for p in group.members
    )
    return f"""
    <section class="group" data-group="{html.escape(group.group_id)}">
      <header class="group-header">
        <h2>Group {html.escape(group.group_id)}</h2>
        <span class="pill type-{detection}">{detection}</span>
        <span class="pill">{group.size} photos</span>
        <span class="pill">max similarity {sim}</span>
      </header>
      <div class="photos">
        {cards}
      </div>
    </section>
    """


_CSS = """
*, *::before, *::after { box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  margin: 0;
  background: #f4f5f7;
  color: #1f2933;
}
header.top {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #ffffff;
  border-bottom: 1px solid #e1e5eb;
  padding: 14px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
header.top h1 { margin: 0; font-size: 18px; }
header.top .summary { color: #5b6573; font-size: 14px; }
header.top .actions { margin-left: auto; display: flex; gap: 8px; }
button {
  cursor: pointer;
  border: 0;
  border-radius: 6px;
  padding: 8px 14px;
  font-size: 14px;
  background: #2c63ff;
  color: white;
}
button.secondary { background: #4b5566; }
button:hover { filter: brightness(1.08); }
main { padding: 16px 24px 80px; max-width: 1400px; margin: 0 auto; }
section.group {
  background: white;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 18px;
  border: 1px solid #e1e5eb;
}
.group-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.group-header h2 { margin: 0; font-size: 16px; font-weight: 600; }
.pill {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  background: #eef2f7;
  font-size: 12px;
  color: #4b5566;
}
.pill.type-exact { background: #e7f6ec; color: #1d6f3a; }
.pill.type-near { background: #fff3e1; color: #93570d; }
.pill.type-mixed { background: #ece9fe; color: #4a3aaf; }
.photos {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.photo {
  display: block;
  border: 2px solid #e1e5eb;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: white;
  transition: border-color 100ms;
  position: relative;
}
.photo input { display: none; }
.photo:has(input.remove-cb:checked) {
  border-color: #d83a3a;
  box-shadow: 0 0 0 1px #d83a3a inset;
}
.photo.suggested-keep:has(input.remove-cb:not(:checked)) {
  border-color: #2bb673;
  box-shadow: 0 0 0 1px #2bb673 inset;
}
.thumb-wrap {
  position: relative;
  background: #1f2933;
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 4 / 3;
  overflow: hidden;
}
.thumb-wrap img {
  max-width: 100%;
  max-height: 100%;
  display: block;
}
.badge {
  position: absolute;
  top: 8px;
  left: 8px;
  background: #2bb673;
  color: white;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}
.meta {
  padding: 8px 10px 10px;
  font-size: 12px;
}
.filename {
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.info { color: #5b6573; margin-top: 4px; line-height: 1.4; }
.empty {
  text-align: center;
  padding: 80px 24px;
  color: #5b6573;
}
"""

_JS_TEMPLATE = """
(function () {
  const SELECTIONS_FILENAME = 'selections.json';
  const REPORT_VERSION = __VERSION__;

  function gather() {
    const cbs = document.querySelectorAll('input.remove-cb');
    const remove = [];
    cbs.forEach(cb => {
      if (cb.checked) remove.push(cb.dataset.path);
    });
    return {
      version: REPORT_VERSION,
      generated_at: new Date().toISOString(),
      remove
    };
  }

  function download(filename, text) {
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function updateCounts() {
    const cbs = document.querySelectorAll('input.remove-cb');
    let removed = 0;
    cbs.forEach(cb => { if (cb.checked) removed += 1; });
    const totalEl = document.getElementById('count-total');
    const remEl = document.getElementById('count-removed');
    if (totalEl) totalEl.textContent = cbs.length;
    if (remEl) remEl.textContent = removed;
  }

  document.addEventListener('change', (e) => {
    if (e.target && e.target.classList.contains('remove-cb')) {
      updateCounts();
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    updateCounts();
    const saveBtn = document.getElementById('save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        const data = gather();
        download(SELECTIONS_FILENAME, JSON.stringify(data, null, 2));
      });
    }
    const selectAllBtn = document.getElementById('select-all');
    if (selectAllBtn) {
      selectAllBtn.addEventListener('click', () => {
        document.querySelectorAll('input.remove-cb').forEach(cb => { cb.checked = true; });
        updateCounts();
      });
    }
    const clearBtn = document.getElementById('clear-all');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        document.querySelectorAll('input.remove-cb').forEach(cb => { cb.checked = false; });
        updateCounts();
      });
    }
    const resetBtn = document.getElementById('reset-suggested');
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        document.querySelectorAll('input.remove-cb').forEach(cb => {
          const card = cb.closest('.photo');
          cb.checked = !(card && card.classList.contains('suggested-keep'));
        });
        updateCounts();
      });
    }
  });
})();
"""


def render_report(
    groups: List[DuplicateGroup],
    output_path: Path,
    *,
    album_path: Path,
    show_progress: bool = True,
) -> Path:
    """Render a self-contained HTML report and write it to `output_path`."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Sort: largest groups first, then by max_similarity desc.
    groups = sorted(groups, key=lambda g: (-g.size, -g.max_similarity))

    if show_progress and groups:
        groups_iter = tqdm(groups, desc="report", unit="grp")
    else:
        groups_iter = groups
    sections = "\n".join(_group_html(g) for g in groups_iter)

    if not groups:
        sections = '<div class="empty">No duplicate groups found.</div>'

    total_photos = sum(g.size for g in groups)
    total_groups = len(groups)
    suggested_removals = sum(
        sum(1 for p in g.members if p.path != g.suggested_keep_path) for g in groups
    )

    js = _JS_TEMPLATE.replace("__VERSION__", json.dumps("1"))
    safe_album = html.escape(str(album_path))

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>PhotoPrune — Duplicate Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>{_CSS}</style>
</head>
<body>
<header class="top">
  <h1>PhotoPrune Report</h1>
  <span class="summary">
    {total_groups} groups · {total_photos} photos ·
    {suggested_removals} suggested removals ·
    <span id="count-removed">0</span>/<span id="count-total">0</span> selected
  </span>
  <span class="summary" title="{safe_album}">album: {safe_album}</span>
  <div class="actions">
    <button id="reset-suggested" class="secondary">Reset to suggested</button>
    <button id="select-all" class="secondary">Select all</button>
    <button id="clear-all" class="secondary">Clear</button>
    <button id="save-btn">Save Selections</button>
  </div>
</header>
<main>
{sections}
</main>
<script>{js}</script>
</body>
</html>
"""
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path
