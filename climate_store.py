"""Govee H5179 の実測値の取得と保存。

Govee の公開APIは**現在値しか返さない**（履歴エンドポイントが存在しない）ので、
24時間のグラフを描くには自分で定期取得して溜めるしかない。ここがその層。

  record_once()  … 1回取得して climate.db へ積む（cron から10分おきに叩く）
  series(date)   … その日の毎時値（同じ時間内の複数サンプルは平均）
  current()      … 直近の値と、何時間更新が止まっているか

★温度の単位について
  H5179 の /device/state は **単位フィールドを返さない**。実測では華氏で返ってきた
  （74.66 = 23.7℃）。Govee アプリ側の表示設定で摂氏に変わる可能性があるため、
  値そのものから判定する:

      室内温度で 45 を超えるのは華氏だけ、45 未満なら摂氏
      （摂氏45℃の室内も、華氏45°F=7℃の室内も、暖房のある家では起こらない）

  GOVEE_TEMP_UNIT=F / =C を置けば自動判定より優先される。
  変換前の生値は raw_temp に必ず残すので、後から単位の取り違えを検出できる。
"""

import os
import sqlite3
import uuid
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path

import httpx

JST = timezone(timedelta(hours=9))
BASE = "https://openapi.api.govee.com/router/api/v1"
SKU = "H5179"

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent / "data"))
DB_PATH = DATA_DIR / "climate.db"

# 室温ステータス（dummy.py と同じ閾値。UI 側の色分けと1対1）
THRESHOLDS = [
    ("cold", None, 20.0, "寒い"),
    ("ok", 20.0, 26.0, "快適"),
    ("warn", 26.0, 28.0, "注意"),
    ("crit", 28.0, None, "危険"),
]
CRIT_TEMP = 28.0
# 何時間データが来なければ「止まった」とみなすか。通知の閾値も兼ねる。
# 動作確認のときだけ GOMA_STALE_HOURS=0.01 のように小さくして試せる。
STALE_HOURS = float(os.environ.get("GOMA_STALE_HOURS", "3"))

# 華氏か摂氏かの分かれ目。室内でこの値をまたぐのは単位が違うときだけ。
UNIT_SPLIT = 45.0
PLAUSIBLE_C = (-15.0, 55.0)


class GoveeError(RuntimeError):
    pass


def _key() -> str:
    key = os.environ.get("GOVEE_API_KEY", "").strip()
    if not key:
        # pm2 起動時は .env を読まないので、ここで拾う
        env = Path(__file__).resolve().parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("GOVEE_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    break
    if not key:
        raise GoveeError("GOVEE_API_KEY が無い")
    return key


def to_celsius(raw: float) -> float:
    """生値を摂氏へ。単位の判定根拠はモジュール冒頭のコメント。"""
    unit = os.environ.get("GOVEE_TEMP_UNIT", "").strip().upper()
    if unit == "C":
        return raw
    if unit == "F":
        return (raw - 32.0) * 5.0 / 9.0
    return (raw - 32.0) * 5.0 / 9.0 if raw > UNIT_SPLIT else raw


def temp_status(t):
    if t is None:
        return ("stale", "データなし")
    for key, lo, hi, ja in THRESHOLDS:
        if (lo is None or t >= lo) and (hi is None or t < hi):
            return (key, ja)
    return ("crit", "危険")


# ── 保存 ────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("""
        CREATE TABLE IF NOT EXISTS climate_log (
            ts       TEXT PRIMARY KEY,   -- ISO8601 (JST, naive)
            temp_c   REAL NOT NULL,
            hum      REAL NOT NULL,
            raw_temp REAL NOT NULL,      -- 変換前。単位が変わったらここで気づける
            online   INTEGER NOT NULL
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS ix_climate_ts ON climate_log(ts)")
    con.execute("CREATE TABLE IF NOT EXISTS climate_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)")
    con.commit()
    return con


def fetch_state(device: str | None = None) -> dict:
    """/device/state を1回。device 未指定なら /user/devices から H5179 を探す。"""
    headers = {"Content-Type": "application/json", "Govee-API-Key": _key()}
    with httpx.Client(timeout=20.0, headers=headers) as client:
        if not device:
            res = client.get(f"{BASE}/user/devices")
            if res.status_code != 200:
                raise GoveeError(f"/user/devices HTTP {res.status_code}: {res.text[:200]}")
            for d in (res.json().get("data") or []):
                if d.get("sku") == SKU:
                    device = d["device"]
                    break
            if not device:
                raise GoveeError(f"{SKU} が Govee アカウントに見つからない")

        res = client.post(f"{BASE}/device/state", json={
            "requestId": str(uuid.uuid4()),
            "payload": {"sku": SKU, "device": device},
        })
    if res.status_code != 200:
        raise GoveeError(f"/device/state HTTP {res.status_code}: {res.text[:200]}")

    caps = {c.get("instance"): (c.get("state") or {}).get("value")
            for c in (res.json().get("payload") or {}).get("capabilities", [])}
    raw = caps.get("sensorTemperature")
    hum = caps.get("sensorHumidity")
    if raw is None or hum is None:
        raise GoveeError(f"温湿度が返ってこない: {caps}")

    temp_c = round(to_celsius(float(raw)), 1)
    if not (PLAUSIBLE_C[0] <= temp_c <= PLAUSIBLE_C[1]):
        raise GoveeError(f"換算後の温度が異常: raw={raw} → {temp_c}℃（単位判定を疑う）")

    return {
        "device": device,
        "temp_c": temp_c,
        "hum": round(float(hum), 1),
        "raw_temp": float(raw),
        "online": bool(caps.get("online", True)),
    }


def record_once(device: str | None = None) -> dict:
    st = fetch_state(device)
    ts = datetime.now(JST).replace(tzinfo=None, microsecond=0)
    con = _connect()
    try:
        con.execute(
            "INSERT OR REPLACE INTO climate_log(ts, temp_c, hum, raw_temp, online) VALUES (?,?,?,?,?)",
            (ts.isoformat(sep=" "), st["temp_c"], st["hum"], st["raw_temp"], int(st["online"])),
        )
        con.commit()
    finally:
        con.close()
    st["ts"] = ts
    return st


# ── 読み出し ─────────────────────────────────────────────────────────

def _rows(sql: str, args=()) -> list:
    if not DB_PATH.exists():
        return []
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    try:
        return con.execute(sql, args).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()


def series(d: _date, upto_hour: int = 23) -> list:
    """その日の毎時値。1時間に複数サンプルあれば平均する（10分刻みのゆらぎを均す）。

    記録の無い時間は行そのものを作らない。埋めると「動いていた」ように見えてしまう。
    """
    rows = _rows(
        "SELECT CAST(strftime('%H', ts) AS INTEGER) AS h, AVG(temp_c), AVG(hum) "
        "FROM climate_log WHERE date(ts) = ? GROUP BY h ORDER BY h",
        (d.isoformat(),),
    )
    out = []
    for h, t, hum in rows:
        if h is None or h > upto_hour:
            continue
        t = round(t, 1)
        key, ja = temp_status(t)
        out.append({"hour": int(h), "temp": t, "hum": int(round(hum)),
                    "status": key, "status_ja": ja})
    return out


def recent_hours(n: int = 24) -> list:
    """直近n時間の毎時値。**記録の無い時間は None を入れて長さを保つ**。

    トップの24hストリップ（現在時刻で終わる24枠）と1対1で並べるための形。
    日付をまたぐので series() の「その日ぶん」では代用できない。
    """
    now = datetime.now(JST).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=n - 1)
    rows = _rows(
        "SELECT strftime('%Y-%m-%d %H', ts) AS k, AVG(temp_c), AVG(hum) "
        "FROM climate_log WHERE ts >= ? GROUP BY k",
        (start.isoformat(sep=" "),),
    )
    got = {k: (t, h) for k, t, h in rows}
    out = []
    for i in range(n):
        d = start + timedelta(hours=i)
        v = got.get(d.strftime("%Y-%m-%d %H"))
        if v is None:
            out.append(None)
            continue
        t = round(v[0], 1)
        key, ja = temp_status(t)
        out.append({"hour": d.hour, "temp": t, "hum": int(round(v[1])),
                    "status": key, "status_ja": ja})
    return out


def summarize(rows):
    if not rows:
        return None
    temps = [r["temp"] for r in rows]
    hot = [r for r in rows if r["temp"] >= CRIT_TEMP]
    return {
        "t_max": max(temps),
        "t_min": min(temps),
        "hot_hours": len(hot),
        "hot_range": (hot[0]["hour"], hot[-1]["hour"]) if hot else None,
    }


def day_max(d: _date):
    rows = series(d)
    if not rows:
        return None, "stale", "データなし"
    t = max(r["temp"] for r in rows)
    key, ja = temp_status(t)
    return t, key, ja


def current(rows=None, stale: bool = False, **_):
    """室温カード/バッジ用の現在値。DBの最新行を直接見る（毎時平均ではなく生の直近）。"""
    def _stale(measured_at="—", age=None):
        return {"temp": None, "hum": None, "status": "stale", "status_ja": "データなし",
                "hour": None, "measured_at": measured_at,
                "age_hours": age if age is not None else 0, "is_stale": True}

    if stale:
        return _stale("（停止を再現中）", STALE_HOURS * 14)

    r = _rows("SELECT ts, temp_c, hum FROM climate_log ORDER BY ts DESC LIMIT 1")
    if not r:
        return _stale("記録なし")
    ts_s, temp, hum = r[0]
    try:
        ts = datetime.fromisoformat(ts_s)
    except ValueError:
        return _stale("記録なし")

    age = (datetime.now(JST).replace(tzinfo=None) - ts).total_seconds() / 3600.0
    if age >= STALE_HOURS:
        return _stale(ts.strftime("%-m月%-d日 %H:%M"), int(age))

    key, ja = temp_status(temp)
    return {"temp": round(temp, 1), "hum": int(round(hum)), "status": key, "status_ja": ja,
            "hour": ts.hour, "measured_at": ts.strftime("%H:%M"),
            "age_hours": int(age), "is_stale": False}


def has_data() -> bool:
    return bool(_rows("SELECT 1 FROM climate_log LIMIT 1"))


# ── 監視状態（通知の重複を避けるための覚え書き） ──────────────────────

def get_meta(key: str, default=None):
    r = _rows("SELECT v FROM climate_meta WHERE k = ?", (key,))
    return r[0][0] if r else default


def set_meta(key: str, value: str) -> None:
    con = _connect()
    try:
        con.execute("INSERT OR REPLACE INTO climate_meta(k, v) VALUES (?, ?)", (key, str(value)))
        con.commit()
    finally:
        con.close()


# ── 暑さの段階 ──────────────────────────────────────────────────────
#
# 閾値ちょうどで判定すると、25.9 → 26.1 → 25.9 と揺れるたびに通知が飛ぶ。
# 上がるときは閾値ちょうど、下がるときは HEAT_HYST ぶん余分に下がってから
# 段階を戻す（＝上げは即座、下げは慎重）。暑さの通知が遅れる方が危ないため。
HEAT_WARN = 26.0
HEAT_CRIT = 28.0
HEAT_HYST = 0.5
HEAT_LEVELS = ("normal", "warn", "crit")


def heat_level(t: float, prev: str = "normal") -> str:
    dn_warn, dn_crit = HEAT_WARN - HEAT_HYST, HEAT_CRIT - HEAT_HYST
    if prev == "crit":
        if t >= dn_crit:
            return "crit"
        return "warn" if t >= dn_warn else "normal"
    if prev == "warn":
        if t >= HEAT_CRIT:
            return "crit"
        return "warn" if t >= dn_warn else "normal"
    if t >= HEAT_CRIT:
        return "crit"
    return "warn" if t >= HEAT_WARN else "normal"


def staleness() -> dict:
    """記録が何時間止まっているか。通知の判定材料。

    一度も記録が無い場合は stale としない（センサー設置前に鳴っても意味がない）。
    """
    r = _rows("SELECT ts, temp_c, hum FROM climate_log ORDER BY ts DESC LIMIT 1")
    if not r:
        return {"known": False, "is_stale": False, "age_hours": None,
                "last_ts": None, "temp": None, "hum": None}
    ts_s, temp, hum = r[0]
    try:
        ts = datetime.fromisoformat(ts_s)
    except ValueError:
        return {"known": False, "is_stale": False, "age_hours": None,
                "last_ts": None, "temp": None, "hum": None}
    age = (datetime.now(JST).replace(tzinfo=None) - ts).total_seconds() / 3600.0
    return {"known": True, "is_stale": age >= STALE_HOURS, "age_hours": age,
            "last_ts": ts, "temp": round(temp, 1), "hum": int(round(hum))}
