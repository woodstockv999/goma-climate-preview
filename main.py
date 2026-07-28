"""ごまモニター 室温連携プレビュー。

本番（~/apps/goma-monitor, port 3003）とは完全に独立。
DB も Ring も Gemini も使わず、dummy.py が生成する決定論的なデータだけで動く。
テンプレートは本番の web/templates を 2026-07-28 時点でコピーし、
patch_templates.py で室温 UI を差し込んだもの。
"""

import os
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import dummy

BASE_PATH = os.environ.get("BASE_PATH", "/goma-preview").rstrip("/")
# 実データが無いので「今」を固定する。時計が進んでも画面が変わらない方が比較しやすい。
NOW = datetime(2026, 7, 28, 23, 0, 0)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="goma-climate-preview", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

WEEKDAYS_JP = ["月", "火", "水", "木", "金", "土", "日"]


def _ctx(request: Request, **kw):
    """全テンプレート共通のコンテキスト。base はサブパス配信用のプレフィックス。"""
    stale = request.query_params.get("sensor") == "stale"
    ctx = {
        "base": BASE_PATH,
        "preview": True,
        "sensor_stale": stale,
        "now_str": NOW.strftime("%-m月%-d日 %H:%M"),
    }
    ctx.update(kw)
    return ctx


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    stale = request.query_params.get("sensor") == "stale"
    days = dummy.days_index(NOW, span=30)
    timeline = dummy.timeline_for(NOW.date(), NOW)
    latest = next((r for r in timeline if r["type"] == "log"), None)
    if latest is not None:
        latest = dict(latest)
        latest["date_str"] = NOW.date().isoformat()

    hourly_slots = [
        {"hour": c["hour"], "label": dummy.activity_for(NOW.date(), c["hour"]),
         "label_ja": dummy.LABEL_NAMES_JA[dummy.activity_for(NOW.date(), c["hour"])]}
        for c in dummy.climate_series(NOW.date(), NOW.hour)
    ]
    counts = {}
    for s in hourly_slots:
        counts[s["label"]] = counts.get(s["label"], 0) + 1
    chart_data = [
        {"label": k, "label_ja": dummy.LABEL_NAMES_JA[k], "count": v}
        for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
    ]

    series = dummy.climate_series(NOW.date(), NOW.hour)
    summary = dummy.summary_for(NOW.date(), timeline)

    return templates.TemplateResponse(
        request,
        "index_v2.html",
        context=_ctx(
            request,
            days=days,
            chart_data=chart_data,
            hourly_slots=hourly_slots,
            latest_entry=latest,
            today_str=NOW.strftime("%-m月%-d日") + f"（{WEEKDAYS_JP[NOW.weekday()]}）",
            climate=dummy.current_climate(NOW, stale=stale),
            climate_series=series,
            climate_summary=summary,
        ),
    )


@app.get("/day/{date_str}", response_class=HTMLResponse)
async def day_view(request: Request, date_str: str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse(f"{BASE_PATH}/")

    stale = request.query_params.get("sensor") == "stale"
    timeline = dummy.timeline_for(d, NOW)
    summary = dummy.summary_for(d, timeline)
    series = dummy.climate_series(d, NOW.hour if d == NOW.date() else 23)

    if d == NOW.date():
        climate = dummy.current_climate(NOW, stale=stale)
    else:
        last = series[-1]
        climate = {
            "temp": last["temp"], "hum": last["hum"], "status": last["status"],
            "status_ja": last["status_ja"], "hour": last["hour"],
            "measured_at": f"{last['hour']:02d}:00", "age_hours": 0, "is_stale": False,
        }
        if stale:
            climate = dummy.current_climate(NOW, stale=True)

    return templates.TemplateResponse(
        request,
        "day_v2.html",
        context=_ctx(
            request,
            date_str=date_str,
            date_display=d.strftime("%-m月%-d日") + f"（{WEEKDAYS_JP[d.weekday()]}）",
            timeline=timeline,
            summary=summary,
            label_names=dummy.LABEL_NAMES_JA,
            diary_content=(
                f"今日は最高 {summary['t_max']}℃ まで上がった。"
                + ("暑い時間帯は伏せて動かなかった。" if summary["hot_hours"] else "過ごしやすい一日だった。")
            ),
            diary_pending=False,
            climate=climate,
            climate_series=series,
            climate_summary=summary,
        ),
    )


@app.get("/image/{path:path}")
async def placeholder_image(path: str):
    """ダミー写真。実画像が無いので、時刻入りのプレースホルダ SVG を返す。"""
    hour = "??"
    stem = path.rsplit("/", 1)[-1].split(".")[0]
    if stem.isdigit():
        hour = f"{int(stem):02d}"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#332720"/><stop offset="60%" stop-color="#1a1210"/>
    <stop offset="100%" stop-color="#241a14"/></linearGradient></defs>
  <rect width="640" height="360" fill="url(#g)"/>
  <text x="320" y="185" font-size="86" text-anchor="middle" opacity=".55">&#128054;</text>
  <text x="320" y="250" font-size="20" text-anchor="middle" fill="#8c7464"
        font-family="sans-serif">{hour}:00 のダミー画像</text>
</svg>"""
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/healthz")
async def healthz():
    return {"ok": True, "app": "goma-climate-preview", "now": NOW.isoformat()}


# 本番にある更新系 API はプレビューには無い。押されたら 501 を返して意図を明示する。
@app.post("/api/log/{log_id}")
@app.post("/api/reanalyze/{log_id}")
@app.post("/snapshot")
async def not_in_preview(log_id: int = 0):
    return Response(
        content='{"detail":"プレビュー環境では更新できません（ダミーデータのため）"}',
        status_code=501, media_type="application/json; charset=utf-8",
    )
