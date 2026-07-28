"""室温連携プレビュー用のダミーデータ生成。

本番 DB には一切触らない。日付から決定論的に生成するので、
リロードしても同じ値が出る（A/B を目で比べられる）。
"""

import hashlib
from datetime import date, datetime, timedelta

LABEL_NAMES_JA = {
    "sleeping": "睡眠中",
    "sitting": "座っている",
    "watching": "見ている",
    "walking": "歩いている",
    "playing": "遊んでいる",
    "eating": "食べている",
    "drinking": "飲んでいる",
    "absent": "お出かけ中",
    "unknown": "不明",
}

EMOJI = {
    "sleeping": "😴", "sitting": "🐕", "watching": "👀", "walking": "🚶",
    "playing": "🎾", "eating": "🍚", "drinking": "💧", "absent": "🚪", "unknown": "❓",
}

DESCRIPTIONS = {
    "sleeping": ["ベッドで丸くなって寝ている。", "フローリングの上で横向きに伸びて寝ている。",
                 "タオルに顔をうずめて熟睡中。"],
    "sitting": ["床に伏せてこちらを見ている。", "床に伏せて口を開け、呼吸が速い。舌が長く出ている。",
                "カーペットの上でお座りしている。"],
    "watching": ["窓の外をじっと見ている。"],
    "walking": ["玄関の方へ歩いていく。見送りの体勢。", "部屋の中をゆっくり歩き回っている。"],
    "playing": ["おもちゃを咥えて振り回している。", "ボールを追いかけて走っている。"],
    "drinking": ["水皿に顔を突っ込んで飲んでいる。"],
    "absent": ["フレーム内にごまの姿が見当たらない。"],
}

# 室温ステータス（モックで validator 5/5 PASS させた4色に対応）
THRESHOLDS = [
    ("cold", None, 20.0, "寒い"),
    ("ok", 20.0, 26.0, "快適"),
    ("warn", 26.0, 28.0, "注意"),
    ("crit", 28.0, None, "危険"),
]

STALE_HOURS = 3


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _rand(seed: int, lo: float, hi: float) -> float:
    """seed から [lo, hi) の決定論的な値。"""
    return lo + (seed % 10_000) / 10_000 * (hi - lo)


def temp_status(t):
    """気温 → (key, 日本語ラベル)。None なら計測なし。"""
    if t is None:
        return ("stale", "データなし")
    for key, lo, hi, ja in THRESHOLDS:
        if (lo is None or t >= lo) and (hi is None or t < hi):
            return (key, ja)
    return ("crit", "危険")


def day_profile(d: date):
    """その日の気候プロファイル。暑い日・穏やかな日を決定論的に振り分ける。"""
    s = _seed("profile", d.isoformat())
    peak = _rand(s, 24.5, 32.0)
    trough = peak - _rand(s + 1, 4.0, 6.5)
    hum_base = _rand(s + 2, 55.0, 68.0)
    return peak, trough, hum_base


def climate_series(d: date, upto_hour: int = 23):
    """24時間ぶんの [{hour, temp, hum, status}]。"""
    peak, trough, hum_base = day_profile(d)
    out = []
    for h in range(0, min(upto_hour, 23) + 1):
        # 5時が最低、14時が最高になる山なりのカーブ
        phase = (h - 5) / 9.0
        if h < 5:
            frac = 1.0 - (5 - h) / 9.0 * 0.35
            frac = max(0.0, 1.0 - frac)
        elif h <= 14:
            frac = phase
        else:
            frac = max(0.0, 1.0 - (h - 14) / 9.5)
        frac = max(0.0, min(1.0, frac))
        jitter = _rand(_seed(d.isoformat(), h), -0.25, 0.25)
        t = round(trough + (peak - trough) * frac + jitter, 1)
        hum = round(hum_base + (t - trough) * 1.6 + _rand(_seed("h", d.isoformat(), h), -1.5, 1.5))
        hum = max(35, min(92, int(hum)))
        key, ja = temp_status(t)
        out.append({"hour": h, "temp": t, "hum": hum, "status": key, "status_ja": ja})
    return out


def activity_for(d: date, h: int) -> str:
    """時刻ごとの行動ラベル。夜は睡眠、日中は在宅/不在が混ざる。"""
    s = _seed("act", d.isoformat(), h)
    if h <= 6 or h >= 22:
        return "sleeping"
    if h == 7:
        return "sitting"
    if h == 8:
        return "walking"
    if 9 <= h <= 12:
        return "absent" if s % 3 else "sleeping"
    if 13 <= h <= 15:
        return "sitting"
    if 16 <= h <= 17:
        return "absent" if s % 2 else "sitting"
    if h == 18:
        return "walking"
    if h == 19:
        return "playing"
    return "sitting" if s % 4 else "drinking"


def _description(label: str, d: date, h: int, hot: bool) -> str:
    opts = DESCRIPTIONS.get(label) or ["様子を記録した。"]
    if hot and label == "sitting" and len(opts) > 1:
        return opts[1]  # 暑い日は「口を開けて呼吸が速い」を選ぶ
    return opts[_seed("desc", d.isoformat(), h) % len(opts)]


def timeline_for(d: date, now: datetime):
    """day ページ用のタイムライン。新しい順。"""
    clim = {c["hour"]: c for c in climate_series(d)}
    last_hour = now.hour if d == now.date() else 23
    rows = []
    for h in range(0, 24):
        c = clim[h]
        if d == now.date() and h > last_hour:
            rows.append({"type": "future", "hour": h, "climate": None})
            continue
        s = _seed("row", d.isoformat(), h)
        if s % 37 == 0:
            rows.append({"type": "gap", "hour": h, "climate": c})
            continue
        label = activity_for(d, h)
        present = label != "absent"
        rows.append({
            "type": "log",
            "id": int(d.strftime("%Y%m%d")) * 100 + h,
            "hour": h,
            "media_path": f"{d.isoformat()}/{h:02d}.jpg",
            "dog_present": present,
            "activity_label": label,
            "activity_label_ja": LABEL_NAMES_JA[label],
            "description": _description(label, d, h, c["temp"] >= 28),
            "confidence": round(_rand(s, 0.72, 0.98), 2),
            "decided_by": ["flash", "flash", "flash", "pro", "opus_override"][s % 5],
            "vote_total": 3,
            "vote_agree": 3 if s % 4 else 2,
            "emoji": EMOJI[label],
            "climate": c,
        })
    rows.reverse()
    return rows


def summary_for(d: date, timeline):
    logs = [r for r in timeline if r["type"] == "log"]
    counts = {}
    for r in logs:
        counts[r["activity_label"]] = counts.get(r["activity_label"], 0) + 1
    ordered = dict(sorted(counts.items(), key=lambda kv: -kv[1]))
    clim = climate_series(d)
    temps = [c["temp"] for c in clim]
    hot_hours = [c for c in clim if c["temp"] >= 28]
    return {
        "label_counts": {k: (v, LABEL_NAMES_JA[k]) for k, v in ordered.items()},
        "hours_present": sum(1 for r in logs if r["dog_present"]),
        "snapshot_count": len(logs),
        "gap_count": sum(1 for r in timeline if r["type"] == "gap"),
        "t_max": max(temps),
        "t_min": min(temps),
        "hot_hours": len(hot_hours),
        "hot_range": (hot_hours[0]["hour"], hot_hours[-1]["hour"]) if hot_hours else None,
    }


def days_index(now: datetime, span: int = 30):
    out = []
    for i in range(span):
        d = (now - timedelta(days=i)).date()
        tl = timeline_for(d, now)
        sm = summary_for(d, tl)
        top = [
            {"label": k, "label_ja": v[1], "count": v[0]}
            for k, v in sm["label_counts"].items()
        ]
        status, status_ja = temp_status(sm["t_max"])
        out.append({
            "date": d.isoformat(),
            "latest_media_path": f"{d.isoformat()}/23.jpg",
            "label_counts": top,
            "t_max": sm["t_max"],
            "t_status": status,
            "t_status_ja": status_ja,
        })
    return out


def current_climate(now: datetime, stale: bool = False):
    """今の室温。stale=True で電池切れシナリオを再現する。"""
    if stale:
        last = now - timedelta(hours=43)
        return {
            "temp": None, "hum": None, "status": "stale", "status_ja": "データなし",
            "hour": last.hour, "measured_at": last.strftime("%-m月%-d日 %H:%M"),
            "age_hours": 43, "is_stale": True,
        }
    series = climate_series(now.date(), now.hour)
    c = series[-1]
    return {
        "temp": c["temp"], "hum": c["hum"], "status": c["status"], "status_ja": c["status_ja"],
        "hour": c["hour"], "measured_at": f"{c['hour']:02d}:00",
        "age_hours": 0, "is_stale": False,
    }
