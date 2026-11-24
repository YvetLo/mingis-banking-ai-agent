# Mingis — 中英雙語銀行 AI 客服 Agent

> **答不出來時，AI 把問題交給真人客服；真人客服的解法，經人工審核後，變成知識庫的新答案。**
>
> LangGraph · Claude · RAG（FAISS）· FastAPI · Streamlit　｜　Demo 專案：虛構的 Future銀行，所有客戶與帳務資料皆為模擬。

![Mingis 最終版架構](docs/assets/architecture-overview.png)

**English summary.** Mingis is a bilingual (Chinese/English) AI customer-service agent for a fictional bank, built with LangGraph, Claude, FAISS-based RAG, FastAPI and Streamlit. The focus is what happens when the AI should *not* answer: the retrieved text is checked before every reply, uncertain or high-risk cases (suspected fraud, disputes, card loss) go to a human agent with the full conversation, and the agent's resolutions are clustered into draft FAQs that a person must approve before they reach the knowledge base. All data is simulated; measurements are small samples and are reported with their limits in [`docs/evaluation.md`](docs/evaluation.md).

---

## 30 秒看懂

| 設計 | 具體做法與實測 |
|------|----------------|
| **有依據才回答** | 每次回答前，先由獨立的核實步驟判斷「檢索到的內容夠不夠回答」，不夠就轉真人客服，不硬答。實測發現：知識庫沒有答案時，模型仍會補一段看似合理的理由。在 12 題「知識庫確定沒有答案」的題目中，原本只有 5 題會轉真人客服，改成每次都核實後 12 題全部轉出。**代價**：首字約多等 3 秒，且答得出來的題目有較多被轉出（62 題中 3 → 11 題）。 |
| **規則在前、LLM 在後** | 進行中的流程、招呼語、籠統的帳單抱怨先用確定性規則處理，其餘才交給溫度為 0 的 LLM 分類器，同一句話永遠走同一條路。疑似盜刷標為緊急；掛失須驗證身分並由客戶確認。 |
| **人在關鍵點** | 真人客服接手時看得到完整對話，客戶不必重講。任何內容要進知識庫，都必須由人審核核准；核准後不需重啟就生效。 |
| **可驗證、可追溯** | 269 個自動化測試（含會呼叫真實 Claude 的評估與資安測試）、20 項技術決策紀錄（[ADR](docs/ADR.md)）、逐 Sprint 的[設計日誌](docs/design_journal.md)、LLM 呼叫成本與延遲追蹤。 |

> **關於測量的誠實說明**：上面的數字來自人工挑選的小樣本（62 題可回答題、12 題知識庫沒有答案的題目），是「漏洞已被補上」的方向性證據，**不是整體準確率**。檢索分數代表「找到相關內容」，不代表答對的比例。完整方法與限制見 [`docs/evaluation.md`](docs/evaluation.md)。

> **關於這個 repo**：這是公開用的整理後快照。完整的設計演進見 [`docs/design_journal.md`](docs/design_journal.md) 與 [`docs/ADR.md`](docs/ADR.md)；最終版架構見 [`docs/architecture.md`](docs/architecture.md)。

---

## 這個專案在展示什麼

多數 chatbot demo 停在「能回答 FAQ」。這個專案的重點在**答不出來的時候會發生什麼事**：

```
客戶提問
   │
   ├─ 知識庫答得好         → 直接回答（串流逐字輸出）
   ├─ 分數模糊             → 先讓 AI 核實 chunk 夠不夠 → 不夠就轉真人客服，不硬答
   └─ 盜刷/爭議/需核准…     → 依 9 條業務規則轉真人客服，各自獨立記錄
                                    │
                              真人客服實際回覆（雙向即時對話）
                                    │
                              客戶評分 1–5 分（低分追問原因）
                                    │
                        AI 聚類「未解決 + 低分 + 真人客服回覆」成待補主題
                                    │
                        生成 FAQ 草稿 → 客服審核 → 一鍵入庫 + 熱重建索引
                                    │
                        量化成效：同一題檢索信心 0.53 → 0.70（跨過門檻）
```

---

## 主要功能

| 功能 | 說明 |
|------|------|
| **FAQ 問答（RAG）** | FAISS 向量檢索 + Claude 生成，答案 grounding 在知識庫，附參考來源 |
| **常見問題快捷路徑** | 空白對話給起始捷徑，每次回答後依「實際檢索到的來源」給延伸追問;**只顯示驗證過答得出來的題目**，點下去不會變成轉真人客服的死路 |
| **Grounding Verifier** | 每則 FAQ 回答前，先獨立核實「這些 chunk 真的答得了嗎」，不夠就轉真人客服（量測：12 題真缺口全部攔下；環境變數 `VERIFY_ALWAYS=0` 可退回「只在分數偏低時核實」，見 ADR-020） |
| **帳務查詢** | 登入後用 tool-calling 查餘額/帳單/消費明細，只取問題真正需要的資料 |
| **信用卡掛失流程** | 三步驟身分驗證工作流程，中途可取消 |
| **轉真人客服** | 9 條業務觸發規則（盜刷/爭議/需核准/敏感資料變更/情緒激動/跨帳戶…）各自獨立分類 |
| **真人客服雙向對話** | 客服端與客戶端共用同一份對話串，兩邊每 5 秒自動更新，不需手動重整 |
| **招呼語直接回覆** | 「你好」「Hi」「謝謝」這類純招呼由 Router 規則直接回覆，不查知識庫、不轉真人客服（見 ADR-018） |
| **帳單問題先追問** | 客戶只說「帳單金額有問題」時，Mingis 先問「哪一筆有問題」，回覆後才轉真人客服，說明直接帶進工單（規則先於 LLM 分類器，見 ADR-017） |
| **訪客轉接前資料收集** | 未登入訪客要求真人客服時，先問客戶類別 + 問題描述，寫進工單讓專員直接接手 |
| **滿意度評分（CSAT）** | 1–5 分笑臉/哭臉，低分追問原因，Dashboard 統計 |
| **知識庫維護** | 網頁介面新增/編輯/封存知識，一鍵重建索引**熱抽換、不需重啟**，附檢索測試工具 |
| **知識優化流程** | LLM 聚類失敗訊號 → 生成去識別化 FAQ 草稿 → 客服審核入庫 → 檢索信心 before/after 量化成效 |
| **雙語** | 客戶對話依輸入語言自動偵測、各自獨立索引；整個平台介面（客戶端與四個後台頁）可用側邊欄切換「中文｜English」，語言記在網址 `?lang=` |

---

## 快速開始

### 1. 環境

```bash
git clone https://github.com/YvetLo/mingis-banking-ai-agent.git
cd mingis-banking-ai-agent
pip install -r requirements.txt

cp .env.example .env
# 編輯 .env，填入下列三類必填值（沒有預設值，缺少或仍是範例值時後端會拒絕啟動）：
#   ANTHROPIC_API_KEY                  你的 Claude API 金鑰
#   JWT_SECRET_KEY                     至少 32 字元，可用下面的指令產生
#   STAFF_USERNAME / STAFF_PASSWORD    客服人員後台的共用帳密
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. 建立向量索引（第一次執行）

```bash
python -m backend.src.rag.build_index
```
會下載嵌入模型 `paraphrase-multilingual-mpnet-base-v2`，把 `data/knowledge_base/` 的 markdown
切塊建成 FAISS 索引存到 `data/faiss_index/`。

### 3. 啟動（兩個終端機）

```bash
# 後端
uvicorn backend.main:app --reload

# 前端
streamlit run frontend/app.py
```

| 位址 | 用途 |
|------|------|
| http://localhost:8501 | 客戶端聊天介面 |
| http://localhost:8000/docs | 後端 API 文件（Swagger） |

### 4. 測試帳號

| 帳號 | 密碼 | 人設 |
|------|------|------|
| `demo_user1` | `demo1234` | 陳小明（一般上班族，2 張信用卡） |
| `demo_user2` | `demo5678` | 王大明（商務人士，無限卡） |
| `demo_user3` | `demo9999` | 陳春花（銀髮族，定存帳戶） |

---

## 四個介面

左側側邊欄可切換：

| 頁面 | 給誰用 | 做什麼 |
|------|--------|--------|
| **app**（首頁） | 客戶 | 聊天、登入查帳務、轉真人客服後的即時對話、結束後評分 |
| **📊 Dashboard** | 管理者 | 4 張 KPI（Tickets總數／待處理／已完成／未解決查詢）、服務單/未解決查詢統計、觸發原因分析、CSAT 與低分回饋；AI 呼叫成本與延遲收在最下方「開發者資訊」摺疊區塊；點「最近未解決查詢」或「最近服務單」任一列，開啟該案件的對話與完整記錄，待處理案件可直接回覆 |
| **🧑‍💼 客服人員介面** | 真人客服 | 上方對話、下方待處理案件列表（緊急優先、顯示等待時間、可篩選），點任一案件即切換並自動捲回對話；回覆客戶（自動更新）、標記已解決（需確認，可復原） |
| **📚 知識庫維護** | 知識維運 | 新增/編輯/封存補充知識（可搜尋的表格）、「N 筆變更尚未套用」提醒、重建索引即時生效、測試檢索分數 |
| **🧩 知識優化流程** | 知識維運 | 分析待優化知識、審核 AI 生成的 FAQ 草稿、追蹤入庫成效 |

---

## 架構

![Mingis 最終版架構](docs/assets/architecture-overview.png)

完整的架構文件（系統圖、LangGraph 流程、閉環時序圖、資料表、API、安全性、已知限制）見
[`docs/architecture.md`](docs/architecture.md)。簡化示意：

```
Streamlit 前端 ──HTTP──► FastAPI 後端 ──► LangGraph Agent
                                              │
                    ┌─────────────────────────┼──────────────────────┐
                    ▼                         ▼                      ▼
              Router Node              FAQ / Account /         Logger Node
          （Claude 意圖分類）         CardLoss / Handoff /      （記未解決）
                              HandoffIntake / BillClarify Node
                                              │
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                        FAISS + 嵌入      Mock 銀行 API      SQLite
                     （RAG 知識檢索）    （帳戶/卡片資料）  （工單/對話/評分/知識）
```

- **LLM**：`claude-haiku-4-5`；意圖分類、grounding 核實、缺口聚類、草稿生成一律用
  `tool_choice` 強制結構化輸出，不解析自由文字
- **RAG**：FAISS `IndexFlatIP` + 正規化向量（= cosine），Top-K 5，信心門檻 **0.60**；
  切塊以 markdown 標題（`##`/`###`）為邊界、每塊掛上標題路徑一起嵌入（見 ADR-016）
- **資料庫**：SQLite（`data/banking.db`）— `tickets` / `unresolved_queries` /
  `handoff_messages` / `satisfaction_ratings` / `kb_entries` / `kb_gap_drafts` /
  `llm_calls`（成本與延遲追蹤）/ `chat_sessions`

---

## 專案結構

```
mingis-banking-ai-agent/
├── backend/
│   ├── main.py                    FastAPI 應用與所有端點
│   └── src/
│       ├── agent/                 LangGraph：graph / nodes / state / intent /
│       │                          verifier / handoff / gap_pipeline / tools
│       ├── rag/                   build_index.py（建索引）、retriever.py（檢索）
│       ├── mock_api/              Mock 銀行 API 與假資料
│       ├── database.py            SQLite schema 與所有 CRUD
│       ├── prompts.py             System prompt 與回覆模板
│       ├── card_loss_workflow.py  掛失三步驟流程
│       └── nlp.py                 語言偵測、否定回饋判斷
├── frontend/
│   ├── app.py                     客戶端聊天介面
│   └── pages/                     Dashboard / 客服人員介面 / 知識庫維護 / 知識優化流程
├── data/
│   ├── knowledge_base/{zh,en}/    官方知識庫 markdown（各 9 檔）
│   ├── faiss_index/               向量索引（build_index 產出）
│   └── banking.db                 SQLite
├── docs/                          設計文件（見下）
└── tests/                         pytest，269 個測試
```

---

## 測試

```bash
python -m pytest -q          # 全部 269 個（含需呼叫 LLM 的 eval）
python -m pytest tests/test_handoff.py -q
```

測試會用獨立的 `test.db`（透過 `BANKING_DB_PATH`），不動到 `data/banking.db`。

**刻意不進 pytest 的部分**：LLM 不確定性高的路徑（缺口分析）與會覆寫真實索引的路徑
（reindex、草稿核准入庫），改用 curl / 瀏覽器 live 驗證 — 理由見 ADR-012 / ADR-013。

---

## 文件

| 文件 | 內容 |
|------|------|
| [docs/PRD.md](docs/PRD.md) | 產品需求：痛點、目標、範圍、驗收標準 |
| [docs/architecture.md](docs/architecture.md) | 系統架構與技術選型 |
| [docs/agent_design.md](docs/agent_design.md) | **Agent 設計**：State 規格、每個 Node 的職責與觸發條件、Sprint roadmap |
| [docs/conversation_design.md](docs/conversation_design.md) | 對話設計原則與話術 |
| [docs/user_flow.md](docs/user_flow.md) | 使用者流程 |
| [docs/design_journal.md](docs/design_journal.md) | **設計日誌**：每個 Sprint 的需求 → 決策 → 實作 → 反思 |
| [docs/ADR.md](docs/ADR.md) | **架構決策記錄**：每個重要取捨的背景、理由與 trade-off |
| [docs/prompt_engineering/](docs/prompt_engineering/) | 五份 prompt 設計文件 |

想快速理解「為什麼這樣做」，直接讀 `design_journal.md` 與 `ADR.md`。

---

## 已知限制（Demo 範圍）

- 單機單用戶：無 rate limiting、無快取、無水平擴展
- 對話即時更新用 5 秒輪詢，生產環境應改 WebSocket / SSE
- 工作流程狀態存在前端 session，重整會中斷（生產應存 Redis）
- Mock 銀行 API，不執行任何真實金融操作
- 密碼為明碼比對的假資料，僅供 demo 登入流程展示
