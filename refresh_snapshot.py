"""本番DBのスナップショットを取り直す。

プレビューは本番 router をそのまま import して動くので、行動ログ・タイムライン・
30日一覧は全て data/goma.db（＝このスナップショット）から出る。取り直さないと
写真も日付も止まったままになる（室温だけは climate.db に独立して溜まるので、
「室温は今日の値なのに29日のページが無い」というズレ方をする）。

本番へは read-only で接続し、sqlite3.backup() で複製する。書き込みは一切しない。

    .venv/bin/python refresh_snapshot.py
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROD_DB = Path("/home/w00dst0ck/apps/goma-monitor/data/goma.db")
SNAP_DB = APP_DIR / "data" / "goma.db"


def latest(db: sqlite3.Connection) -> str:
    row = db.execute("SELECT COUNT(*), MAX(timestamp) FROM behavior_logs").fetchone()
    return f"{row[0]}件 / 最新 {row[1]}"


def main() -> int:
    if not PROD_DB.is_file():
        print(f"本番DBが無い: {PROD_DB}", file=sys.stderr)
        return 1

    # mode=ro を明示する。ここが書き込み可能だと、プレビュー由来の操作で
    # 本番を壊しうる（プレビュー上の「見直す」は DB を書き換える）。
    src = sqlite3.connect(f"file:{PROD_DB}?mode=ro", uri=True)
    before = latest(sqlite3.connect(f"file:{SNAP_DB}?mode=ro", uri=True)) if SNAP_DB.is_file() else "なし"

    dst = sqlite3.connect(SNAP_DB)
    src.backup(dst)
    dst.close()

    after = latest(sqlite3.connect(f"file:{SNAP_DB}?mode=ro", uri=True))
    src.close()

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} スナップショット更新")
    print(f"  前: {before}")
    print(f"  後: {after}")

    # 本番DBの mtime が変わっていないこと（＝書き込んでいないこと）は
    # 呼び出し側で確認する。ここで触れると自分で壊した場合に気づけない。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
