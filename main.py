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

import climate_store  # noqa: E402
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


# UI 刷新案（v3 = Apple 準拠 / v4 = 黒地の観測所）は 2026-07-28 に不採用。
# テンプレートは templates/*_v3.html, *_v4.html に残してあるが、配信はしない。
# 見返すときは _v2.html を差し替える分岐を戻すこと（git 履歴に実装がある）。
#
# 切替に使っていた cookie がブラウザに残っていると刷新案が出続けるので、
# 応答のたびに期限切れにして現行UIへ引き戻す。
UI_COOKIE = "goma_ui"


class ClimateTemplates(Jinja2Templates):
    """本番テンプレート（パッチ済みコピー）へ室温データを流し込む。

    本番 router のハンドラには一切手を入れず、描画の直前で context を足すだけ。
    テンプレート名の _v2 → _v3 差し替えもここで行うので、router 側は
    どちらのUIを描いているか知らないままでいられる。
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

        response = super().TemplateResponse(*args, **kwargs)
        if request is not None and UI_COOKIE in request.cookies:
            response.delete_cookie(UI_COOKIE, path="/")
        return response

    @staticmethod
    def _inject(request: Request, ctx: dict) -> None:
        stale = request.query_params.get("sensor") == "stale"
        # 既定は Govee の実測値。?src=dummy で従来の合成データに戻せる
        # （実測はまだ積み上がっていないので、UI の見え方を確かめたいときに使う）。
        use_dummy = request.query_params.get("src") == "dummy"
        src = dummy if use_dummy else climate_store

        ctx["base"] = BASE_PATH
        ctx["preview"] = True
        ctx["sensor_stale"] = stale
        ctx["climate_src"] = "dummy" if use_dummy else "govee"

        d = _target_date(ctx)
        # 合成データは「写真がある最後の時刻」で打ち切る（未来を作らないため）。
        # 実測はセンサーが独立して動くので、写真の有無で切ってはいけない
        # （14時が最後の写真、22時が最後の計測、という日に室温が丸ごと消えた）。
        upto = 23 if not use_dummy else _last_hour(ctx, d)
        rows = src.series(d, upto)
        ctx["climate_series"] = rows
        ctx["climate_summary"] = src.summarize(rows)
        ctx["climate"] = src.current(rows, stale=stale)

        # 30日一覧: 各日の最高気温。記録の無い日はキーごと置かない
        # （None を入れると「最高 None℃」と描かれる）。
        for row in ctx.get("days") or []:
            try:
                dd = datetime.strptime(row["date"], "%Y-%m-%d").date()
            except (ValueError, KeyError, TypeError):
                continue
            t, key, ja = src.day_max(dd)
            if t is None:
                continue
            row["t_max"], row["t_status"], row["t_status_ja"] = t, key, ja

        # タイムライン: 各時刻の室温
        by_hour = {r["hour"]: r for r in rows}
        for e in ctx.get("timeline") or []:
            if e.get("type") == "log":
                e["climate"] = by_hour.get(e.get("hour"))

        # トップのスパークライン用。24hストリップ（現在時刻で終わる24枠）と
        # 1対1に並べる。記録の無い時間は None を残して長さを保つ——ここを詰めると
        # 真上のストリップと時間軸がズレて、この図の意味が壊れる。
        slots = ctx.get("hourly_slots") or []
        if not slots:
            ctx["climate_strip"] = []
        elif use_dummy:
            ctx["climate_strip"] = [by_hour.get(s["hour"]) for s in slots]
        else:
            ctx["climate_strip"] = climate_store.recent_hours(len(slots))


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
