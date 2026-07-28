"""室温・湿度のダミー生成。行動ログは本番DBのスナップショットを使うので、ここは気候だけ。

日付から決定論的に作るので、リロードしても同じ値が出る（配置やUIを目で比較できる）。
Govee H5179 の実データが入ったら、このモジュールを差し替えるだけで済む。
"""

import hashlib
from datetime import date

# 室温ステータス（categorical パレット検証 5/5 PASS の4色に対応）
THRESHOLDS = [
    ("cold", None, 20.0, "寒い"),
    ("ok", 20.0, 26.0, "快適"),
    ("warn", 26.0, 28.0, "注意"),
    ("crit", 28.0, None, "危険"),
]
CRIT_TEMP = 28.0
STALE_HOURS = 3


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _rand(seed: int, lo: float, hi: float) -> float:
    return lo + (seed % 10_000) / 10_000 * (hi - lo)


def temp_status(t):
    if t is None:
        return ("stale", "データなし")
    for key, lo, hi, ja in THRESHOLDS:
        if (lo is None or t >= lo) and (hi is None or t < hi):
            return (key, ja)
    return ("crit", "危険")


def _profile(d: date):
    """その日の最高・最低・湿度ベース。暑い日と穏やかな日が混ざるように散らす。"""
    s = _seed("profile", d.isoformat())
    peak = _rand(s, 24.0, 32.0)
    trough = peak - _rand(s + 1, 3.5, 6.5)
    hum_base = _rand(s + 2, 52.0, 68.0)
    return peak, trough, hum_base


def series(d: date, upto_hour: int = 23):
    """[{hour, temp, hum, status, status_ja}] を 0時から upto_hour まで。"""
    peak, trough, hum_base = _profile(d)
    out = []
    for h in range(0, max(0, min(upto_hour, 23)) + 1):
        # 5時が最低・14時が最高の山なり
        if h <= 5:
            frac = (5 - h) / 5.0 * 0.18
        elif h <= 14:
            frac = (h - 5) / 9.0
        else:
            frac = max(0.0, 1.0 - (h - 14) / 9.5)
        frac = max(0.0, min(1.0, frac))
        t = round(trough + (peak - trough) * frac + _rand(_seed(d.isoformat(), h), -0.25, 0.25), 1)
        hum = int(round(hum_base + (t - trough) * 1.6 + _rand(_seed("h", d.isoformat(), h), -1.5, 1.5)))
        hum = max(35, min(92, hum))
        key, ja = temp_status(t)
        out.append({"hour": h, "temp": t, "hum": hum, "status": key, "status_ja": ja})
    return out


def summarize(rows, d=None):
    # d は実測側が生の記録から最高/最低を取るために使う。合成データは
    # 毎時値しか持たないので受け取るだけで無視する。
    if not rows:
        return None
    temps = [r["temp"] for r in rows]
    hums = [r["hum"] for r in rows]
    hot = [r for r in rows if r["temp"] >= CRIT_TEMP]
    return {
        "t_max": max(temps),
        "t_min": min(temps),
        "h_max": max(hums),
        "h_min": min(hums),
        "hot_hours": len(hot),
        "hot_range": (hot[0]["hour"], hot[-1]["hour"]) if hot else None,
    }


def day_max(d: date):
    """一覧用。その日の最高気温と状態。"""
    rows = series(d)
    t = max(r["temp"] for r in rows)
    key, ja = temp_status(t)
    return t, key, ja


def current(rows, stale: bool = False, stale_hours: int = 43):
    """室温カード/バッジ用の現在値。stale=True で電池切れを再現。"""
    if stale or not rows:
        return {
            "temp": None, "hum": None, "status": "stale", "status_ja": "データなし",
            "hour": None, "measured_at": "7月26日 04:12",
            "age_hours": stale_hours, "is_stale": True,
        }
    r = rows[-1]
    return {
        "temp": r["temp"], "hum": r["hum"], "status": r["status"], "status_ja": r["status_ja"],
        "hour": r["hour"], "measured_at": f"{r['hour']:02d}:00",
        "age_hours": 0, "is_stale": False,
    }
