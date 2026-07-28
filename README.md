# goma-climate-preview

ごまモニターに室温・湿度を統合した場合の **UI プレビュー環境**。ダミーデータで動く。

**本番（`~/apps/goma-monitor` / port 3003）とは完全に独立**。DB・Ring・Gemini・API キーのいずれにも触らない。

- URL: `https://ujt7qflvfr.goma-monitor.com/goma-preview/`
- PM2 名: `goma-climate-preview` / ポート: **3000**
- センサー停止（電池切れ）の再現: URL に `?sensor=stale`

## 構成

| ファイル | 役割 |
|---|---|
| `main.py` | FastAPI。`/`（トップ）と `/day/{date}`（日別詳細）。`NOW` を 2026-07-28 23:00 に固定 |
| `dummy.py` | 決定論的なダミーデータ生成。日付から算出するのでリロードしても値が変わらない |
| `patch_templates.py` | **本番テンプレートに入れるべき差分そのもの**。アンカー方式で、一致しなければ即失敗する |
| `templates/` | `~/apps/goma-monitor/web/templates` の 2026-07-28 時点のコピー + 上記パッチ適用済み |

## 本番への移植

`patch_templates.py` の各 `patch(...)` が、本番テンプレートに対して行う挿入と 1:1 対応している。
本番側で必要になるのはこの3つ:

1. **テンプレート** — `patch_templates.py` を本番の `web/templates` に対して実行（`base` 変数の置換分だけは不要。本番はサブパス配信ではないため）
2. **router** — `index_v2.html` / `day_v2.html` のコンテキストに `climate` / `climate_series` / `climate_summary` を追加、`days` の各要素に `t_max` / `t_status` を追加、`timeline` の各エントリに `climate` を追加
3. **データ** — `dummy.py` を Govee H5179 の実データ取得に差し替え（`~/apps/goma-monitor/tools/govee_probe.py` が疎通確認済み）

## 室温ステータス

| 状態 | 範囲 | 色 |
|---|---|---|
| 寒い | < 20℃ | `#2f6fb0` |
| 快適 | 20–26℃ | `#2b9873` |
| 注意 | 26–28℃ | `#c67610` |
| 危険 | 28℃ ≦ | `#a82815` |
| データなし | 3時間以上 更新なし | グレー |

4色は categorical パレット検証（明度帯・彩度下限・色覚特性の分離・通常視の分離・コントラスト）を **5/5 PASS** している。
閾値は一般的な室内犬の目安。実測を貯めてから、ごまの実際のパンティング開始温度に合わせて詰める。

## 運用

```bash
pm2 restart goma-climate-preview && pm2 save
pm2 logs goma-climate-preview
```

不要になったら `pm2 delete goma-climate-preview && pm2 save` と nginx の `/goma-preview/` location 削除で撤去できる。
