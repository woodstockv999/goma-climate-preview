"""本番テンプレートのコピーに室温 UI を差し込む。

templates/ は ~/apps/goma-monitor/web/templates を 2026-07-28 にコピーしたもの。
ここで行う挿入が、そのまま本番へ移植すべき差分になる。

アンカーが見つからない／複数一致したら即座に落とす（黙って壊さない）。
    python3 patch_templates.py
"""

import sys
from pathlib import Path

T = Path(__file__).parent / "templates"
MARK = "<!-- climate-patch -->"


def patch(fname, edits):
    p = T / fname
    src = p.read_text(encoding="utf-8")
    if MARK in src:
        print(f"  {fname}: 適用済みなのでスキップ")
        return
    for i, (anchor, repl, expect) in enumerate(edits, 1):
        n = src.count(anchor)
        if n != expect:
            sys.exit(f"[FAIL] {fname} edit#{i}: アンカーの一致数が {n}（期待 {expect}）\n---\n{anchor[:200]}\n---")
        src = src.replace(anchor, repl)
    p.write_text(src + f"\n{MARK}\n", encoding="utf-8")
    print(f"  {fname}: {len(edits)} 箇所 適用")


# ══════════════════════════════════════════════════════════════
# 1) base_v2.html — 共通トークン・共通CSS・共通JS・サブパス対応
# ══════════════════════════════════════════════════════════════

CLIMATE_TOKENS = """
      /* ── 室温ステータス（categorical validator 5/5 PASS） ── */
      --t-cold:  #2f6fb0;
      --t-ok:    #2b9873;
      --t-warn:  #c67610;
      --t-crit:  #a82815;
"""

CLIMATE_CSS = """
    /* ══ 室温 UI ══════════════════════════════ */
    .t-pill {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 3px 10px; border-radius: 20px;
      font-size: 0.72rem; font-weight: 700; color: #fff; white-space: nowrap; flex: none;
    }
    .t-pill.cold  { background: var(--t-cold); }
    .t-pill.ok    { background: var(--t-ok); }
    .t-pill.warn  { background: var(--t-warn); }
    .t-pill.crit  { background: var(--t-crit); }
    .t-pill.stale { background: var(--c-absent); color: #3d3d3d; }

    /* 写真オーバーレイの室温バッジ（トップ） */
    .ov-temp {
      margin-left: auto; display: inline-flex; align-items: center; gap: 4px;
      font-size: 0.7rem; font-weight: 800; color: #fff;
      padding: 3px 10px; border-radius: 20px; white-space: nowrap;
      font-variant-numeric: tabular-nums;
      background: rgba(255,255,255,0.18); backdrop-filter: blur(4px);
    }
    .ov-temp.warn  { background: rgba(198,118,16,0.92); }
    .ov-temp.crit  { background: rgba(168,40,21,0.94); }
    .ov-temp.stale { background: rgba(255,255,255,0.14); color: rgba(255,255,255,0.6); }

    /* 一行サマリー（トップ） */
    .today-climate {
      display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap;
      padding: 0.5rem 0.6rem; border-radius: 12px;
      background: var(--surface); border: 1.5px solid var(--border-2);
      font-size: 0.78rem; line-height: 1.5;
    }
    .today-climate .lead { font-weight: 800; font-variant-numeric: tabular-nums; }
    .today-climate .note { color: var(--muted); }
    .today-climate.crit  { background: #fdf0ec; border-color: #f2d3c9; }
    .today-climate.stale { background: #f1f0ef; border-color: #ddd9d5; }
    .today-climate.stale .lead { color: var(--muted); }

    /* 行動ストリップに揃えたスパークライン（トップ）。
       枠は .day-card と同じ処方。横パディングは入れない——入れるとSVGの幅が縮み、
       真上の 24h ストリップと時間軸がズレて、この図の意味（暑い時間帯に何をしていたか）が壊れる。
       上下の余白だけカード内に持たせ、左右は border 1.5px 分のみ内側に入る。 */
    .spark-card {
      background: var(--surface);
      border: 1.5px solid var(--border-2);
      border-radius: 12px;
      padding: 0.4rem 0 0.3rem;
      margin-top: 0.45rem;
    }
    .spark-head {
      display: flex; align-items: baseline; justify-content: space-between;
      flex-wrap: wrap; gap: 0.1rem 0.6rem;
      font-size: 0.66rem; color: var(--muted);
      padding: 0 0.6rem; margin-bottom: 0.15rem;
    }
    .spark-head b { color: var(--text); font-size: 0.74rem; font-variant-numeric: tabular-nums; }
    /* 危険ラインの凡例。破線の見本を出すことで、図中の点線が何なのかを言葉で示す */
    .thresh-key {
      display: inline-block; width: 13px; height: 0; vertical-align: middle;
      border-top: 2px dashed var(--t-crit); margin: 0 4px 0 6px;
    }
    .spark { display: block; width: 100%; height: auto; }

    /* 一覧の最高室温（トップ） */
    .day-top { display: flex; align-items: baseline; gap: 0.4rem; }
    .day-tmax {
      margin-left: auto; font-size: 0.7rem; color: var(--muted);
      font-variant-numeric: tabular-nums; white-space: nowrap;
      display: inline-flex; align-items: center; gap: 4px;
    }
    .day-tmax i { width: 6px; height: 6px; border-radius: 50%; flex: none; display: block; }
    .day-tmax i.warn { background: var(--t-warn); }
    .day-tmax i.crit { background: var(--t-crit); }
    .day-tmax.crit { color: var(--t-crit); font-weight: 700; }

    /* センサー停止の注意書き（日別詳細）。
       室温カードは廃してグラフ2枚だけにしたが、停止時に無言でグラフを出すと
       「データが流れている」と誤読されるため、ここだけは残す。 */
    .climate-stale {
      font-size: 0.76rem; line-height: 1.55; padding: 0.5rem 0.6rem;
      border-radius: 10px; margin-bottom: 0.55rem;
      background: #f1f0ef; border: 1px solid #ddd9d5; color: #4a443f;
    }

    /* グラフ（日別詳細） */
    .chart-card {
      background: var(--surface); border: 1.5px solid var(--border-2);
      border-radius: 16px; padding: 0.7rem 0.3rem 0.5rem; margin-bottom: 0.55rem;
    }
    .chart-head { display: flex; align-items: baseline; gap: 0.45rem; padding: 0 0.6rem; }
    .chart-title { font-size: 0.8rem; font-weight: 800; }
    .chart-now { margin-left: auto; font-size: 0.74rem; color: var(--muted); font-variant-numeric: tabular-nums; }
    /* JS のクランプが効かなかった場合の保険。横だけ塞ぐ（overflow:hidden だと
       吹き出しが上方向に切れるので不可。overflow-x:clip は縦を visible のまま残せる） */
    .chart-wrap { position: relative; overflow-x: clip; }
    /* pan-y にしないと、グラフに指を置いた状態で縦スクロールできなくなる */
    .chart-svg { display: block; width: 100%; height: auto; touch-action: pan-y; }
    .grid-line { stroke: var(--border-2); stroke-width: 1; }
    .axis-text { fill: var(--muted); font-size: 9px; font-variant-numeric: tabular-nums; }
    .band-crit { fill: var(--t-crit); opacity: 0.07; }
    .thresh-line { stroke: var(--t-crit); stroke-width: 1; stroke-dasharray: 3 3; opacity: 0.55; }
    .thresh-text { fill: var(--t-crit); font-size: 8.5px; font-weight: 700; }
    .series-line { fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
    .end-dot { stroke: var(--surface); stroke-width: 2; }
    .cross-line { stroke: var(--text); stroke-width: 1; opacity: 0.35; }
    .chart-tip {
      position: absolute; pointer-events: none; background: var(--charcoal); color: #fff;
      font-size: 0.7rem; font-weight: 700; padding: 0.22rem 0.5rem; border-radius: 6px;
      white-space: nowrap; font-variant-numeric: tabular-nums; opacity: 0;
      transition: opacity 0.12s; transform: translate(-50%, -130%); z-index: 5;
    }

    /* タイムラインの温度（控えめ・異常時だけドット） */
    .tl-temp {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 0.68rem; color: var(--muted);
      font-variant-numeric: tabular-nums; white-space: nowrap; flex: none;
    }
    .tl-temp i { width: 5px; height: 5px; border-radius: 50%; flex: none; display: block; }
    .tl-temp i.warn { background: var(--t-warn); }
    .tl-temp i.crit { background: var(--t-crit); }
    .tl-temp.crit { color: var(--t-crit); font-weight: 700; }

    /* ── ズーム禁止（写真の拡大表示中だけ解除） ──
       ダブルタップ拡大は touch-action で殺せる。ピンチは iOS Safari が
       user-scalable=no を無視するため JS の gesture イベントで止める。 */
    body { touch-action: manipulation; }
    #lb  { touch-action: auto; }   /* ライトボックス内は拡大できるまま残す */

    /* プレビュー環境であることを常時明示するバー。
       内箱を .site-header-inner と同じ max-width:640px に揃える
       （揃えないとデスクトップでここだけ全幅に伸びて本番と違って見える）。 */
    .preview-bar {
      background: repeating-linear-gradient(135deg, #2a1d14, #2a1d14 10px, #322419 10px, #322419 20px);
      color: #e0b070; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.02em;
    }
    .preview-bar-inner {
      max-width: 640px; margin: 0 auto; padding: 0.3rem 1rem;
      display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
    }
    .preview-bar a { color: #f0b020; margin-left: auto; }
"""

CLIMATE_JS = """
  <script>
  /* 室温グラフ共通描画。テンプレートが埋めた JSON を読んで SVG を組む。 */
  (function () {
    "use strict";
    var node = document.getElementById("climate-data");
    if (!node) { return; }
    var SERIES = JSON.parse(node.textContent || "[]");
    if (!SERIES.length) { return; }
    var NS = "http://www.w3.org/2000/svg";
    var C = { ok: "#2b9873", crit: "#a82815", hum: "#3a9fd4" };

    function el(n, a) {
      var e = document.createElementNS(NS, n);
      for (var k in a) { if (a[k] !== null && a[k] !== undefined) { e.setAttribute(k, a[k]); } }
      return e;
    }

    /* ── トップ: 行動ストリップと同じ時間軸のスパークライン ── */
    var spark = document.getElementById("spark");
    if (spark) {
      var n = SERIES.length, W = n * 10, H = 40, pT = 5, pB = 3, ih = H - pT - pB;
      spark.setAttribute("viewBox", "0 0 " + W + " " + H);
      var lo = 22, hi = 34;
      var sx = function (i) { return i * 10 + 5; };
      var sy = function (v) { return pT + ih - ((v - lo) / (hi - lo)) * ih; };
      var f = document.createDocumentFragment();
      f.appendChild(el("rect", { x: 0, y: pT, width: W, height: Math.max(0, sy(28) - pT), class: "band-crit" }));
      f.appendChild(el("line", { x1: 0, y1: sy(28), x2: W, y2: sy(28), class: "thresh-line" }));
      var segs = [], cur = null;
      SERIES.forEach(function (c, i) {
        var hot = c.temp >= 28, pt = [sx(i), sy(c.temp)];
        if (!cur) { cur = { hot: hot, pts: [pt] }; }
        else if (cur.hot !== hot) { cur.pts.push(pt); segs.push(cur); cur = { hot: hot, pts: [pt] }; }
        else { cur.pts.push(pt); }
      });
      if (cur) { segs.push(cur); }
      segs.forEach(function (sg) {
        if (sg.pts.length < 2) { return; }
        var d = sg.pts.map(function (p, k) {
          return (k ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1);
        }).join(" ");
        f.appendChild(el("path", { d: d, class: "series-line", stroke: sg.hot ? C.crit : C.ok }));
      });
      var lastC = SERIES[n - 1];
      f.appendChild(el("circle", {
        cx: sx(n - 1), cy: sy(lastC.temp), r: 3,
        fill: lastC.temp >= 28 ? C.crit : C.ok, stroke: "#fff", "stroke-width": 1.5
      }));
      // 閾値ラベルは図内に置かない。高さ40単位に対して文字が大きく、折れ線と重なる。
      // 意味（何の線か）も伝わらないので、見出しの凡例に出している。
      spark.appendChild(f);
    }

    /* ── 日別詳細: 温度・湿度の2枚（1枚に2軸は立てない） ── */
    function build(id, tipId, vals, lo, hi, ticks, unit, color, thresh) {
      var svg = document.getElementById(id);
      if (!svg) { return; }
      var tip = document.getElementById(tipId);
      var W = 340, H = thresh ? 124 : 100, pL = 26, pR = 10, pT = 10, pB = 18;
      var iw = W - pL - pR, ih = H - pT - pB, last = vals.length - 1;
      svg.setAttribute("viewBox", "0 0 " + W + " " + H);
      var X = function (i) { return pL + (iw * i) / last; };
      var Y = function (v) { return pT + ih - ((v - lo) / (hi - lo)) * ih; };
      var f = document.createDocumentFragment();

      if (thresh && thresh < hi) {
        f.appendChild(el("rect", { x: pL, y: pT, width: iw, height: Math.max(0, Y(thresh) - pT), class: "band-crit" }));
        f.appendChild(el("line", { x1: pL, y1: Y(thresh), x2: pL + iw, y2: Y(thresh), class: "thresh-line" }));
        var tt = el("text", { x: pL + iw, y: Y(thresh) - 3, class: "thresh-text", "text-anchor": "end" });
        tt.textContent = "危険 " + thresh + "℃";
        f.appendChild(tt);
      }
      ticks.forEach(function (v) {
        f.appendChild(el("line", { x1: pL, y1: Y(v), x2: pL + iw, y2: Y(v), class: "grid-line" }));
        var t = el("text", { x: pL - 5, y: Y(v) + 3, class: "axis-text", "text-anchor": "end" });
        t.textContent = v + unit;
        f.appendChild(t);
      });
      [0, 6, 12, 18, last].forEach(function (i) {
        if (i > last) { return; }
        var t = el("text", {
          x: X(i), y: H - 5, class: "axis-text",
          "text-anchor": i === 0 ? "start" : (i === last ? "end" : "middle")
        });
        t.textContent = (i === 23 ? 24 : i) + "時";
        f.appendChild(t);
      });

      var dLine = "";
      vals.forEach(function (v, i) { dLine += (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1) + " "; });
      var gid = id + "-g", defs = el("defs", {});
      var lg = el("linearGradient", { id: gid, x1: "0", y1: "0", x2: "0", y2: "1" });
      lg.appendChild(el("stop", { offset: "0%", "stop-color": color, "stop-opacity": "0.2" }));
      lg.appendChild(el("stop", { offset: "100%", "stop-color": color, "stop-opacity": "0" }));
      defs.appendChild(lg); f.appendChild(defs);
      f.appendChild(el("path", {
        d: dLine + "L" + X(last).toFixed(1) + " " + (pT + ih) + " L" + pL + " " + (pT + ih) + " Z",
        fill: "url(#" + gid + ")", stroke: "none"
      }));
      f.appendChild(el("path", { d: dLine, class: "series-line", stroke: color }));
      f.appendChild(el("circle", { cx: X(last), cy: Y(vals[last]), r: 4, fill: color, class: "end-dot" }));

      var cross = el("line", { x1: 0, y1: pT, x2: 0, y2: pT + ih, class: "cross-line", opacity: "0" });
      var hdot = el("circle", { cx: 0, cy: 0, r: 4.5, fill: color, class: "end-dot", opacity: "0" });
      f.appendChild(cross); f.appendChild(hdot);
      var hit = el("rect", { x: pL, y: pT, width: iw, height: ih, fill: "transparent", "pointer-events": "all" });
      f.appendChild(hit);
      svg.appendChild(f);

      function move(ev) {
        var r = svg.getBoundingClientRect();
        var i = Math.round(((((ev.clientX - r.left) / r.width) * W) - pL) / iw * last);
        if (i < 0) { i = 0; }
        if (i > last) { i = last; }
        var cx = X(i), cy = Y(vals[i]);
        cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("opacity", "1");
        hdot.setAttribute("cx", cx); hdot.setAttribute("cy", cy); hdot.setAttribute("opacity", "1");
        // 先に文面を入れてから幅を測る（幅が確定しないとクランプできない）
        tip.textContent = SERIES[i].hour + ":00　" + vals[i] + unit;
        tip.style.opacity = "1";
        tip.style.top = (cy / H * 100) + "%";
        // 右端・左端で吹き出しがコンテナからはみ出すと、ページ全体が横に広がり
        // iPhone が縮小表示になる。左右をコンテナ内へクランプする。
        var wrapW = (svg.parentElement && svg.parentElement.clientWidth) || svg.clientWidth;
        var half = tip.offsetWidth / 2 + 2;
        var px = (cx / W) * wrapW;
        if (wrapW > tip.offsetWidth + 4) {
          px = Math.max(half, Math.min(wrapW - half, px));
        }
        tip.style.left = px + "px";
      }
      hit.addEventListener("pointermove", move);
      hit.addEventListener("pointerdown", move);
      hit.addEventListener("pointerleave", function () {
        cross.setAttribute("opacity", "0"); hdot.setAttribute("opacity", "0"); tip.style.opacity = "0";
      });
    }

    var temps = SERIES.map(function (c) { return c.temp; });
    var hums = SERIES.map(function (c) { return c.hum; });
    build("chart-temp", "tip-temp", temps, 22, 34, [22, 28, 34], "℃", C.crit, 28);
    build("chart-hum", "tip-hum", hums, 40, 90, [40, 65, 90], "%", C.hum, null);
  })();
  </script>
"""

ZOOM_JS = """
  <script>
  /* ページのピンチズームを禁止する。ただし写真を拡大表示している間（#lb 表示中）は許可。

     meta viewport の user-scalable=no / maximum-scale は iOS Safari が
     アクセシビリティのため無視するので効かない。Safari 固有の gesture イベントを
     止めるのが実際に効く唯一の方法。ダブルタップ拡大は CSS の touch-action 側で処理。 */
  (function () {
    "use strict";
    function lightboxOpen() {
      var lb = document.getElementById("lb");
      return !!lb && getComputedStyle(lb).display !== "none";
    }
    ["gesturestart", "gesturechange", "gestureend"].forEach(function (type) {
      document.addEventListener(type, function (e) {
        if (!lightboxOpen()) { e.preventDefault(); }
      }, { passive: false });
    });
  })();
  </script>
"""

PREVIEW_BAR = """  {% if preview %}
  <div class="preview-bar">
    <div class="preview-bar-inner">
      <span>プレビュー環境 — 室温のみダミー値</span>
      {% if sensor_stale %}
        <a href="?">センサーを正常に戻す</a>
      {% else %}
        <a href="?sensor=stale">センサー停止を再現</a>
      {% endif %}
    </div>
  </div>
  {% endif %}
"""

patch("base_v2.html", [
    # 室温トークンを既存パレットの直後に追加
    ("      --c-unknown:   #c0a898;\n    }", "      --c-unknown:   #c0a898;\n" + CLIMATE_TOKENS + "    }", 1),
    # 共通CSS
    ("    @media (prefers-reduced-motion: reduce) {", CLIMATE_CSS + "\n    @media (prefers-reduced-motion: reduce) {", 1),
    # サブパス対応
    ('<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">',
     '<link rel="apple-touch-icon" sizes="180x180" href="{{ base }}/static/apple-touch-icon.png">', 1),
    ('<link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32.png">',
     '<link rel="icon" type="image/png" sizes="32x32" href="{{ base }}/static/favicon-32.png">', 1),
    ('<link rel="shortcut icon" href="/favicon.ico">',
     '<link rel="shortcut icon" href="{{ base }}/static/favicon.ico">', 1),
    ('<a class="site-logo" href="/">', '<a class="site-logo" href="{{ base }}/">', 1),
    # プレビューバー + 共通JS
    ('  <main class="page">', PREVIEW_BAR + '  <main class="page">', 1),
    ("  </main>\n</body>", "  </main>\n" + CLIMATE_JS + ZOOM_JS + "</body>", 1),
])


# ══════════════════════════════════════════════════════════════
# 2) index_v2.html — トップページ
# ══════════════════════════════════════════════════════════════

OV_TEMP = """          {% endif %}
          {% if climate %}
          <span class="ov-temp {{ climate.status }}">🌡 {% if climate.temp is not none %}{{ climate.temp }}℃{% else %}--.-℃{% endif %}</span>
          {% endif %}
"""

CLIMATE_ROW = """
<!-- ── 室温（今どうなのか） ───────────────────── -->
{% if climate %}
<div class="today-section" style="margin-top:0.9rem;">
  <div class="section-label">室温</div>
  <div class="today-climate {{ climate.status }}">
    <span class="t-pill {{ climate.status }}">{{ climate.status_ja }}</span>
    {% if climate.temp is not none %}
      <span class="lead">{{ climate.temp }}℃ / {{ climate.hum }}%</span>
      <span class="note">
        本日の最高 {{ climate_summary.t_max }}℃
        {%- if climate_summary.hot_range %}（{{ climate_summary.hot_range[0] }}〜{{ climate_summary.hot_range[1] }}時が28℃超）{% endif %}
      </span>
    {% else %}
      <span class="lead">計測できていない</span>
      <span class="note">最終更新 {{ climate.measured_at }}（{{ climate.age_hours }}時間前）・電池切れの可能性</span>
    {% endif %}
  </div>
</div>
{% endif %}

"""

SPARK = """  <!-- 行動ストリップと同じ時間軸の室温 -->
  {% if climate_series %}
  <div class="spark-card">
    <div class="spark-head">
      <span>室温<i class="thresh-key"></i>28℃ 危険ライン</span>
      <span>最高 <b>{{ climate_summary.t_max }}℃</b>　最低 <b>{{ climate_summary.t_min }}℃</b></span>
    </div>
    <svg class="spark" id="spark" role="img"
         aria-label="直近24時間の室温推移。最高{{ climate_summary.t_max }}℃、最低{{ climate_summary.t_min }}℃。"></svg>
  </div>
  <script type="application/json" id="climate-data">{{ climate_series | tojson }}</script>
  {% endif %}

"""

DAY_TOP = """      <div class="day-top">
        <div class="day-date">{{ d.date }}</div>
        {% if d.t_max is defined %}
        <span class="day-tmax {{ 'crit' if d.t_status == 'crit' else '' }}">
          {% if d.t_status in ('warn', 'crit') %}<i class="{{ d.t_status }}"></i>{% endif %}最高 {{ d.t_max }}℃
        </span>
        {% endif %}
      </div>"""

patch("index_v2.html", [
    ('          <span class="today-presence-badge away">🚪 お出かけ中</span>\n          {% endif %}\n',
     '          <span class="today-presence-badge away">🚪 お出かけ中</span>\n' + OV_TEMP, 1),
    ("<!-- ── 24h Activity Strip ─────────────────────── -->", CLIMATE_ROW + "<!-- ── 24h Activity Strip ─────────────────────── -->", 1),
    ('  <div class="strip-legend">', SPARK + '  <div class="strip-legend">', 1),
    ('      <div class="day-date">{{ d.date }}</div>', DAY_TOP, 1),
    ('href="/day/{{ d.date }}"', 'href="{{ base }}/day/{{ d.date }}"', 1),
    ("src=\"/image/{{ d.latest_media_path }}\"", "src=\"{{ base }}/image/{{ d.latest_media_path }}\"", 1),
    ("{% set img_path = '/image/' + latest_entry.media_path %}",
     "{% set img_path = base + '/image/' + latest_entry.media_path %}", 1),
    ("fetch('/snapshot'", "fetch('{{ base }}/snapshot'", 1),
])


# ══════════════════════════════════════════════════════════════
# 3) day_v2.html — 日別詳細ページ
# ══════════════════════════════════════════════════════════════

CLIMATE_BLOCK = """<!-- ── 室温（詳細ページはグラフ2枚のみ） ──────── -->
{% if climate and climate_series %}
<div class="section-label">室温</div>
{% if climate.temp is none %}
<div class="climate-stale">
  <strong>{{ climate.age_hours }}時間 更新が止まっている。</strong>電池切れの可能性。以下は停止前までの記録。
</div>
{% endif %}
<div class="chart-card">
  <div class="chart-head">
    <span class="chart-title">室温</span>
    <span class="chart-now">最高 {{ climate_summary.t_max }}℃ / 最低 {{ climate_summary.t_min }}℃</span>
  </div>
  <div class="chart-wrap">
    <svg class="chart-svg" id="chart-temp" role="img"
         aria-label="室温の推移。最高{{ climate_summary.t_max }}℃、最低{{ climate_summary.t_min }}℃。"></svg>
    <div class="chart-tip" id="tip-temp"></div>
  </div>
</div>
<div class="chart-card">
  <div class="chart-head">
    <span class="chart-title">湿度</span>
    <span class="chart-now">{{ climate_series[-1].hum }}%</span>
  </div>
  <div class="chart-wrap">
    <svg class="chart-svg" id="chart-hum" role="img" aria-label="湿度の推移。"></svg>
    <div class="chart-tip" id="tip-hum"></div>
  </div>
</div>
<script type="application/json" id="climate-data">{{ climate_series | tojson }}</script>
{% endif %}

"""

# お出かけ中だけ金バッジ＋黄色いカードで強調していたのをやめ、他のラベルと同じピルに統一する。
# dog_present=0 の行は全件 activity_label='absent' なので、ピルでも正しく「お出かけ中」と出る。
# あわせて各行の室温を右端に置く。
OUTING_ANCHOR = """            {% if is_outing %}
              <span class="outing-badge">🐾 お出かけ中！</span>
            {% else %}
              <span class="pill {{ entry.activity_label }}">{{ entry.activity_label_ja }}</span>
            {% endif %}
"""

ROW_BADGES = """            <span class="pill {{ entry.activity_label }}">{{ entry.activity_label_ja }}</span>
            {% if entry.climate %}
            <span class="tl-temp {{ 'crit' if entry.climate.status == 'crit' else '' }}">
              {%- if entry.climate.status in ('warn', 'crit') %}<i class="{{ entry.climate.status }}"></i>{% endif -%}
              {{ entry.climate.temp }}℃ · {{ entry.climate.hum }}%
            </span>
            {% endif %}
"""

# 上で消したので死ぬ CSS（お出かけ中の黄色い強調そのもの）
OUTING_CSS = """  /* Outing */
  .tl-entry.type-absent .tl-card {
    background: linear-gradient(135deg, #fefce8, #fef9c3);
    border-color: #fde68a;
  }
  .outing-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 12px;
    border-radius: 50px;
    background: linear-gradient(135deg, var(--gold), #e6a820);
    color: #3d1f00;
    font-size: 0.8rem;
    font-weight: 800;
  }

"""

LABEL_DESC_JS = """let _editLogId = null;

// 「見直す」でラベルを選んだときに入れる定型の説明文。
// ラベル変更のたびに必ず入れ替える。既存の説明文（Gemini が書いた文）は
// 全記録に入っているので、「空欄のときだけ」等の条件を付けると一度も発動しない。
//
// 文面は prompt.md の description 規約に揃えること:
//   「必ず『ごま』という名前を含め、少し自由で可愛らしい一言」
// 以下は sleeping/active/sitting/walking/playing/drinking/absent が
// prompt.md の例文そのもの。unknown だけ例が無いので同じ調子で補った。
const LABEL_DESC = {
  sleeping: 'ごまはスヤスヤおやすみ中です',
  active:   'ごまはパッチリ起きています',
  sitting:  'ごまはまったりくつろぎ中です',
  walking:  'ごまはトコトコ移動中です',
  playing:  'ごまは元気にあそんでいます',
  drinking: 'ごまはおみずを飲んでいます',
  absent:   'ごまはどこかへお出かけ中です',
  unknown:  'ごまの様子がよく見えません',
};

function applyLabelDesc() {
  const label = document.getElementById('edit-label').value;
  document.getElementById('edit-desc').value = LABEL_DESC[label] || '';
}
"""

patch("day_v2.html", [
    # ── 「見直す」の定型文オートフィル（室温連携とは独立した機能追加） ──
    ("let _editLogId = null;\n", LABEL_DESC_JS, 1),
    ('<select id="edit-label">', '<select id="edit-label" onchange="applyLabelDesc()">', 1),

    # AI の分析精度バッジ（87% 等）を削除。
    # タイムラインに湿度が % で並ぶようになり、どちらの % か判別できないため。
    ('              {% if entry.confidence %}<span class="conf-badge">{{ "%.0f"|format(entry.confidence * 100) }}%</span>{% endif %}\n', "", 1),
    # 上で消したので死ぬ CSS
    ("  .conf-badge {\n    font-size: 0.65rem;\n    color: var(--muted);\n  }\n", "", 1),
    # バッジを消したので常に null になる死んだ参照
    ("    const confEl = row.querySelector('.conf-badge');\n"
     "    if (confEl) confEl.textContent = `${Math.round(data.confidence * 100)}%`;\n", "", 1),
    # 再分析後の投票バッジ挿入が confEl 起点だったため、バッジが消えると
    # `confEl?.after()` が no-op になり DOM へ挿さらない。操作ボタンの親に入れる。
    ("      confEl?.after(voteEl);",
     "      row.querySelector('.btn-action')?.parentElement?.prepend(voteEl);", 1),
    ("<!-- Timeline -->", CLIMATE_BLOCK + "<!-- Timeline -->", 1),
    # お出かけ中の金バッジを通常ピルに統一し、各行に室温を足す
    (OUTING_ANCHOR, ROW_BADGES, 1),
    # 黄色い強調の CSS を削除
    (OUTING_CSS, "", 1),
    ('<a href="/"', '<a href="{{ base }}/"', 1),
    ("{% set img_url = ('/image/' + entry.media_path) if entry.media_path else \"\" %}",
     "{% set img_url = (base + '/image/' + entry.media_path) if entry.media_path else \"\" %}", 1),
    ("fetch(`/api/log/${_editLogId}`", "fetch(`{{ base }}/api/log/${_editLogId}`", 1),
    ("fetch(`/api/reanalyze/${logId}`", "fetch(`{{ base }}/api/reanalyze/${logId}`", 1),
])

print("完了。")
