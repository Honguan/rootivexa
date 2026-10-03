# Codex 全域角色安裝器

Windows 一鍵安裝／解除安裝四種角色。各角色透過獨立 Codex CLI 程序執行，可分別設定模型、推理強度及 Fast。只用 Python 標準函式庫，不新增 Hook、MCP 或 Skill。

## 預設角色

| 角色 | 模型 | 推理強度 | Fast | 分工 |
| --- | --- | --- | --- | --- |
| explorer | gpt-6-luna | xhigh | 關 | 跨檔案探索，回報證據 |
| researcher | gpt-6-luna | xhigh | 關 | 文件查詢，附來源與版本 |
| worker | gpt-6.1-sol | high | 關 | 指定範圍的實作與驗證 |
| architect | gpt-6-astra | medium | 關 | 高影響方案與重大修改審查 |

Root 沒有模型或推理強度限制，只須能執行本機命令。本機原有 Root 設定保持不變。所有角色合計最多同時執行 **3 個程序**；可同時有 3 個 Luna，並非每個角色各有 3 個名額。

## 一鍵操作

先備條件：Windows、Python 3.11 以上（`py -3 --version`），以及已可登入使用的官方 Codex CLI。已驗證 CLI 0.159.2 與 0.160.0；其他版本須重新驗證。

1. 解壓整個安裝包。
2. 雙擊 **install.cmd**。完成後開啟新的 Codex 對話。
3. 雙擊 **configure.cmd** 修改 `settings.json`，儲存後再次執行 **install.cmd** 套用。
4. **status.cmd** 查看設定；**uninstall.cmd** 解除安裝。

安裝器不下載 Python 或 Codex，也不變更登入資訊。若無法自動找到 CLI，可在啟動安裝器及 Codex 的環境中，將 `CODEX_ORCHESTRATION_CODEX` 設為官方 `codex.exe` 完整路徑。執行角色時也可提供 `--codex`。

只預覽、不寫入：

```powershell
py -3 manage.py install --dry-run
py -3 manage.py uninstall --dry-run
```

只有全域安裝模式。預設位置為 `%USERPROFILE%\.codex`；若已設定絕對路徑的 `CODEX_HOME`，使用該全域目錄。沒有專案安裝選項。

## 安裝結構

```text
%USERPROFILE%\.codex\
├─ AGENTS.md                         # 追加有起訖標記的簡短分工規則
└─ codex-orchestration\
   ├─ runner.py                      # 獨立 CLI 執行器
   ├─ agents\
   │  ├─ explorer.toml
   │  ├─ researcher.toml
   │  ├─ worker.toml
   │  └─ architect.toml
   ├─ manifest.json                  # 安裝紀錄、管理範圍、雜湊
   ├─ lock
   ├─ slots\                         # 全域共用 3 個執行名額
   ├─ backups\*.json                 # 安裝／更新／解除安裝快照
   └─ runs\時間-識別碼\
      ├─ result.md                   # 角色最後回覆
      ├─ events.jsonl                # CLI 事件
      ├─ stderr.log
      └─ status.json
```

不寫入 `config.toml` 或原生 `agents\` 目錄，不覆蓋原生同名角色。原有 Token Optimizer、Ponytail、Hook、MCP 與 Root 設定均保留。

## 手動設定

`settings.json` 每個角色都包含三個欄位，例如：

```json
"worker": {"model": "gpt-6.1-sol", "effort": "high", "fast": true}
```

`fast: true` 使用 Fast；`false` 明確使用 Standard，不繼承 Root 的 Fast。模型名稱及 effort 必須由帳戶／CLI 實際支援；安裝器檢查格式，不以付費請求驗證模型資格。執行失敗不會自動更換模型。

可修改 `prompts/` 內的角色提示詞再安裝。也可直接修改已安裝的角色 TOML，下一個角色程序就會採用；但安裝器更新時會停下保留手動修改。建議將變更同步回安裝包，再解除安裝後重新安裝；解除安裝會備份手動修改。

## 呼叫與分工

短小任務由 Root 處理；可獨立交付的探索、研究與實作才委派。Architect 用於高影響方案、同一問題修復失敗兩次，以及重大跨模組修改完成前。已有結果則重用，避免重複探索或審查。

Root 準備 UTF-8 任務檔，包含問題、必要證據、授權範圍、檔案所有權、驗收條件及回覆語言。角色不繼承目前聊天記錄：

```powershell
py -3 "$env:USERPROFILE\.codex\codex-orchestration\runner.py" explorer --cwd "C:\work\project" --task-file "C:\work\brief.txt"
```

若使用自訂 `CODEX_HOME`，替換上述 runner 路徑。Root 的安裝規則會自動帶入實際路徑。執行器回傳結果檔案路徑，Root 讀取結果後整合；結果不會以桌面版原生子代理出現。

- Explorer、Researcher、Architect 使用 CLI 的 `read-only` sandbox；Worker 使用 `workspace-write`。均為非互動執行，`approval_policy=never`。
- 子程序載入該全域目錄及工作目錄的適用設定／指示。Root 在桌面對話內取得的臨時權限、工具或訊息不會自動轉交；CLI 無法取得的工具會造成任務限制。
- Runner 停用該程序的原生 agents，並禁止自身遞迴呼叫。Worker 不負責 staging、commit 或遠端寫入，由 Root 按使用者授權處理。
- 3 個名額滿時由本機程序等待，不反覆呼叫模型。預設逾時 1800 秒，包含排隊，可用 `--timeout` 修改。逾時終止執行中的 CLI 程序樹。
- 安裝／更新／解除安裝期間持有同一組鎖；有角色執行中時拒絕更新，以免刪除工作中的檔案。

## 解除安裝與復原

解除安裝移除四個私有角色、runner、manifest 及自己的 AGENTS 分工區塊。若 AGENTS 其餘內容未變，還原原始位元組；外部新增的規則保留。結果、快照與鎖檔保留，可自行另存後刪除。

每次實際變更先建立備份。備份 JSON 中 `before`／`after` 為 Base64 原始內容，`null` 代表不存在。僅備份本工具管理的檔案，不複製認證或主設定。

中途失敗會回復；程序意外中斷由 `pending.json` 記錄，下次安裝／解除安裝先復原。偵測到外部修改時停止，保留檔案和快照。重複安裝相同設定不重寫檔案。有效的全域 `AGENTS.override.md`、管理檔案衝突或規則超過載入容量時會停止，不覆蓋。

## 能保證與不能保證的範圍

**獨立 Fast 的參數路由已驗證。** 原生子代理在本機測試中繼承 Root 的 service tier，因此依使用者選擇改用獨立 CLI。全域設定與既有原生角色的保留、回復及解除安裝都有測試。

提示詞能明確分工，但無法保證每次自動選對角色，也不保證 `large_read_guard` 攔截所有讀取路徑。此工具不增加攔截 Hook。需要確定使用某角色時，可明確要求 Root 使用該角色執行器。

不能承諾零額外 token：全域分工規則、各程序的必要上下文與回覆仍耗用 token；Fast 也可能增加用量。獨立程序還會啟動自己的 CLI／MCP／Hook，可能增加時間及本機資源。保留設定不等於所有第三方外掛組合皆已實測。

此設計符合「全域、可移除、各角色獨立 Fast」需求；若重視原生子代理 UI 與完整聊天繼承，則存在取捨。

## 驗證

```powershell
py -3 -m unittest discover -s tests -v
py -3 tests/probe_cli.py "完整路徑\codex.exe"
```

測試使用暫存全域目錄；整合測試使用真正 CLI 搭配本機回送 HTTP 模型替身，檢查實際送出的模型、effort、Fast，以及結果保存與解除安裝。不使用付費推論，不能證明帳戶資格、真實模型品質或實際費率。測試結果見 `VALIDATION.md`。

官方依據（2026-10-03 查閱）：[Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)、[Speed](https://learn.chatgpt.com/docs/agent-configuration/speed)、[Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)。
