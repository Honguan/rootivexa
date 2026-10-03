# 驗證紀錄

日期：2026-10-03。Windows／Python 3.13.15。未使用付費模型推論。

| 檢查 | 結果 |
| --- | --- |
| `py -3 -m unittest discover -s tests -q` | 25 項通過 |
| `tests/probe_cli.py`，桌面版內附 Codex 0.160.0 | 9 組通過 |
| `tests/probe_cli.py`，npm Codex 0.159.2 | 9 組通過 |
| 真正全域目錄的安裝 dry-run | 通過，預覽 7 個檔案變更，未實際安裝 |

單元測試涵蓋 UTF-8／BOM／CRLF 還原、重複安裝、設定更新、既有原生角色與設定保留、手動修改保護、外部修改衝突、寫入失敗回復、中斷復原、三個並行名額限制、遞迴呼叫拒絕、逾時與記錄保存，以及真正 Windows `.cmd` 安裝／查詢／解除安裝流程。

每版 CLI 的 9 組整合測試為：4 個角色 × Fast 開／關，加上空白結果拒絕。各案例使用與角色相反的 Root service tier，驗證實際 HTTP 請求中的模型、effort、Fast、角色提示詞及中文任務文字；亦驗證結果保存、退出狀態和解除安裝後原設定未變。Fast 請求包含 `service_tier=priority`，Standard 請求省略該欄位。

真實全域 dry-run 比對 `AGENTS.md`、`config.toml`、`hooks.json`、`AGENTS.override.md` 的 SHA-256／存在狀態，以及工具安裝目錄的存在狀態，確認未改動。沒有在真實全域目錄執行安裝或解除安裝。

## 設計依據與限制

先前原生角色測試顯示 Codex 0.160.0 的角色模型與 effort 生效，但角色 Fast 仍繼承 Root；0.159.2 亦重現繼承。使用者明確選擇各角色獨立 CLI，因此最終不註冊原生角色。

測試證明 CLI 參數傳遞、執行器及安裝／復原流程。未驗證真實服務帳戶的模型與 Fast 資格、語義觸發準確率、任務品質、第三方外掛全部組合或實際費用；亦無法保證零額外 token 或所有讀取都被既有 Hook 攔截。

Windows CLI 後代程序曾短暫持有直接傳入的記錄檔 handle，造成整合測試清理失敗。改以 PIPE 接收 stdout／stderr，再由 runner 寫入記錄後，兩版全部案例通過，逾時測試亦確認記錄保存和名額釋放。
