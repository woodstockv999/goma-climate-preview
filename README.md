# goma-climate-preview

ごまモニターに室温・湿度を統合した場合の **UI プレビュー環境**。

- URL: `https://ujt7qflvfr.goma-monitor.com/goma-preview/?key=fb8082e094b1c7bc402b0d84e5942e72`
- PM2 名: `goma-climate-preview` / ポート **3000**
- センサー停止（電池切れ）の再現: URL に `?sensor=stale`

## 本番と UI が完全一致する仕組み

集計ロジックを再実装するとズレるので、**本番の `web/router.py` をそのまま import して使う**。
行動サマリー・タイムライン・24hストリップ・30日一覧・日記は本番と同一の出力になる
（実測で 24hストリップ24件・30日一覧・行動ピル109件・凡例・説明文まで完全一致を確認）。

```
sys.path に ~/apps/goma-monitor を追加
  → DATA_DIR をこのアプリの data/ に向けてから import（順序が重要）
  → prod_router.templates を ClimateTemplates に差し替え
  → 描画直前に室温 context を注入
```

差分は室温 UI と上部のプレビューバーだけ。

## 本番に触れない担保

| 対象 | 扱い |
|---|---|
| DB | `data/goma.db` は `sqlite3.backup()` によるスナップショット。`DATA_DIR` を先に差し替えるので接続先はここ。**起動時に assert で確認** |
| 写真 | 複製せず（242MB）、専用ルートが本番 `data/` を **読み取り専用**で参照。トラバーサルは 501 で遮断 |
| Gemini | `/api/reanalyze` を本番 router より先に登録して 501。API を消費しない |
| Ring | `/snapshot` も同様に 501 |
| 本番プロセス | 一切再起動しない |

プレビュー上の「見直す」はスナップショットDBを書き換えるので、自由に触ってよい。

## 構成

| ファイル | 役割 |
|---|---|
| `main.py` | 本番 router の取り込み・室温注入・外部経路の遮断・画像ルート |
| `dummy.py` | 室温と湿度だけを日付から決定論的に生成。行動ログは本番DB由来 |
| `patch_templates.py` | **本番テンプレートに入れるべき差分そのもの**。アンカー方式で、一致数が想定と違えば即 exit |
| `templates/` | 本番 `web/templates` のコピー + 上記パッチ適用済み |

テンプレートを作り直すときは、本番から再コピーして `python3 patch_templates.py` を流す。

## UI 配置

- **トップ** — 写真オーバーレイ右端に室温バッジ／24h行動ストリップの真下に**同じ時間軸**のスパークライン（縦に見れば暑い時間帯の行動が読める）／30日一覧は最高室温のみ
- **日別詳細** — グラフ2枚のみ。℃ と % はスケールが違うので1枚に2軸を立てない。センサー停止時だけ1行の注意書き
- **タイムライン** — muted テキスト＋異常時だけ5pxドット。快適域では色が乗らない

## 室温ステータス

| 状態 | 範囲 | 色 |
|---|---|---|
| 寒い | < 20℃ | `#2f6fb0` |
| 快適 | 20–26℃ | `#2b9873` |
| 注意 | 26–28℃ | `#c67610` |
| 危険 | 28℃ ≦ | `#a82815` |

4色は categorical パレット検証 5/5 PASS。閾値は一般的な室内犬の目安で、実測後にごまに合わせて詰める。

## 本番への移植

1. **テンプレート** — `patch_templates.py` を本番 `web/templates` に対して実行（`{{ base }}` 置換分は不要）
2. **router.py** — context に `climate` / `climate_series` / `climate_summary`、`days[]` に `t_max`/`t_status`、`timeline[]` に `climate` を追加（`main.py` の `ClimateTemplates._inject` がそのまま雛形）
3. **データ** — `dummy.py` を Govee H5179 の実データ取得に差し替え

## 撤去

```bash
pm2 delete goma-climate-preview && pm2 save
# nginx の /goma-preview/ 2ブロックを削除 → nginx -t → reload
# バックアップ: /etc/nginx/backups/ujt7qflvfr.bak-20260728-095024
rm -rf ~/apps/goma-climate-preview
```
