#!/usr/bin/env python
"""Govee の現在値を1回取って climate.db へ積む。cron から10分おきに叩く。

Govee の公開APIに履歴が無いので、グラフの元データはこの積み重ねしかない。
止まると穴が開くだけで復旧できないため、失敗はログに残す。

    */10 * * * * cd ~/apps/goma-climate-preview && .venv/bin/python record_climate.py
"""

import sys
import traceback
from datetime import datetime

import climate_store


def main() -> int:
    stamp = datetime.now(climate_store.JST).strftime("%Y-%m-%d %H:%M:%S")
    try:
        st = climate_store.record_once()
    except Exception as e:
        print(f"{stamp} FAIL {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
    print(f"{stamp} ok {st['temp_c']}℃ {st['hum']}% (raw={st['raw_temp']}, online={st['online']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
