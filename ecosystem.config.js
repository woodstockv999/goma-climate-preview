// goma-climate-preview — 室温連携のプレビュー環境（ダミーデータ）
// venv の console script は shebang が壊れやすいので、venv python の -m で起動する
// （goma-monitor のコールドスタート事故と同じ轍を踏まないため）。
module.exports = {
  apps: [
    {
      name: "goma-climate-preview",
      script: "/home/w00dst0ck/apps/goma-climate-preview/.venv/bin/python",
      args: "-m uvicorn main:app --host 127.0.0.1 --port 3000",
      cwd: "/home/w00dst0ck/apps/goma-climate-preview",
      interpreter: "none",
      env: { BASE_PATH: "/goma-preview" },
      max_memory_restart: "180M",
      out_file: "/home/w00dst0ck/logs/goma-climate-preview-out.log",
      error_file: "/home/w00dst0ck/logs/goma-climate-preview-error.log",
    },
  ],
};
