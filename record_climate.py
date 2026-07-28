#!/usr/bin/env python
"""Govee の現在値を1回取って climate.db へ積み、止まっていれば Discord へ知らせる。

Govee の公開APIに履歴が無いので、グラフの元データはこの積み重ねしかない。
止まると穴が開くだけで復旧できないため、失敗はログに残す。

    */10 * * * * cd ~/apps/goma-climate-preview && .venv/bin/python record_climate.py

★停止検知がこのスクリプトの本題。乾電池駆動なので、電池が切れると
  「エラーも出ないまま監視が止まる」のが最悪の失敗モード。
  取得に失敗した回でも必ず停止判定まで走らせる（失敗こそが停止の原因なので）。
"""

import subprocess
import sys
import traceback
from datetime import datetime, timedelta

import climate_store

DISCORD = "/home/w00dst0ck/.local/bin/discord-notify"  # cron の PATH は最小なので絶対パス

STATE_KEY = "sensor_state"          # "ok" / "stale"
NOTIFIED_KEY = "stale_notified_at"  # 最後に停止を知らせた時刻

# 停止が続く間の再通知間隔。通知は状態遷移時のみが原則だが、電池切れは
# 「1通見落とすと永久に気づけない」性質なので、1日1回だけ念を押す。
REMIND_HOURS = 24


def notify(title: str, body: str, color: str) -> None:
    """fail-open。通知が飛ばなくても記録側は止めない。"""
    try:
        subprocess.run([DISCORD, "-t", title, "-c", color, body], timeout=30, check=False)
    except Exception as e:
        print(f"  discord-notify 失敗（記録は継続）: {e}", file=sys.stderr)


def check_stale() -> None:
    st = climate_store.staleness()
    if not st["known"]:
        # 一度も記録が無い＝設置前。ここで鳴らしても意味がない
        return

    prev = climate_store.get_meta(STATE_KEY, "ok")
    now = "stale" if st["is_stale"] else "ok"
    last_ts = st["last_ts"]
    age = st["age_hours"]

    if now == "stale":
        notified_at = climate_store.get_meta(NOTIFIED_KEY) or ""
        if prev != "stale":
            due = True                     # ok → stale の遷移。ここが本命
        elif not notified_at:
            due = True                     # 状態だけ stale で通知記録が無い（不整合の自己修復）
        else:
            try:
                due = (datetime.now(climate_store.JST).replace(tzinfo=None)
                       - datetime.fromisoformat(notified_at)) >= timedelta(hours=REMIND_HOURS)
            except ValueError:
                due = True

        if due:
            notify(
                "ごまモニター 室温センサーが止まっています",
                f"室温の記録が **{age:.1f}時間** 届いていません。\n"
                f"最後の記録: {last_ts.strftime('%-m月%-d日 %H:%M')} / {st['temp']}℃ {st['hum']}%\n"
                f"Govee H5179 は乾電池駆動です。電池切れか Wi-Fi 切断の可能性。",
                "red",
            )
            climate_store.set_meta(
                NOTIFIED_KEY,
                datetime.now(climate_store.JST).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds"),
            )
            print(f"  → 停止を通知（{age:.1f}h）")

    elif prev == "stale":
        notify(
            "ごまモニター 室温センサーが復帰しました",
            f"室温の記録が再開しました。\n現在 {st['temp']}℃ / 湿度 {st['hum']}%",
            "green",
        )
        climate_store.set_meta(NOTIFIED_KEY, "")
        print("  → 復帰を通知")

    climate_store.set_meta(STATE_KEY, now)


def main() -> int:
    stamp = datetime.now(climate_store.JST).strftime("%Y-%m-%d %H:%M:%S")
    rc = 0
    try:
        st = climate_store.record_once()
        print(f"{stamp} ok {st['temp_c']}℃ {st['hum']}% (raw={st['raw_temp']}, online={st['online']})")
    except Exception as e:
        print(f"{stamp} FAIL {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        rc = 1

    # 取得に失敗した回でも必ず通す。失敗が続くことこそが停止だから。
    try:
        check_stale()
    except Exception as e:
        print(f"{stamp} 停止判定に失敗: {e}", file=sys.stderr)

    return rc


if __name__ == "__main__":
    if "--test-notify" in sys.argv:
        # 閾値を跨いだときの文面を実際に飛ばして確かめる。
        # 環境変数ではなくモジュール属性を直接書き換える
        # （STALE_HOURS は import 時に読まれるので、ここで env を置いても遅い）。
        climate_store.STALE_HOURS = 0.0
    raise SystemExit(main())
