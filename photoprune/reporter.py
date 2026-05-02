"""Self-contained HTML review report.

UX model: each photo card is either *Keep* (highlighted) or *Trash* (quiet).
Click anywhere on a card to toggle. The Save action emits a `selections.json`
listing the paths to remove — that's still what `cleaner.py` consumes.
"""

from __future__ import annotations

import base64
import html
import io
import urllib.parse
from pathlib import Path
from typing import List

from PIL import Image, ImageOps
from tqdm import tqdm

from .models import DuplicateGroup, PhotoFile

_THUMB_MAX = 480  # px on the long edge — also used as preview when zoomed
_THUMB_QUALITY = 76


def _thumb_data_uri(path: str) -> str:
    """Render a small JPEG thumbnail as a base64 data URI.

    EXIF orientation is normalized so portrait photos render upright.
    """
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((_THUMB_MAX, _THUMB_MAX), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=_THUMB_QUALITY, optimize=True)
            return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
    except Exception:
        return ""


def _file_url(path: str) -> str:
    """Local file:// URL pointing at the original image (used by the lightbox)."""
    abs_path = str(Path(path).resolve())
    return "file://" + urllib.parse.quote(abs_path, safe="/")


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


def _photo_card_html(
    photo: PhotoFile, group_id: str, suggested_keep: bool
) -> str:
    thumb = _thumb_data_uri(photo.path)
    full = _file_url(photo.path)
    sharp = f"{photo.sharpness:.0f}" if photo.sharpness is not None else "—"
    quality = f"{photo.quality_rank:.2f}" if photo.quality_rank is not None else "—"
    safe_path = html.escape(photo.path)
    safe_full = html.escape(full)
    safe_name = html.escape(photo.filename)

    suggested_badge = (
        '<span class="badge-suggested" title="Suggested by quality score">★</span>'
        if suggested_keep else ""
    )
    initial_state = "keep" if suggested_keep else "trash"

    return f"""
    <article class="photo" data-state="{initial_state}"
             data-suggested="{'1' if suggested_keep else '0'}"
             data-group="{html.escape(group_id)}"
             data-path="{safe_path}"
             data-full="{safe_full}">
      <button type="button" class="card-toggle" aria-pressed="{'true' if suggested_keep else 'false'}">
        <div class="thumb-wrap">
          <img loading="lazy" src="{thumb}" alt="{safe_name}" />
          <div class="status">
            <span class="state-pill keep">Keep</span>
            <span class="state-pill trash">→ Trash</span>
          </div>
          {suggested_badge}
        </div>
      </button>
      <div class="meta">
        <div class="filename" title="{safe_path}">{safe_name}</div>
        <div class="info">
          <span>{photo.width}×{photo.height}</span>
          <span>{_format_size(photo.size_bytes)}</span>
          <span>sharp {sharp}</span>
          <span>q {quality}</span>
        </div>
        <button type="button" class="zoom-btn" aria-label="View full size">
          <span class="zoom-icon">⌕</span> View
        </button>
      </div>
    </article>
    """


def _group_html(group: DuplicateGroup) -> str:
    detection = html.escape(group.detection_type)
    sim = f"{group.max_similarity:.2f}"

    # Suggested keep first, then by quality desc — the user sees the "winner"
    # of the group immediately.
    members = sorted(
        group.members,
        key=lambda p: (
            p.path != group.suggested_keep_path,
            -(p.quality_rank or 0),
        ),
    )
    cards = "\n".join(
        _photo_card_html(p, group.group_id, p.path == group.suggested_keep_path)
        for p in members
    )

    return f"""
    <section class="group" data-group="{html.escape(group.group_id)}">
      <header class="group-header">
        <div class="group-title">
          <h2>Group {html.escape(group.group_id)}</h2>
          <span class="pill type-{detection}">{detection}</span>
          <span class="muted">{group.size} photos · max similarity {sim}</span>
        </div>
        <div class="group-actions">
          <span class="group-counts" aria-live="polite">
            <span class="count-keep">1</span> keep
            ·
            <span class="count-trash">{group.size - 1}</span> trash
          </span>
          <button type="button" class="reset-group" data-group="{html.escape(group.group_id)}">
            ↺ Reset
          </button>
        </div>
      </header>
      <div class="photos">
        {cards}
      </div>
    </section>
    """


_CSS = """
*, *::before, *::after { box-sizing: border-box; }
:root {
  --bg: #f3f5f9;
  --surface: #ffffff;
  --border: #dfe3eb;
  --text: #1c2530;
  --muted: #67707c;
  --primary: #2a63ff;
  --primary-hover: #2353d4;
  --keep: #0f9d58;
  --keep-soft: #e6f5ec;
  --keep-text: #086a3a;
  --trash: #b94a48;
  --suggest: #d6a83a;
}
html, body { height: 100%; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  -webkit-font-smoothing: antialiased;
}
button { font: inherit; cursor: pointer; }

/* ---------- Top bar ---------- */
.topbar {
  position: sticky; top: 0; z-index: 20;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 16px;
  align-items: center;
  padding: 12px 28px;
}
.topbar h1 { margin: 0 0 2px; font-size: 16px; letter-spacing: 0.01em; }
.topbar .summary { font-size: 13px; color: var(--muted); }
.topbar .summary strong { color: var(--text); }
.topbar .album { font-size: 12px; color: var(--muted); margin-top: 2px; word-break: break-all; }
.topbar .actions { display: flex; gap: 8px; align-items: center; }
.btn {
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  border-radius: 6px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
}
.btn:hover { background: #f6f8fb; }
.btn.primary {
  background: var(--primary);
  color: white;
  border-color: var(--primary);
}
.btn.primary:hover { background: var(--primary-hover); border-color: var(--primary-hover); }
.btn.ghost { border-color: transparent; background: transparent; color: var(--muted); }
.btn.ghost:hover { color: var(--text); background: #eef1f5; }

/* ---------- Layout ---------- */
main { padding: 20px 28px 96px; max-width: 1480px; margin: 0 auto; }
.section-help {
  background: #fffbe9;
  border: 1px solid #f1e0a4;
  color: #6b5d22;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 13px;
}
.section-help kbd {
  background: #fef6d6;
  border: 1px solid #e0c878;
  border-radius: 3px;
  padding: 1px 5px;
  font-family: ui-monospace, monospace;
  font-size: 11px;
}
.empty {
  text-align: center;
  padding: 100px 24px;
  color: var(--muted);
  font-size: 15px;
}

/* ---------- Group ---------- */
section.group {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 18px 14px;
  margin-bottom: 18px;
}
section.group.empty-keep {
  border-color: #f1c0bf;
  background: #fff8f8;
}
.group-header {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 8px;
  margin-bottom: 14px;
}
.group-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.group-title h2 { margin: 0; font-size: 15px; font-weight: 600; }
.muted { color: var(--muted); font-size: 13px; }
.pill {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 3px 9px;
  border-radius: 999px;
  background: #eef1f6;
  color: var(--muted);
}
.pill.type-exact { background: #e6f5ec; color: #086a3a; }
.pill.type-near { background: #fff3df; color: #80570a; }
.pill.type-mixed { background: #ece8ff; color: #3f3491; }
.group-actions { display: flex; gap: 12px; align-items: center; }
.group-counts { font-size: 13px; color: var(--muted); }
.group-counts .count-keep { color: var(--keep-text); font-weight: 600; }
.group-counts .count-trash { color: var(--trash); font-weight: 600; }
.reset-group {
  border: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 12px;
}
.reset-group:hover { color: var(--text); background: #eef1f5; }

/* ---------- Photo grid ---------- */
.photos {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.photo {
  background: var(--surface);
  border-radius: 10px;
  border: 1px solid var(--border);
  overflow: hidden;
  display: flex; flex-direction: column;
  transition: box-shadow 120ms ease, transform 120ms ease, border-color 120ms ease;
  position: relative;
}
.photo:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(15, 25, 60, 0.06); }

.photo[data-state="keep"] {
  border-color: var(--keep);
  box-shadow: 0 0 0 2px var(--keep) inset;
  background: var(--keep-soft);
}
.photo[data-state="trash"] { opacity: 0.78; }
.photo[data-state="trash"] .thumb-wrap img { filter: saturate(0.6); }

/* ---------- Card toggle (clickable thumbnail area) ---------- */
.card-toggle {
  border: 0;
  background: transparent;
  padding: 0;
  display: block;
  width: 100%;
  text-align: left;
  position: relative;
}
.thumb-wrap {
  background: #14171c;
  position: relative;
  display: flex; align-items: center; justify-content: center;
  aspect-ratio: 4 / 3;
  overflow: hidden;
}
.thumb-wrap img {
  max-width: 100%; max-height: 100%;
  display: block;
  user-select: none;
  pointer-events: none;
}

.status {
  position: absolute; top: 8px; left: 8px;
  display: flex; gap: 6px;
  pointer-events: none;
}
.state-pill {
  font-size: 11px; font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  backdrop-filter: blur(4px);
  display: none;
}
.state-pill.keep { background: var(--keep); color: white; }
.state-pill.trash { background: rgba(28, 37, 48, 0.78); color: #f4f6fa; }
.photo[data-state="keep"] .state-pill.keep { display: inline-flex; }
.photo[data-state="trash"] .state-pill.trash { display: inline-flex; }

.badge-suggested {
  position: absolute; top: 8px; right: 8px;
  background: var(--suggest);
  color: white;
  font-weight: 700; font-size: 12px;
  width: 22px; height: 22px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  box-shadow: 0 2px 6px rgba(0,0,0,0.3);
  pointer-events: none;
}

.meta {
  padding: 10px 12px 12px;
  display: flex; flex-direction: column; gap: 4px;
  background: var(--surface);
}
.photo[data-state="keep"] .meta { background: var(--keep-soft); }
.filename {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.info {
  display: flex; flex-wrap: wrap; gap: 6px;
  font-size: 11px;
  color: var(--muted);
}
.info span::after { content: "·"; margin-left: 6px; opacity: 0.5; }
.info span:last-child::after { content: ""; }
.zoom-btn {
  align-self: flex-start;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  padding: 4px 0;
  margin-top: 2px;
}
.zoom-btn:hover { color: var(--primary); }
.zoom-icon { font-size: 14px; margin-right: 2px; }

/* ---------- Lightbox ---------- */
.lightbox {
  position: fixed; inset: 0;
  background: rgba(10, 14, 22, 0.92);
  display: none;
  z-index: 100;
  padding: 24px;
}
.lightbox[aria-hidden="false"] { display: flex; flex-direction: column; }
.lightbox-bar {
  display: flex; justify-content: space-between; align-items: center;
  color: #f4f6fa;
  margin-bottom: 12px;
  gap: 12px;
}
.lightbox-bar .lb-title { font-size: 14px; }
.lightbox-bar .lb-title .lb-meta { color: #b8bdc7; margin-left: 8px; font-size: 12px; }
.lightbox-bar .lb-actions { display: flex; gap: 8px; align-items: center; }
.lightbox-stage {
  flex: 1;
  position: relative;
  display: flex; align-items: center; justify-content: center;
  min-height: 0;
}
.lightbox-stage img {
  max-width: 100%; max-height: 100%;
  border-radius: 6px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}
.lightbox-stage .err {
  color: #f4d2d4;
  text-align: center;
  font-size: 14px;
  padding: 24px;
}
.lb-nav {
  position: absolute; top: 50%; transform: translateY(-50%);
  width: 48px; height: 48px;
  border-radius: 50%;
  background: rgba(255,255,255,0.12);
  color: white;
  border: 0;
  font-size: 22px;
}
.lb-nav:hover { background: rgba(255,255,255,0.22); }
.lb-prev { left: 12px; }
.lb-next { right: 12px; }
.lb-toggle {
  background: var(--keep);
  color: white;
  border-radius: 6px;
  border: 0;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
}
.lb-toggle.is-trash { background: rgba(255,255,255,0.14); color: white; }
.lb-close {
  background: transparent;
  border: 0; color: #b8bdc7;
  font-size: 26px;
  line-height: 1;
}
.lb-close:hover { color: white; }
.lb-help {
  text-align: center;
  color: #8b939f;
  font-size: 11px;
  margin-top: 8px;
  letter-spacing: 0.04em;
}
"""


_JS_TEMPLATE = """
(function () {
  const SELECTIONS_FILENAME = 'selections.json';

  function setCardState(card, state) {
    card.dataset.state = state;
    const btn = card.querySelector('.card-toggle');
    if (btn) btn.setAttribute('aria-pressed', state === 'keep' ? 'true' : 'false');
  }

  function toggleCard(card) {
    setCardState(card, card.dataset.state === 'keep' ? 'trash' : 'keep');
    refreshGroupCounts(card.dataset.group);
    refreshGlobalCounts();
  }

  function groupCards(groupId) {
    return document.querySelectorAll(`.photo[data-group="${CSS.escape(groupId)}"]`);
  }

  function refreshGroupCounts(groupId) {
    const cards = groupCards(groupId);
    let keep = 0, trash = 0;
    cards.forEach(c => { if (c.dataset.state === 'keep') keep++; else trash++; });
    const sec = document.querySelector(`section.group[data-group="${CSS.escape(groupId)}"]`);
    if (!sec) return;
    sec.querySelector('.count-keep').textContent = keep;
    sec.querySelector('.count-trash').textContent = trash;
    sec.classList.toggle('empty-keep', keep === 0);
  }

  function refreshGlobalCounts() {
    let keep = 0, trash = 0;
    document.querySelectorAll('.photo').forEach(c => {
      if (c.dataset.state === 'keep') keep++; else trash++;
    });
    const ke = document.getElementById('total-keep');
    const tr = document.getElementById('total-trash');
    if (ke) ke.textContent = keep;
    if (tr) tr.textContent = trash;
    const btn = document.getElementById('save-btn');
    if (btn) btn.textContent = trash === 0
      ? 'Save (nothing to trash)'
      : `Save & move ${trash} to trash`;
  }

  function gather() {
    const remove = [];
    document.querySelectorAll('.photo').forEach(card => {
      if (card.dataset.state === 'trash') remove.push(card.dataset.path);
    });
    return {
      version: '2',
      generated_at: new Date().toISOString(),
      remove
    };
  }

  function download(filename, text) {
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function resetGroup(groupId) {
    groupCards(groupId).forEach(c => {
      setCardState(c, c.dataset.suggested === '1' ? 'keep' : 'trash');
    });
    refreshGroupCounts(groupId);
    refreshGlobalCounts();
  }

  function resetAll() {
    document.querySelectorAll('.photo').forEach(c => {
      setCardState(c, c.dataset.suggested === '1' ? 'keep' : 'trash');
    });
    document.querySelectorAll('section.group').forEach(s => refreshGroupCounts(s.dataset.group));
    refreshGlobalCounts();
  }

  /* ---------- lightbox ---------- */
  let lbCurrentCard = null;

  function openLightbox(card) {
    lbCurrentCard = card;
    const lb = document.getElementById('lightbox');
    const img = document.getElementById('lb-img');
    const err = document.getElementById('lb-err');
    const title = document.getElementById('lb-title');
    const meta = document.getElementById('lb-meta');

    title.textContent = card.querySelector('.filename').textContent;
    meta.textContent = card.querySelector('.info').textContent.replace(/\\s+/g, ' ').trim();

    err.style.display = 'none';
    img.style.display = 'block';
    img.src = card.dataset.full;
    img.onerror = () => {
      img.style.display = 'none';
      err.style.display = 'block';
      err.textContent = 'Could not load original. Path: ' + card.dataset.path;
    };
    refreshLbToggle();
    lb.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeLightbox() {
    document.getElementById('lightbox').setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    lbCurrentCard = null;
  }

  function refreshLbToggle() {
    if (!lbCurrentCard) return;
    const btn = document.getElementById('lb-toggle');
    if (lbCurrentCard.dataset.state === 'keep') {
      btn.textContent = 'Move to trash';
      btn.classList.add('is-trash');
    } else {
      btn.textContent = 'Keep this one';
      btn.classList.remove('is-trash');
    }
  }

  function lbNav(delta) {
    if (!lbCurrentCard) return;
    const sibs = Array.from(lbCurrentCard.parentElement.querySelectorAll('.photo'));
    const i = sibs.indexOf(lbCurrentCard);
    if (i < 0) return;
    const next = sibs[(i + delta + sibs.length) % sibs.length];
    openLightbox(next);
  }

  /* ---------- wiring ---------- */
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('section.group').forEach(s => refreshGroupCounts(s.dataset.group));
    refreshGlobalCounts();

    document.body.addEventListener('click', (e) => {
      const toggleBtn = e.target.closest('.card-toggle');
      if (toggleBtn) {
        const card = toggleBtn.closest('.photo');
        if (card) toggleCard(card);
        e.preventDefault();
        return;
      }
      const zoom = e.target.closest('.zoom-btn');
      if (zoom) {
        const card = zoom.closest('.photo');
        if (card) openLightbox(card);
        return;
      }
      const reset = e.target.closest('.reset-group');
      if (reset) {
        resetGroup(reset.dataset.group);
        return;
      }
      if (e.target.id === 'save-btn') {
        download(SELECTIONS_FILENAME, JSON.stringify(gather(), null, 2));
        return;
      }
      if (e.target.id === 'reset-all-btn') {
        resetAll();
        return;
      }
      if (e.target.id === 'lb-close') { closeLightbox(); return; }
      if (e.target.id === 'lb-prev') { lbNav(-1); return; }
      if (e.target.id === 'lb-next') { lbNav(1); return; }
      if (e.target.id === 'lb-toggle') {
        if (lbCurrentCard) { toggleCard(lbCurrentCard); refreshLbToggle(); }
        return;
      }
    });

    document.addEventListener('keydown', (e) => {
      const lbOpen = document.getElementById('lightbox').getAttribute('aria-hidden') === 'false';
      if (lbOpen) {
        if (e.key === 'Escape') { closeLightbox(); e.preventDefault(); }
        else if (e.key === 'ArrowLeft') { lbNav(-1); e.preventDefault(); }
        else if (e.key === 'ArrowRight') { lbNav(1); e.preventDefault(); }
        else if (e.key === 'k' || e.key === 'K') {
          if (lbCurrentCard) { toggleCard(lbCurrentCard); refreshLbToggle(); }
          e.preventDefault();
        }
      } else if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        download(SELECTIONS_FILENAME, JSON.stringify(gather(), null, 2));
      }
    });
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

    # Largest groups first; ties broken by max similarity desc.
    groups = sorted(groups, key=lambda g: (-g.size, -g.max_similarity))

    if show_progress and groups:
        groups_iter = tqdm(groups, desc="report", unit="grp")
    else:
        groups_iter = groups
    sections = "\n".join(_group_html(g) for g in groups_iter)

    if not groups:
        sections = (
            '<div class="empty">'
            "<p>No duplicate groups found at this threshold.</p>"
            '<p class="muted">Try lowering <code>--threshold</code> '
            "(default 0.94) for looser matches.</p>"
            "</div>"
        )

    total_groups = len(groups)
    total_in_groups = sum(g.size for g in groups)
    initial_keep = total_groups
    initial_trash = total_in_groups - total_groups
    save_label = (
        "Save (nothing to trash)"
        if initial_trash == 0
        else f"Save &amp; move {initial_trash} to trash"
    )

    js = _JS_TEMPLATE
    safe_album = html.escape(str(album_path))

    help_block = ""
    if groups:
        help_block = (
            '<div class="section-help">'
            "<strong>How to review:</strong> click a card to toggle "
            "<em>Keep</em> or <em>Trash</em>. The ★ marks the auto-suggested "
            "keeper based on sharpness, resolution, and file size. "
            "Click <strong>View</strong> to inspect at full size "
            "(<kbd>←</kbd>/<kbd>→</kbd> navigate, <kbd>K</kbd> toggle, "
            "<kbd>Esc</kbd> close). When you're done, click "
            "<strong>Save &amp; move N to trash</strong>."
            "</div>"
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>PhotoPrune — Review</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>{_CSS}</style>
</head>
<body>
<header class="topbar">
  <div>
    <h1>PhotoPrune Review</h1>
    <div class="summary">
      <strong>{total_groups}</strong> group(s) ·
      <strong>{total_in_groups}</strong> photos ·
      <strong id="total-keep">{initial_keep}</strong> keeping ·
      <strong id="total-trash">{initial_trash}</strong> to trash
    </div>
    <div class="album">album: {safe_album}</div>
  </div>
  <div class="actions">
    <button type="button" id="reset-all-btn" class="btn ghost">↺ Reset all to suggested</button>
    <button type="button" id="save-btn" class="btn primary">{save_label}</button>
  </div>
</header>
<main>
  {help_block}
  {sections}
</main>

<div class="lightbox" id="lightbox" aria-hidden="true" role="dialog" aria-label="Photo preview">
  <div class="lightbox-bar">
    <div class="lb-title">
      <span id="lb-title"></span>
      <span class="lb-meta" id="lb-meta"></span>
    </div>
    <div class="lb-actions">
      <button type="button" id="lb-toggle" class="lb-toggle">Keep this one</button>
      <button type="button" id="lb-close" class="lb-close" aria-label="Close">×</button>
    </div>
  </div>
  <div class="lightbox-stage">
    <button type="button" class="lb-nav lb-prev" id="lb-prev" aria-label="Previous">‹</button>
    <img id="lb-img" alt="" />
    <div class="err" id="lb-err" style="display:none;"></div>
    <button type="button" class="lb-nav lb-next" id="lb-next" aria-label="Next">›</button>
  </div>
  <div class="lb-help">← / →  navigate · K  toggle keep/trash · Esc  close</div>
</div>

<script>{js}</script>
</body>
</html>
"""
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path
