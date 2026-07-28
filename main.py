"""ごまモニター 室温連携プレビュー。

UI を本番と完全に一致させるため、**本番の web/router.py をそのまま import して使う**。
集計ロジックを再実装しないので、行動サマリー・タイムライン・24hストリップ・
30日一覧は本番と同一の結果になる。

本番に対する安全性:
  - DATA_DIR を本番より先にこのアプリの data/ へ向けるので、DB 接続先は
    スナップショット（data/goma.db）。本番 DB へは読み書きとも到達しない。
  - 画像は 242MB あるので複製せず、専用ルートが本番 data/ を読み取り専用で参照する
    （本番 router の /image は DATA_DIR 配下しか許さないため、先に登録して差し替える）。
  - Gemini を叩く /api/reanalyze と Ring を叩く /snapshot は import 前に潰す。

室温だけが dummy.py 由来の合成値で、テンプレートへは ClimateTemplates が注入する。
"""

import os
import sys
from datetime import date, datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROD_DIR = Path("/home/w00dst0ck/apps/goma-monitor")

# ── 本番モジュールを import する前に接続先を差し替える（順序が重要） ──
os.environ["DATA_DIR"] = str(APP_DIR / "data")
sys.path.insert(0, str(PROD_DIR))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402

import dummy  # noqa: E402
from web import router as prod_router  # noqa: E402

BASE_PATH = os.environ.get("BASE_PATH", "/goma-preview").rstrip("/")

# 接続先が本当にスナップショットを向いているか、起動時に確かめる
import database  # noqa: E402

assert str(APP_DIR) in database.DATABASE_URL, f"DB がプレビュー外を向いている: {database.DATABASE_URL}"
assert str(APP_DIR) in str(prod_router.DATA_DIR), f"DATA_DIR が不正: {prod_router.DATA_DIR}"


def _target_date(ctx) -> date:
    """このページが対象にしている日付。"""
    ds = ctx.get("date_str")
    if ds:
        try:
            return datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            pass
    latest = ctx.get("latest_entry")
    if latest and latest.get("date_str"):
        try:
            return datetime.strptime(latest["date_str"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
    days = ctx.get("days") or []
    if days:
        try:
            return datetime.strptime(days[0]["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError, TypeError):
            pass
    return date.today()


def _last_hour(ctx, d: date) -> int:
    """その日の記録がある最後の時刻。無ければ23時。"""
    latest = ctx.get("latest_entry")
    if latest and latest.get("date_str") == d.isoformat() and latest.get("hour") is not None:
        return int(latest["hour"])
    hours = [
        e["hour"] for e in (ctx.get("timeline") or [])
        if e.get("type") == "log" and e.get("hour") is not None
    ]
    return max(hours) if hours else 23


class ClimateTemplates(Jinja2Templates):
    """本番テンプレート（パッチ済みコピー）へ室温データを流し込む。

    本番 router のハンドラには一切手を入れず、描画の直前で context を足すだけ。
    """

    def TemplateResponse(self, *args, **kwargs):
        request = args[0] if args and isinstance(args[0], Request) else kwargs.get("request")
        ctx = kwargs.get("context")
        if ctx is None:
            for a in args:
                if isinstance(a, dict):
                    ctx = a
                    break
        if ctx is not None and request is not None:
            try:
                self._inject(request, ctx)
            except Exception as e:  # 室温の合成でページ全体を落とさない
                ctx.setdefault("base", BASE_PATH)
                ctx["climate_error"] = str(e)
        return super().TemplateResponse(*args, **kwargs)

    @staticmethod
    def _inject(request: Request, ctx: dict) -> None:
        stale = request.query_params.get("sensor") == "stale"
        ctx["base"] = BASE_PATH
        ctx["preview"] = True
        ctx["sensor_stale"] = stale

        d = _target_date(ctx)
        rows = dummy.series(d, _last_hour(ctx, d))
        ctx["climate_series"] = rows
        ctx["climate_summary"] = dummy.summarize(rows)
        ctx["climate"] = dummy.current(rows, stale=stale)

        # 30日一覧: 各日の最高気温
        for row in ctx.get("days") or []:
            try:
                dd = datetime.strptime(row["date"], "%Y-%m-%d").date()
            except (ValueError, KeyError, TypeError):
                continue
            t, key, ja = dummy.day_max(dd)
            row["t_max"], row["t_status"], row["t_status_ja"] = t, key, ja

        # タイムライン: 各時刻の室温
        by_hour = {r["hour"]: r for r in rows}
        for e in ctx.get("timeline") or []:
            if e.get("type") == "log":
                e["climate"] = by_hour.get(e.get("hour"))


prod_router.templates = ClimateTemplates(directory=str(APP_DIR / "templates"))

app = FastAPI(title="goma-climate-preview", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(PROD_DIR / "web/static")), name="static")


# ── 外部を叩く経路は本番 router より先に登録して潰す（先勝ちで無効化される） ──
def _blocked(reason: str):
    return JSONResponse({"detail": reason}, status_code=501)


@app.post("/api/reanalyze/{log_id}")
async def _no_reanalyze(log_id: int):
    return _blocked("プレビューでは再分析しません（Gemini API を消費するため）")


@app.post("/snapshot")
async def _no_snapshot():
    return _blocked("プレビューでは撮影しません（Ring カメラに接続しないため）")


@app.get("/image/{media_path:path}")
async def serve_image(media_path: str):
    """写真は本番 data/ を読み取り専用で参照する（242MB を複製しないため）。

    本番 router の同名ルートは DATA_DIR 配下しか許さず、symlink を .resolve() で
    辿ると外に出て 403 になる。ここで先に登録して差し替える。
    ディレクトリトラバーサルは本番と同じ方式で塞ぐ。
    """
    root = (PROD_DIR / "data").resolve()
    full = (root / media_path).resolve()
    if not full.is_relative_to(root):
        return _blocked("Forbidden")
    if not full.is_file():
        return JSONResponse({"detail": "Image not found"}, status_code=404)
    return FileResponse(str(full), media_type="image/jpeg")


@app.get("/healthz")
async def healthz():
    return {
        "ok": True,
        "app": "goma-climate-preview",
        "db": database.DATABASE_URL,
        "data_dir": str(prod_router.DATA_DIR),
    }


app.include_router(prod_router.router)
