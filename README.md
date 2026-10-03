# Codex 全域原生角色安裝器

開源套件 **1.0.1**，採 [MIT License](LICENSE)。本專案為社群工具，與 OpenAI 無隸屬關係。

Windows 一鍵安裝／解除安裝四種原生子代理。可個別設定模型與推理強度；**Fast 統一跟隨 Root**。不需要獨立 CLI 執行器，不新增 Hook、MCP 或 Skill。

## 預設角色

| 角色 | 模型 | 推理強度 | 分工 |
| --- | --- | --- | --- |
| explorer | gpt-6-luna | xhigh | 跨檔案探索與證據整理 |
| researcher | gpt-6-luna | xhigh | 文件查詢，附來源與版本 |
| worker | gpt-6.1-sol | high | 指定範圍的實作與驗證 |
| architect | gpt-6-astra | medium | 高影響方案與重大修改審查 |

Root 可使用任何具備原生子代理工具的模型。本工具保留既有 Root 模型、Fast、權限及並行設定。

## 一鍵操作

先備條件：Python 3.11 以上（`py -3 --version`），以及支援原生自訂角色的 Codex。測試版本為 Codex 0.159.2／0.160.0。

1. 解壓整個安裝包，雙擊 **install.cmd**。
2. 完成後開啟新的 Codex 對話，載入四個原生角色及分工規則。
3. **configure.cmd** 編輯 `settings.json`；儲存後再次執行 **install.cmd** 套用。
4. **status.cmd** 查看設定；**uninstall.cmd** 解除安裝。

安裝器不下載套件、不修改登入資訊。安裝只需 Python；角色執行由現有 Codex 的原生工具負責。

模型預設是可編輯的範例，請依帳戶與宿主支援範圍修改 `settings.json`，再執行安裝。使用角色不需要 Token Optimizer、Ponytail 或其他外掛；有既有最佳化工具時才使用。

只預覽、不寫入：

```powershell
py -3 manage.py install --dry-run
py -3 manage.py uninstall --dry-run
```

只有全域模式。預設為 `%USERPROFILE%\.codex`；若已設定絕對路徑的 `CODEX_HOME`，使用該全域目錄。沒有專案安裝選項。

## 安裝結構

```text
%USERPROFILE%\.codex\
├─ AGENTS.md                         # 追加有起訖標記的簡短分工規則
├─ agents\
│  ├─ explorer.toml
│  ├─ researcher.toml
│  ├─ worker.toml
│  └─ architect.toml
└─ codex-orchestration\
   ├─ manifest.json                  # 安裝紀錄、管理範圍與雜湊
   ├─ lock                           # 安裝／更新／移除操作鎖
   └─ backups\*.json                 # 修改前快照
```

安裝只寫四個角色、AGENTS 規則及安裝紀錄；不修改 `config.toml`。既有 Token Optimizer、Ponytail、Hook、MCP 與其他角色檔案保持不變。

同名的內建 Explorer／Worker 會採用這次安裝的自訂角色設定；若已有同名的使用者角色（含不同檔名或 `config.toml` 宣告），安裝器會停止，避免覆蓋。

## 手動設定

`settings.json` 每個角色僅包含：

```json
"worker": {"model": "gpt-6.1-sol", "effort": "high"}
```

已移除 `fast` 欄位；生成的角色 TOML 不含 `service_tier`。Fast 使用 Root 的既有設定。模型與 effort 仍須由帳戶及執行環境支援，安裝器不以付費請求驗證資格。

可修改 `prompts/` 內的角色提示詞再安裝，也可直接修改已安裝 TOML。直接修改後，安裝器更新會停止，保留手動變更；建議將修改同步回安裝包，再解除安裝後重新安裝。解除安裝會備份修改。

## 分工方式

派工前比較目前 Root 與目標角色實際使用的模型 ID。**模型完全相同時，預設由 Root 直接完成角色工作**，遵守該角色的任務限制與檢查方法；角色名稱或推理強度不同，本身不構成另開代理的理由，也不代表 Root 已切換推理強度。只有使用者明確要求獨立代理，或任務需要並行、隔離上下文、獨立審查、無法在本地滿足的角色設定時，才另開同模型子代理並說明原因。模型未知時不猜測，不自行認定別名相同。

需要委派時，Root 透過原生子代理工具選擇角色；有 `agent_type` 參數時指定角色名稱。短小任務由 Root 處理，可獨立交付的探索、研究及實作才委派。Architect 檢查用於高影響方案、同一問題修復失敗兩次，以及重大跨模組修改完成前；模型相同且適用直接處理時由 Root 自查，明確標示為自查，不能宣稱獨立審查。已有證據則重用。

每次派工指定問題、必要證據、授權範圍、檔案所有權、驗收條件及回覆語言。偏好精簡任務說明，避免不必要的完整聊天複製。Worker 不負責 staging、commit 或遠端寫入，由 Root 依使用者授權處理。

Luna Explorer 在自己的範圍內使用既有最佳化工具，每批並行最多 4 個互不依賴的讀取／搜尋，逐一檢查結果。有前後依賴的讀取、編輯及後續判斷仍依序執行。較大的獨立區域調查可由 Root 同時派給多個 Luna Explorer，共用原有最多 3 個子代理的規則；各自分區並回傳精簡證據，Root 不重複讀取。這是提示詞規則；實際加速取決於工具並行支援，尚未做速度或 token 節省基準測試。

- 分工規則建議每個 Root 同時最多 3 個子代理；這是提示詞規則，**並非本工具強制限制**。實際上限由既有原生設定及宿主可用名額決定。
- 角色使用原生的等待、回報與生命週期管理；移除獨立 runner、slots 與 runs 目錄設計。
- 權限依原生繼承機制及目前工作環境決定。探索／研究／審查角色的提示詞要求不修改檔案，但這不是額外的 sandbox 保證。
- 子代理預設不再委派。角色或模型不可用時應回報限制，不宣稱已完成未執行的審查。

## 保留環境與解除安裝

每次變更先備份，重複安裝相同設定不重寫檔案。解除安裝移除四個管理角色、manifest 及自己的 AGENTS 分工區塊；原始內容未被其他人修改時按原始位元組還原，外部新增規則會保留。備份、鎖檔及空目錄保留。

備份 JSON 的 `before`／`after` 是 Base64 原始內容，`null` 表示原本不存在。僅備份本工具管理的檔案，不複製認證或主設定。

寫入失敗會回復；意外中斷由 `pending.json` 記錄，下次操作先復原。若檔案另有外部修改，停止並保留現況與快照。有效的全域 `AGENTS.override.md`、`agents.enabled=false`、同名角色衝突或規則超出載入容量都會停止安裝，不自行改動原設定。

更新或解除安裝前請結束舊子代理，完成後開啟新對話；安裝鎖只協調安裝器，不追蹤原生代理。若曾安裝舊版獨立 CLI 方案，先用原安裝包解除安裝；新版不自動改寫舊版安裝紀錄。

更新原生角色版：將自訂 `settings.json` 與角色提示詞合併至新版安裝包，再執行 `install.cmd`。請保留新版 `prompts/routing.md` 的派工規則，避免用整個舊 `prompts/` 覆蓋新版邏輯。套件版本與 manifest schema 不同；本版維持 schema 2。

## 建立開源發佈包

```powershell
py -3 -m unittest discover -s tests -q
py -3 build_release.py
Get-FileHash dist/codex-orchestration-1.0.1.zip -Algorithm SHA256
Get-Content dist/codex-orchestration-1.0.1.zip.sha256
```

輸出包含 ZIP 與同名 `.zip.sha256`；核對兩者的雜湊值後即可分享。ZIP 使用明列的 20 個檔案，包含完整原始碼、MIT 授權、文件及測試。固定 ZIP 時間與權限，相同來源在相同 Python／zlib 環境可產生相同位元組。

打包不讀取全域 Codex 目錄，不包含登入資訊、安裝備份、聊天記錄、`.git`、快取或本機最佳化資料。`dist/` 是生成檔案，不提交到 Git。修改或回報問題時，請附 Python／Codex 版本、重現步驟與測試結果，勿附認證資料。發佈紀錄見 [CHANGELOG.md](CHANGELOG.md)。

## 限制與驗證

自動選用角色是提示詞行為，不能保證每次正確觸發。專案角色／設定、更高優先級指示、帳戶權限與原生名額可能影響結果。全域安裝檢查不掃描所有專案。

本工具不增加讀取攔截 Hook，不能保證 `large_read_guard` 攔截所有路徑，也不能承諾零額外 token；分工規則、角色上下文及回覆仍耗用 token。

```powershell
py -3 -m unittest discover -s tests -v
py -3 tests/probe_native.py "完整路徑\codex.exe"
```

測試使用暫存全域目錄。整合測試由本機 HTTP 模型替身驅動真正的原生派工，驗證角色模型、effort、Fast 跟隨 Root 及中文任務內容，不使用付費模型推論。測試結果見 `VALIDATION.md`；不代表真實帳戶資格、語義觸發率或模型品質已驗證。

角色格式與原生管理依據：[OpenAI Docs — Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)（2026-10-03 查閱）。
