# 設計決策日誌 Design Decision Journal
# AI Banking Customer Assistant

**說明**：這份日誌記錄整個專案的思考過程，從需求發現到最終反思，
按照四個維度循環記錄每個 Phase 和 Sprint 的決策歷程。

與 `ADR.md` 的區別：
- **ADR.md** → 記錄技術選型的正式決策（What & Why，結構化）
- **Design Journal** → 記錄人的思考過程（How I thought, What I learned，敘述性）

---

## 格式說明

每個 Phase / Sprint 包含四個區塊：

> **① Requirement & Discovery** — 為什麼做、解決什麼問題、目標使用者是誰
> **② Design Decision** — 遇到哪些選擇、有哪些方案、最後為什麼這樣決定
> **③ Implementation & Iteration** — 實作後遇到什麼問題、如何修改
> **④ Evaluation & Reflection** — 測試結果如何、哪些地方有效、哪些地方下一版需要改善

---
---

# Phase 1：Product Discovery

## ① Requirement & Discovery

**為什麼做這個專案？**
我需要一個具體的 AI 作品集，來展示實作能力。銀行客服是很好的選題，因為它涵蓋了 AI 工程最常見的三種模式：知識庫查詢（RAG）、API 整合、多步驟工作流程（Workflow），一個專案就能展示多種能力。

**解決什麼問題？**
銀行客服中心每日處理大量重複性查詢，造成等待時間長、人力成本高。AI 助理可以自動處理標準問題，讓真人客服專注於複雜案件。

**目標使用者是誰？**
設計了三個 Persona：
- **Lisa（25-35 歲，上班族）**：下班後查帳單，不想等電話
- **Kevin（商務人士）**：出差時緊急掛失，需要即時處理
- **陳伯伯（銀髮族）**：需要清楚的步驟引導，不熟悉複雜操作

這三個 Persona 剛好對應三種不同的使用強度和技術熟練度，幫助我設計出包容性更廣的對話流程。

## ② Design Decision

**三個 MVP 的選擇邏輯：**
- **FAQ 查詢**：預期佔客服量的大宗，是最高頻的需求，且不需登入，最容易驗證
- **帳務查詢**：需要個人資料，代表 API 整合能力，是企業 AI 最常見的場景
- **信用卡掛失**：雖然量少，但影響最大（緊急性高），代表多步驟 Workflow 能力

最初考慮是否要加入「產品申辦」，後來決定不加，原因是申辦流程複雜度高、需要更多產品知識，對作品集的額外價值有限。先把三個 MVP 做好，比四個 MVP 做一半更有說服力。

**Disclaimer 設計的思考：**
一開始沒有想到這個問題。被挑戰「AI 回答錯誤利率，責任在誰？」之後，設計了三層防護：UI 固定文字、Prompt 規則、Intent 層強制插入。這個設計過程值得記錄。

## ③ Implementation & Iteration

*（本階段為文件產出，無實作內容）*

## ④ Evaluation & Reflection

**有效的部分：**
- PRD 的 12 個章節涵蓋了產品規劃階段會被問到的大部分問題
- 三個 Persona 的設計讓對話流程更有針對性
- Success Metrics 把「感覺上有效」轉換成可量化的數字

**下一版需要改善：**
- Use Case 可以加入更多的 Edge Case 場景描述
- 銀行業的監管合規需求（如個資法、金管會規定）目前未涉及，需要另外補充說明

---
---

# Phase 2：Conversation Design

## ① Requirement & Discovery

**為什麼需要專門的對話設計階段？**
AI 的回答品質不只取決於模型，更取決於對話流程的設計。如果沒有明確定義每個意圖的回應方式、Fallback 策略、Human Handoff 條件，實作時會充滿不確定性。先把對話設計好，程式碼才有明確的目標。

**這個階段要回答的核心問題：**
- 用戶說了什麼 → AI 應該做什麼
- AI 不知道怎麼回答時 → 怎麼處理
- 什麼情況下應該轉真人客服 → 轉接的門檻是什麼

## ② Design Decision

**Intent Taxonomy 的設計思考：**
初版只有 3 個大類（FAQ / ACCOUNT / WORKFLOW）。設計過程中發現需要再加 ESCALATION（投訴、轉接）和 OUT_OF_SCOPE（範圍外問題），因為這兩種情況在真實使用中會高頻出現，若沒有明確設計，AI 會不知道如何處理。

**Fallback 門檻的選擇：**
設定連續 3 次 Fallback 才觸發 Human Handoff。考慮過 2 次，但覺得太敏感；考慮過 5 次，但用戶體驗太差。3 次是在「給 AI 機會」和「不讓用戶等太久」之間的平衡點。

**對話記憶 10 輪的選擇：**
保留 10 輪（5 問 5 答）是為了平衡上下文理解能力和 token 成本。銀行客服對話通常不超過 5-6 輪就會解決，10 輪提供了足夠的緩衝。

## ③ Implementation & Iteration

*（本階段為文件產出，無實作內容）*

## ④ Evaluation & Reflection

**有效的部分：**
- UC-03 信用卡掛失的 5 步驟流程設計清楚，每個步驟都有明確的輸入、驗證、輸出
- Fallback 策略表格讓「什麼情況記錄、什麼情況不記錄」一目了然
- Mermaid 流程圖在 GitHub 自動渲染，視覺效果比純文字好很多

**下一版需要改善：**
- 中英文混用（Chinglish）的處理邏輯還不夠細緻，需要在實作時測試實際效果
- 對話流程目前只有文字腳本，Phase 8 Portfolio 時考慮錄製實際對話影片

---
---

# Phase 3：Solution Architecture

## ① Requirement & Discovery

**為什麼需要正式的架構設計階段？**
沒有架構圖就開始寫程式，很容易在模組之間的介面上卡住。先定義清楚「誰呼叫誰」「資料怎麼流」「每個元件的職責是什麼」，實作時才有明確的邊界。

**這個階段要回答的核心問題：**
- 系統由哪些元件組成
- 每個 Use Case 的資料流是什麼
- API 長什麼樣子（讓 Swagger 有內容）
- 資料庫存什麼、怎麼存

## ② Design Decision

**最重要的決策：兩層技術策略**
設計文件層（企業標準：Next.js、LangGraph、PostgreSQL、Docker）和實作層（作品集版：Streamlit、函式路由、SQLite）分開。這個決策讓我可以展示完整的企業思維，同時在可控的技術範圍內實際做出來。

**ADR 的引入：**
被問到「你怎麼決定這個技術選型？」時，意識到光有架構圖不夠，需要一份記錄「為什麼這樣選」的文件。ADR 的格式讓每個決策都有：背景、決策、理由、Trade-off、生產環境方案，這五個維度足以回答任何「為什麼這樣選」的追問。

**DB Schema 的設計思考：**
`unresolved_queries` 表記錄了 `trigger_reason`（low_similarity / handoff / api_failure），讓日後分析時可以區分「知識庫缺漏」和「用戶要求轉接」，這兩種情況的優化方向完全不同。

## ③ Implementation & Iteration

*（本階段為文件產出，無實作內容）*

## ④ Evaluation & Reflection

**有效的部分：**
- Mermaid 系統架構圖在 GitHub 上渲染效果好，可以直接展示給閱讀者
- ADR 7 個條目覆蓋了幾乎所有主要技術選型，有充分的說明素材
- 生產環境升級路徑表格（Section 8）讓閱讀者看到「這不只是 Demo，有完整的擴展思維」

**下一版需要改善：**
- 架構圖目前只有文字版 Mermaid，Phase 8 考慮用 draw.io 做一張更精緻的視覺版
- API endpoint 的 Request / Response schema 可以在 Phase 6 實作後補充真實的範例

---
---

# Phase 4：Knowledge Base

## ① Requirement & Discovery

**核心問題：沒有真實銀行資料，怎麼辦？**

這是作品集專案最現實的挑戰。真實銀行的 FAQ 文件、CRM 資料都是內部機密，無法取得。最初有兩個選項：
1. 找公開的銀行官網截圖，手動整理
2. 設計合成資料（Synthetic Data），仿照業界標準格式

選擇了合成資料，原因是：公開資料格式零散，且版權不明；合成資料可以完全控制結構和覆蓋範圍，且更容易說明「介面設計為可替換」。

**知識庫需要覆蓋哪些主題？**

根據 Phase 1 的 Intent Taxonomy 設計，FAQ 類別共有 8 個子意圖，因此知識庫也對應設計 8 個主題文件：
- 信用卡費用、信用卡優惠、帳戶服務、轉帳規則、ATM 服務、貸款概覽、數位銀行、一般服務

中英文各一份，合計 16 個 Markdown 文件。

## ② Design Decision

**決定一：每個主題一個文件，而非所有 FAQ 合成一個大文件**

選擇多文件結構，原因：
- RAG 的 Source Attribution（來源顯示）能增加可信度。「回答來自 credit_card_fees.md」比「回答來自 faq_all.md」更具說明力
- 維護性好：日後只需修改對應的主題文件，不需翻找大文件
- Chunking 後的 metadata 更清晰（source 欄位有意義）

**決定二：語言路由用獨立 Index，而非單一多語言 Index**

語言路由邏輯：`langdetect` 偵測輸入語言 → 路由到 `zh.index` 或 `en.index`。

原本考慮用單一多語言 FAISS index（`paraphrase-multilingual-mpnet-base-v2` 支援），但最終選擇分開，原因：
- 向量空間中，中英文同義詞的向量距離不一定夠近，可能造成搜尋混淆
- 分開 index 讓中文問題只搜中文文件，英文問題只搜英文文件，結果更可預測
- ADR-07 有詳細說明這個 trade-off

**決定三：Mock 客戶資料設計三個 Persona**

三個 Persona 對應三種使用情境：
- `user_001`（陳小明）：一般上班族，持 2 張信用卡，帳單金額適中
- `user_002`（王大明）：高消費商務人士，持無限卡，帳單金額高
- `user_003`（陳春花）：銀髮族，持基本金卡，有定存帳戶

這樣設計讓 demo 時可以展示不同場景，也能測試 AI 對不同資料結構的理解。

## ③ Implementation & Iteration

**知識庫文件撰寫策略**

採用「結構化 Markdown」格式，而非自然文字段落：
- 表格呈現費用、限額、服務時間（適合 RAG Chunking 後保留關鍵數字）
- 每個主題末尾有 FAQ 問答（模擬用戶真實問法，提高 RAG 匹配率）
- 同時用中文和英文撰寫，確保語言對等性

**Chunking 參數設計（預設 Sprint 5 實作）**

- Chunk Size：400 words（約 600 中文字），避免單一 chunk 太短失去語境、太長增加 noise
- Overlap：80 words，確保跨 chunk 的資訊不遺失（例如表格標題和內容分在不同 chunk）
- 這些參數設計在 `build_index.py` 中有詳細注釋，Sprint 5 驗證後可調整

**`build_index.py` 作為佔位符的意義**

Sprint 1-4 使用 Context Stuffing，不需要真正執行 FAISS。但在 Phase 4 就寫好這個腳本的原因：
- 展示知識庫架構的完整性（不只是文件，還有處理管線設計）
- 幫自己確認 chunking 邏輯是否可行
- Sprint 5 時只需解除注釋（uncomment）即可使用

## ④ Evaluation & Reflection

**成果驗收**

- 中文文件 8 個：`credit_card_fees.md`、`credit_card_benefits.md`、`account_services.md`、`transfer_rules.md`、`atm_services.md`、`loan_overview.md`、`digital_banking.md`、`general_services.md`
- 英文文件 8 個：內容與中文對等
- Mock 客戶資料：3 個 Persona，含帳戶餘額、信用卡資料、帳單、交易明細
- `build_index.py`：Sprint 5 佔位符，已設計好 chunking 邏輯和完整 TODO

**發現的問題**

- 知識庫中的利率、費用數字是虛構的（非真實銀行數字），這是作品集的限制，需要主動說明這一點，並強調「介面設計完全相容於真實文件」。
- 貸款相關文件（`loan_overview.md`）需要特別注意 Disclaimer 觸發設計，確保 AI 不會直接建議用戶申請特定產品。這個邏輯將在 Phase 5 的 Prompt Engineering 中處理。

**下一步（Phase 5）**

Phase 4 完成後，知識庫結構已確定。Phase 5 的重點是設計 AI Agent 的行為：
1. System Prompt：設定銀行 AI 的角色和行為規則
2. Intent Classifier Prompt：如何從用戶輸入判斷意圖
3. Safety Guard：哪些問題不該回答
4. RAG Answer Prompt：如何根據知識庫 context 生成回答
5. Workflow Prompt：掛失流程中每個步驟的對話設計

---
---

# Phase 5：AI Agent Design

## ① Requirement & Discovery

**這個階段要解決什麼問題？**

Phase 1-4 完成了「做什麼」（PRD、Conversation Design、Architecture、Knowledge Base），Phase 5 要定義「怎麼做」——AI 的行為規格。

在 Phase 4 結束後，知識庫已建立，但 AI 還不知道：
- 如何判斷用戶想要什麼（意圖分類）
- 判斷出意圖後，要怎麼回答（RAG / API / Workflow）
- 什麼情況下不該回答（Safety Guard）
- 掛失流程的每個步驟說什麼

這些設計如果不事先寫清楚，實作時就會每個問題都需要「現場決定」，品質不一致。

**這個階段的核心輸出：**
把 Phase 1-3 的需求，翻譯成 AI 可以執行的 Prompt 規格，讓 Sprint 實作時有明確依據。

## ② Design Decision

**決定一：Intent Classifier 獨立於主對話**

意圖分類使用獨立的 LLM 呼叫，輸出結構化 JSON，而非讓主對話 AI 在回答中「暗示」意圖。

理由：
- 分類結果機器可解析，不依賴文字解讀
- 可單獨測試分類準確率（建立 30 個測試案例，目標 > 90%）
- 未來可替換為更快的小模型，不影響主對話品質

**決定二：Safety Guard 分三層，最高優先級硬編碼**

非財務問題：Intent-level 攔截（不送 LLM，直接返回拒絕訊息）
財務 Disclaimer：程式碼層強制插入（不依賴 AI 自行判斷何時加）
詐騙情境警告：完全繞過 LLM，返回硬編碼的標準化警告

這個設計的一句話概括：「最高風險的邊界由程式碼控制，而非 AI 判斷」。

**決定三：Workflow Prompt 按步驟分離，而非一個大 Prompt**

信用卡掛失的 5 個步驟，每個步驟用不同的 Prompt，原因：
- 每步驟的 context 不同（Step 1 需要 id_last4、Step 2 需要 cards list）
- 每步驟的失敗處理不同（Step 1 最多 3 次、Step 3 可取消）
- 一個大 Prompt 包含所有步驟會讓 AI 混淆當前在哪個步驟

**決定四：RAG Answer Prompt 強調 Context-only**

RAG Prompt 的核心約束是「只根據提供的 Context 回答，不使用訓練知識補充」。
這個限制讓幻覺的空間縮小到「改寫知識庫內容」的範圍，比「憑空生成」風險低得多。

## ③ Implementation & Iteration

**產出物清單：**

| 文件 | 內容 |
|------|------|
| `docs/agent_design.md` | AgentState TypedDict、6 個 Node 設計、9 個 Tool spec、LangGraph 流程圖 |
| `docs/prompt_engineering/system_prompt.md` | System Prompt v1.0 + 版本歷史 + 測試案例 |
| `docs/prompt_engineering/intent_classifier.md` | 分類 Prompt + 路由邏輯 + 10 個測試案例 |
| `docs/prompt_engineering/safety_guard.md` | 三層安全設計 + 詐騙偵測 + Disclaimer 注入邏輯 |
| `docs/prompt_engineering/rag_answer.md` | Context-only Prompt + Sprint 1-4 Stuffing 版 + Sprint 5 RAG 版 |
| `docs/prompt_engineering/workflow_card_loss.md` | 5 步驟完整 Prompt + 邊界情境表格 |

**設計過程中發現的問題：**

- `workflow_data` 需要在 AgentState 中設計為 mutable dict，允許逐步填入（id_last4、card_id、ticket_id），這個結構在 Sprint 3 實作時需要小心初始化
- Intent Classifier 的 `unclear` 情境需要一個「最多問 2 次再提供選單」的機制，這個計數器也需要在 AgentState 中追蹤

## ④ Evaluation & Reflection

**有效的部分：**
- Prompt 規格文件讓每個 Sprint 的實作有明確依據，不需要在寫程式時臨時決定 AI 說什麼
- 9 個 Tool spec 用 OpenAI-compatible 格式撰寫，Sprint 6 移植到 LangGraph 時可直接使用
- Safety Guard 的三層架構清楚說明了責任分界，可以系統性地回答「如何防止 AI 幻覺」

**下一步（Sprint 0 → Sprint 1）：**
Phase 5 文件完成後，正式進入實作階段。

Sprint 0（專案骨架）：
- 建立 `requirements.txt`
- 建立 `backend/main.py` FastAPI 骨架
- 建立 `frontend/app.py` Streamlit 骨架
- 確認 `.env` 和 `ANTHROPIC_API_KEY` 設定

Sprint 1（FAQ with Context Stuffing）：
- Streamlit 聊天介面 + FastAPI `/chat` endpoint
- 使用 Context Stuffing + System Prompt 回答 FAQ
- 通過 10 個基本 FAQ 測試問題

---
---

# Sprint 1：FAQ（Context Stuffing）

## ① Requirement & Discovery

*(Sprint 1 開始後填寫)*

## ② Design Decision

*(Sprint 1 開始後填寫)*

## ③ Implementation & Iteration

*(Sprint 1 完成後填寫)*

## ④ Evaluation & Reflection

*(Sprint 1 完成後填寫)*

---
---

# Sprint 6：LangGraph 重構

## ① Requirement & Discovery

Sprint 1-5 已經把 FAQ、帳務查詢、信用卡掛失、真人客服轉接、未解決記錄五種行為，全部用 `backend/main.py` 裡一連串 `if/else` 撐起來。邏輯是對的，但 `/chat` 這個函式一路長到 371 行，五種分支的輸入輸出混在一起，沒有任何一個地方能單獨看到「這個意圖進來、產生了什麼 state」。ADR-002 早就寫好了要在這個時間點升級：先讓業務邏輯跑通、驗證過，再換架構。Sprint 6 就是兌現這個承諾——目標不是新增功能，是把已經驗證過的行為，重新組織成有明確邊界、可追蹤 State 的 Graph。

## ② Design Decision

**維持「外部行為完全一致」的硬限制**：`docs/agent_design.md` 開頭就寫「Sprint 1-5 與 Sprint 6 的外部行為一致，差異只在內部架構」，所以重構過程中不新增、不修改任何使用者可觀察到的行為，純粹是把同一段邏輯搬進 Router / CardLoss / Handoff / FAQ / Account / Logger 六個 Node。

**FAQ Node 和 Account Node 共用同一個實作**：這是最大的取捨。`docs/agent_design.md` §3.2/§3.3 把 FAQ 和 Account 寫成兩個獨立 Node，但 Sprint 1-5 的實際行為是——不管使用者問的是知識庫問題還是帳務問題，都丟進同一次 Claude 呼叫，system prompt 裡同時塞 RAG chunks 和使用者帳務資料（`format_user_context`）。如果為了呼應設計文件硬拆成兩個真正獨立的 LLM 呼叫，等於改變了實際行為（例如「我的信用卡年費是多少，另外我這個月帳單多少」這種混合問題，原本一次回答，拆開後可能要問兩次）。所以最後選擇：Router 仍然分類並標記 `intent="faq"` 或 `"account"`（State 上看得到、log 也分得開），但兩者路由到同一個 `qa_node`。這個決定的理由是：Node 邊界是為了可觀察性和未來擴充（如果之後真的要幫 Account 接 `get_account_balance` 之類的 tool call，只需要新增一個真正獨立的 Account Node，不影響 FAQ），不是為了現在就過度設計。

**Logger Node 要撐住「一輪可能觸發兩次 log」的既有行為**：原本的 `if/else` 裡，`negative_feedback` 檢查和 RAG `low_similarity` 檢查是兩段獨立的程式碼，同一則訊息如果兩個條件都成立，會呼叫兩次 `log_unresolved`。重構時一開始想把 Logger 簡化成「只記一筆」，後來意識到這樣會悄悄改變外部行為（DB 記錄筆數變少），違反①的硬限制。最後讓 State 帶一個 `log_entries: list[dict]`，`qa_node`/`handoff_node` 各自往裡面 append，`logger_node` 迴圈寫入——這樣兩次 log 的行為原封不動保留。

## ③ Implementation & Iteration

把原本塞在 `main.py` 裡的關鍵字判斷（`is_card_loss`／`is_handoff_trigger`／`is_negative_feedback`）和語言偵測搬到新的 `backend/src/nlp.py`；system prompt 組裝（`build_system_prompt`／`format_user_context`／`CONFIGS`）搬到 `backend/src/prompts.py`。新增 `backend/src/agent/`（`state.py` 定義 `AgentState`、`nodes.py` 六個 Node 函式、`graph.py` 用 `langgraph.graph.StateGraph` 接線）。`main.py` 的 `/chat` endpoint 縮到只剩：組出 initial state → `agent_graph.invoke()` → 轉成 `ChatResponse`，Pydantic 的 `ChatRequest`／`ChatResponse` 完全沒動，前端 Streamlit 不用改一行。

驗證方式：先用假的 `client`／`retriever`（回傳固定字串，不打真的 API）跑過六條路徑確認 Graph 走線正確；接著啟動真正的 `uvicorn`，用實際的 Claude API + FAISS index 跑了 FAQ（中英各一）、已登入帳務查詢、完整四步驟信用卡掛失流程、關鍵字轉真人客服、負面回饋+低相似度同時觸發五種情境，逐一比對 `/tickets`、`/unresolved`、`/stats` 三個 dashboard endpoint 的寫入結果，確認和 Sprint 5 的行為（包含「一輪兩筆 log」這個邊角案例）完全一致。

## ④ Evaluation & Reflection

實測跑下來，六個 Node 的行為和重構前逐項核對都一致，包含最容易漏掉的邊角案例：使用者在掛失流程中途被登出（`workflow_step > 0` 但沒有 `user_id`）時，原本的程式碼會把 workflow 悄悄重置成 step 0——這其實比較像是 Sprint 1-4 沒注意到的行為，而不是刻意設計。重構時選擇原封不動保留這個行為（沒有藉機「順手修掉」），因為 Sprint 6 的任務是重構架構、不是修正邏輯，兩件事分開做才不會讓「行為有沒有變」這個驗證變得混亂。這個小案例本身也值得記錄：重構最大的風險不是寫錯新程式碼，而是「順手」把舊的（不管是不是 bug）行為改掉。

下一版如果要繼續往前，Account Node 是最明確的候選：接上 §4 定義的 `get_account_balance`／`get_credit_card_bill`／`get_transactions` 等 tool spec，讓 Account 查詢真正走結構化 API 呼叫而不是整包 context stuffing，這樣可以顯著縮小 system prompt、也更貼近企業產線常見的 tool-calling Agent 設計。

---
---

# Sprint 7：Account Node Tool-Calling

## ① Requirement & Discovery

Sprint 6 的反思裡已經寫得很清楚：Account Node 只是 Router 貼的一個標籤，實際查帳務問題還是走 FAQ Node 那套 context stuffing——把整個使用者的存款、信用卡、帳單、近期交易全部塞進 system prompt，不管使用者只是問「餘額多少」。這在作品集中是個明顯的破綻：一個宣稱懂 Agent 架構的人，Account「Node」卻沒有真正做到「Node」該做的事。Sprint 7 的目標很單純：把這筆 Sprint 6 刻意欠下的技術債還掉，讓 Account Node 變成一個真正會呼叫 tool 的 Agent。

## ② Design Decision

**Account 從此和 FAQ 分家，各自獨立呼叫 Claude**：不再共用 `qa_node`。Account Node 有自己的 system prompt（只講帳務規則、不帶 RAG）、自己的 tools 參數、自己的 tool-use 迴圈。這是 Sprint 6 沒做但已經預告的事——現在條件成熟了（Sprint 6 已經把 Node 邊界搭好），可以放心拆。

**`user_id` 不給模型填，後端注入**：這是這次最重要的安全決策。`docs/agent_design.md` §4.2-4.4 原始的 tool spec 把 `user_id` 列成參數之一，是為了描述一個「通用」的工具介面；但如果照抄進 Claude 看得到的 schema，等於讓模型自己決定要查誰的帳戶——萬一被 prompt injection（例如使用者在對話中說「幫我查 user_003 的餘額」）操控，就有跨用戶查詢的風險。所以 `backend/src/agent/tools.py` 的 `ACCOUNT_TOOLS` 故意不包含 `user_id`，改由 `execute_tool()` 在執行當下從已驗證的 session state 注入。這個決定值得記下來，因為它是「照抄設計文件 vs. 自己多想一步」的具體案例。

**FAQ Node 的 context stuffing 保留當安全網**：Router 用關鍵字判斷 `is_account_query`，一定會有誤判（例如「信用卡年費」被誤判成 FAQ，或反過來）。與其花時間把關鍵字規則調到完美，選擇讓 FAQ Node 的 system prompt 繼續帶著使用者帳務資料——就算 Router 判斷錯，使用者也不會得到「查不到」的爛體驗，只是沒有用到 tool-calling 的精準度。這是刻意保留的重複，不是漏掉沒清理。

## ③ Implementation & Iteration

在 `backend/src/mock_api/mock_data.py` 新增三個純函式（`get_account_balance`／`get_credit_card_bill`／`get_transactions`），對應 §4.2-4.4 的資料形狀。新建 `backend/src/agent/tools.py` 定義 Anthropic tool schema 和 `execute_tool()` dispatcher。`nodes.py` 新增 `make_account_node()`：先檢查 `user_id`，未登入直接回登入提示（不打 API）；已登入則跑 tool-use 迴圈（最多 `MAX_TOOL_ITERATIONS=3` 輪，防止模型卡在無限呼叫工具）。`graph.py` 把 `account` 意圖從 `qa` 節點改指到新的 `account` 節點。

驗證方式：實測餘額查詢、帳單查詢、交易明細查詢、以及一次問兩件事（「活期餘額多少，最近花了什麼」）確認模型會依序呼叫兩個工具再整合回答；也測了未登入時查帳務資訊，確認完全不觸發 Claude 呼叫、直接回登入提示。同時跑了 FAQ 和信用卡掛失流程的回歸測試，確認沒有被這次改動波及。

## ④ Evaluation & Reflection

混合問題（一次問餘額又問交易）那個測試案例特別能說明 tool-calling 相對 context stuffing 的優勢：Claude 自己決定要呼叫兩個工具、依序取得資料再整合成一段自然語言回答，而不是像之前那樣不管問什麼都把所有資料倒給它讀。輸出品質沒有變差，但 system prompt 大小和資料曝露範圍都明顯縮小。

比較意外的收穫是「`user_id` 由後端注入」這個決定——一開始只是照著 §4 的 tool spec 抄，抄到一半才意識到「如果 Claude 自己填 user_id，這個工具就是不安全的」。這提醒了自己：設計文件是 Sprint 6 之前寫的規格，寫規格的時候還沒有認真想過 prompt injection 這個角度，執行到這一步才補上，說明「先寫文件、再寫程式」的流程本身不能取代寫程式當下的安全意識。

下一版如果要繼續往前，比較明確的候選是把 Router 的關鍵字分類（`is_account_query` 等）換成真正的 LLM Intent Classification，減少誤判；另一個方向是幫 CardLoss Workflow 也導入 tool-calling（`verify_identity`／`block_card`／`create_ticket` 目前都是直接呼叫 Python 函式，沒有經過 Claude 決策），但這個改動風險較高，需要先想清楚多步驟工作流程和 tool-calling 迴圈要怎麼共存。

---
---

# Sprint 8：測試套件

## ① Requirement & Discovery

Sprint 1-7 每一輪都是手動測試——啟動 `uvicorn`、用 curl 或 Python script 打幾個請求、看結果對不對、然後關掉 server，測試腳本沒有留下來。這樣做的問題在 Sprint 6/7 交界處就露出來了：兩次都要重新手動驗證同一批舊行為（FAQ、Handoff、CardLoss）沒有被新改動波及，而且有一次手動測試甚至把真的 `banking.db`（展示用的 Dashboard 資料）弄髒了，得手動清資料列。這次的目標是把「驗證系統沒壞」這件事，從一次性的手動動作變成可以留在 repo 裡、隨時重跑的東西。

## ② Design Decision

**測試用資料庫要完全獨立，不跟真實 demo 資料共用檔案**：討論了兩個方案——(A) 獨立 `test.db`、(B) 每次測試後自動清除新增的資料列。方案 B 的風險是：如果測試中途 assert 失敗或程式當掉，清除邏輯根本不會執行，垃圾資料就留在真實 `banking.db` 裡（這正是這次 Sprint 6/7 之間手動測試時實際發生過的事）。方案 A 結構上更安全——就算測試寫錯、當掉，最壞情況也只是 `test.db` 裡有垃圾，重新產生一次就好，不會動到用來展示的 Dashboard 資料。代價是要把 `backend/src/database.py` 原本寫死的 `DB_PATH` 改成可以用環境變數 `BANKING_DB_PATH` 覆寫，`tests/conftest.py` 在 import `backend.main` 之前先設好這個環境變數。

**測試斷言只驗證「結構」，不驗證「LLM 說了什麼」**：FAQ 和 Account Node 每次呼叫 Claude，用字遣詞都會變，沒辦法寫 `assert response == "..."`。這次的分工很明確：pytest 只負責驗證確定性的部分——語言偵測對不對、意圖有沒有路由到對的 Node、workflow_step 有沒有正確推進、tool 有沒有被呼叫、DB 有沒有寫入正確的 ticket/log；回答「寫得好不好」留給人工，checklist 已經整理在跟使用者的討論記錄裡（語言正確性、有沒有幻覺、disclaimer 出現時機、中英文語意對齊等）。這個分工意外地讓一大部分測試變得完全免費——CardLoss 和 Handoff 兩個 Node 本來就是純 Python 邏輯，完全不呼叫 Claude，所以這兩個檔案的測試是零 token 成本，也因為沒有 LLM 的不確定性，可以放心用 `assert ... ==` 精確比對。真正會呼叫 API、需要保持斷言寬鬆的，只有 FAQ 和 Account 兩個檔案。

**測試資料用不同的 mock user 隔開，而不是靠 fixture reset**：`MOCK_USERS` 是 Python 記憶體裡的全域字典，`block_card()` 會直接改掉裡面卡片的狀態。因為每次執行 `pytest` 都是全新的 Python process，`MOCK_USERS` 本來就會重新從原始碼載入，不需要額外寫 reset 邏輯；只要確保「會改變卡片狀態」的測試（掛失流程走到底）跟其他測試用不同的 demo 帳號（`user_002` 專門給完整掛失流程用，`user_001` 只做唯讀的帳務查詢，`user_003` 給中途取消的流程用），彼此就不會互相干擾。

## ③ Implementation & Iteration

新增 `tests/conftest.py`：在 import `backend.main` 之前設定 `BANKING_DB_PATH` 指向 `tests/test.db`，用 session-scoped 的 `TestClient` fixture（`with TestClient(app) as c`）觸發一次真正的 FastAPI startup event（`init_db()`、RAG retriever 載入、LangGraph build），整個測試 session 只需要載入一次 embedding model，而不是每個測試都重新載入一次。新增 `pytest.ini` 設定 `pythonpath = .`，確保不管用 `pytest` 還是 `python -m pytest` 執行，`backend.*` 的 import 都能正確解析。

四個測試檔案：`test_faq.py`（FAQ 中英文、負面回饋+低相似度雙重 log 的回歸測試）、`test_account.py`（未登入拒答、餘額/帳單/交易查詢、混合問題觸發多個 tool）、`test_card_loss.py`（完整四步驟流程並驗證 ticket 正確建立、中途取消、未登入、身分驗證失敗重試）、`test_handoff.py`（關鍵字觸發、`force_handoff` flag）。總共 14 個測試案例，跑一輪大約 40 秒。

驗證方式：連續跑兩次確認結果一致（沒有測試間互相汙染）；跑完後直接檢查真實 `data/banking.db`，確認 ticket 數量和 unresolved_queries 筆數完全沒有變化，證明隔離確實有效；也確認沒設 `BANKING_DB_PATH` 時 `DB_PATH` 仍正確預設回原本的路徑，production 行為不受影響。

## ④ Evaluation & Reflection

意外的收穫是 CardLoss 和 Handoff 兩個 Node 的測試完全零成本——一開始以為「整套測試套件」意味著全部都要打 Claude API、要精算 token 預算，實際動手才發現真正呼叫 LLM 的只有 FAQ 和 Account 兩塊，其餘的路由、狀態機、DB 寫入邏輯都是確定性的 Python，可以又快又精準地測。這也間接印證了 Sprint 6 的 Node 化設計是對的方向：邊界清楚之後，才看得出哪些部分是「AI 決策」、哪些部分是「工程邏輯」，兩者需要完全不同的測試策略。

`negative_feedback_and_low_similarity_dual_log` 這個測試特別值得一提：它不是新寫的功能測試，而是把 Sprint 6 design journal 裡提到的「一輪對話可能觸發兩筆 log」這個容易被未來的自己不小心「順手修掉」的邊角行為，轉成一個會在 CI 或下次改動時自動失敗的斷言。這是測試套件相對於手動測試最大的價值——手動測試驗證的是「現在對不對」，自動化測試保護的是「以後會不會被悄悄改壞」。

下一步如果要讓這套測試更完整，比較明確的候選是：(1) 把 `on_event("startup")` 換成 FastAPI 建議的 `lifespan` 寫法，消除目前測試輸出裡的 deprecation warning；(2) 若之後想接 GitHub Actions 秀 CI 徽章，需要另外決定 `ANTHROPIC_API_KEY` 怎麼安全地存進 GitHub Secrets，以及能不能接受每次 push 都燒一次 token 的成本。

---
---

# Sprint 9：Router LLM Intent Classification

## ① Requirement & Discovery

`docs/agent_design.md` §3.1 從專案一開始（Phase 5，寫在 Sprint 1 之前）就把 Router 定義成「Intent Classification（LLM 分類）」，但 Sprint 1-8 一直是用關鍵字比對頂著——這件事在 Sprint 7、Sprint 8 的反思裡都各自提過一次，是明確欠著的一筆債。這次要還的不是新功能，是讓實作終於對齊最早寫下的設計文件。動機也很具體：關鍵字比對的失敗模式是結構性的，不是清單不夠長的問題——它只能比對「有沒有出現特定字」，沒辦法理解語意，遇到清單沒覆蓋到的講法就會誤判。

## ② Design Decision

**用 `tool_choice` 強制結構化輸出，不解析自由文字**：分類器呼叫 Claude 時用 `tool_choice={"type": "tool", "name": "classify_intent"}` 強迫模型一定要呼叫這個 tool、一定要從四個分類（`faq`／`account`／`card_loss`／`handoff`）裡選一個。這樣拿到的結果保證合法，不需要處理「模型沒照格式回答」這種例外，也不用寫文字比對或 regex 去猜模型想表達哪個分類。這個做法直接複用了 Sprint 7 已經驗證過的 tool-calling 模式，只是這次工具不是拿去查資料，而是拿來逼出一個結構化分類結果——算是同一個技術手法的第二種用法，這點值得一提。

**兩種情況刻意不呼叫分類器**：掛失流程進行中（`workflow_step > 0`）和前端強制轉真人客服（`force_handoff`，連續 fallback 達門檻）維持原本的確定性判斷，直接跳過 LLM。這兩者本質上是「系統目前處於什麼狀態」，不是「使用者這句話是什麼意圖」——如果連這個都交給 LLM 判斷，等於把一個原本 100% 確定的邏輯，換成一個有機率誤判的邏輯，沒有任何好處，純粹增加延遲和不確定性。這個判斷跟 Sprint 6 保留「一輪兩筆 log」行為是同一種思路：分清楚「這是系統狀態」還是「這是需要理解的內容」，兩者的處理方式不該混在一起。

**FAQ Node 的 context stuffing 繼續留著當安全網**：這個決定 Sprint 7 就做過一次，這次沒有理由推翻——即使分類器比關鍵字準，還是有機率誤判，FAQ Node 的 system prompt 仍然帶著使用者帳務資料，誤判時不會完全答不出來。

## ③ Implementation & Iteration

新增 `backend/src/agent/intent.py`：`INTENT_CLASSIFIER_TOOL` 定義四分類 tool schema，`classify_intent()` 用強制 tool_choice 呼叫並取出分類結果。`nodes.py` 的 `router_node` 改寫成 `make_router_node(client, model)` 工廠函式，保留 `workflow_step > 0` 和 `force_handoff` 兩個確定性分支，其餘交給 `classify_intent()`。`nlp.py` 刪掉三個變成死代碼的關鍵字函式（`is_card_loss`／`is_handoff_trigger`／`is_account_query`）和對應的關鍵字清單，只留 `is_negative_feedback`（FAQ/Account Node 內部用，跟路由是不同關注點）和 `detect_language`。

第一版寫完直接被 Sprint 8 的測試套件抓到一個問題：`test_negative_feedback_and_low_similarity_dual_log`（Sprint 6 就存在的回歸測試）失敗，原因是「你搞錯了，這不是我要的答案」被分類器誤判成 `handoff`——這句話單獨看確實像在抱怨，分類器沒有上下文，判斷「使用者聽起來不爽 = 想找真人客服」不是完全沒道理的推論，但這跟系統原本的設計不符（單純的負面回饋走 `negative_feedback` log，不直接升級成 Handoff）。修法是在 tool description 裡明確列出反例（「單純說答案不對／沒幫助，不算要求轉真人客服」），並補一個 `no prior conversation` 的提醒，讓模型知道自己只看得到這一句話、沒有前後文可以判斷。修完後另外寫了 `tests/test_router_intent.py` 直接測 `classify_intent()` 本身（不透過完整 `/chat`），把這個案例釘成一個獨立的分類器回歸測試——這樣以後如果又不小心把 tool description 改壞，能直接定位到是分類器的問題，不用先猜是不是 FAQ Node 或 DB 寫入壞了。

順手處理了兩個因為改名而出現的殘留：`trigger_reason` 從 `"handoff_keyword"` 改名成 `"handoff_intent"`（因為觸發方式已經不是關鍵字了），這個字串同時出現在 `nodes.py` 的預設值和 `frontend/pages/1_Dashboard.py` 的兩個 Dashboard 圖表 label 對照表裡——後者如果沒改，Dashboard 上「要求真人客服」這個分類會因為字典查不到 key 而直接顯示英文原始字串，不會報錯但會很難看，算是那種「不會壞、但會露餡」的細節。

驗證方式：連續跑兩次完整 pytest 套件（19 個測試，含新增的 `test_router_intent.py` 5 個案例）確認結果穩定；跑完後檢查真實 `data/banking.db` 沒有任何變化，確認 Sprint 8 的隔離設計在這次改動後依然有效。

## ④ Evaluation & Reflection

這次最有價值的部分不是分類器本身寫出來了，而是「寫完馬上被自動化測試抓到一個沒預料到的誤判案例」這個過程本身——如果沒有 Sprint 8 先把測試套件建起來，這個誤判很可能要等到手動測試、甚至demo 時才會被發現，而且很可能被忽略過去（畢竟「你搞錯了」被當成抱怨要轉真人客服，語意上不算離譜，不仔細看行為對不對就很容易滑過去）。這也是這幾個 Sprint 疊起來的複利效果：Sprint 6 定義清楚 Node 邊界、Sprint 7 建立 tool-calling 模式、Sprint 8 把回歸測試變成可重跑的東西，Sprint 9 才有辦法在改動當下就抓到問題，而不是憑感覺相信「LLM 應該分得出來」。

比較意外的收穫是「Sprint 9 讓測試套件的成本模型也跟著變了」——Sprint 8 完成時特別強調 CardLoss／Handoff 測試零成本，因為關鍵字路由不呼叫 API；Sprint 9 把路由本身換成 LLM 之後，這個「零成本」的說法已經不完全準確（每個流程的第一句觸發訊息現在都要過一次分類器）。這提醒了自己：文件裡寫「零成本」這種具體宣稱時，要意識到它是建立在當下架構上的，架構一變就要回頭檢查有沒有跟著過時——這次有記得回去更新 Sprint 8 測試檔案的 docstring，但如果沒有測試套件這個明確的參照物，這種文件跟實作脫節的狀況很容易被忽略。

下一步如果要讓 Router 更完整，比較明確的候選是 §3.1 提到但 v1 一直沒做的「意圖分類信心度低 → 反問用戶」——現在用 `tool_choice` 強制輸出，拿到的是確定結果，沒有信心分數可以判斷模型是不是在瞎猜，如果要做需要換一種呼叫方式（例如比較拿掉強制呼叫後模型會不會遲疑、或用 logprobs）。這個功能對「展示核心 Agent 架構」的邊際效益不高，暫不列入下一個 Sprint。

---
---

# Sprint 10：實際上線測試抓到的三個修復

## ① Requirement & Discovery

Sprint 9 完成後，請使用者親自扮演「真人客服」的角色，登入前台實際測試整個系統，而不是只看我自己的煙霧測試。這次測試抓到兩份回報，拆開來看其實是三個獨立的根本原因：語氣贅字（「好的，我幫您說明...」每句都套用，文法也奇怪）、信用卡掛失流程混亂（掛失完成後說「取消掛失」卻被當成開新流程處理），以及最嚴重的一個——AI 在對話中順著使用者的錯誤說法，捏造「卡片應該已經恢復正常使用」這種假話，即使當下系統其實有正確的帳戶資料可以查。

## ② Design Decision

**語氣**：System Prompt 裡「Lead with action... e.g. 好的，我馬上幫您查！」這句「範例」被模型當成固定模板套用，改成明確要求「每次開頭要變化，多數回答可以直接進內容，真的需要開場白時要用「我為您」不是「我幫您」」。

**掛失流程混亂**：根本原因是 `card_loss_node` 在 `workflow_step == 0` 時，完全沒有能力分辨「這是要開新的掛失」還是「這是在講一個已完成的掛失」——新增 `RESTORE_KW` 關鍵字比對（比照 `card_loss_workflow.py` 既有的 `_is_cancel()` 模式），偵測到「取消掛失」「找到卡了」這類講法、且使用者確實有已掛失的卡片時，誠實回覆「聊天機器人無法復原已掛失的卡片，請撥客服」，而不是盲目重新觸發驗證流程。刻意**不**新增一個「恢復卡片」功能——系統從掛失流程第 3 步就明確告知「掛失後立即停用」，這本來就設計成單向動作，跟真實銀行的行為一致。

**AI 順著使用者說謊**：在 System Prompt 的 Answer Rules／Tool Use Rule 加一條明確指令——「使用者的說法如果跟帳戶資料衝突，以資料為準，不能為了順著對話而附和」。

## ③ Implementation & Iteration

三個修復都重現了使用者原始回報的完整對話來驗證：語氣測試跑了多個 FAQ 問題確認開頭有變化；掛失流程重現「掛失完成 → 說取消 → 再次掛失」的完整序列，確認新回應正確；順著說謊的情境用同樣的假設句「剛不是已經恢復正常了嗎」重新測，確認模型改為堅持查證後的真實狀態。三次都跑在真實 `uvicorn --reload`（不是隔離的 test.db），因為這次是在驗證使用者真的會走的對話，不是抽象的單元測試。

## ④ Evaluation & Reflection

這三個修復沒有一個是我自己測試時能發現的——都要靠使用者真的把系統當工具用、走一遍完整對話才會露出來。特別是「AI 順著說謊」這個問題：如果只看單一輪的回答，模型的行為看起來完全正常（有禮貌、看似合理），只有把多輪對話串起來看，才看得出來它在附和一個跟真實資料矛盾的說法。這提醒了自己：手動測試的價值不是「找 bug」，是「模擬真實使用者會怎麼帶著錯誤假設繼續往下問」——這是任何單輪測試案例都設計不出來的情境。

---
---

# Sprint 11：已轉接真人客服 Banner

## ① Requirement & Discovery

使用者測試時發現「轉真人客服」沒有任何視覺變化，追問後才發現：系統本來就沒有做「已轉接真人客服」的對話介面，只是回一則文字訊息。透過 `/plan` 進入正式規劃流程，用 Explore agent 確認現況、Plan agent 設計實作細節，最後選定三個選項裡範圍最小的一個：在對話上方顯示持久性 banner，不改訊息泡泡樣式、不做模擬雙方對話。

## ② Design Decision

**後端要先補一個信號**：Explore 階段發現 `ChatResponse` 完全沒有欄位可以讓前端知道「這輪是不是轉真人客服」——LangGraph 內部 `intent` 早就算出來了，只是沒有傳到 HTTP 回應。新增 `is_handoff: bool`，比照既有的 `is_negative_feedback` 做法（在 API 邊界把內部訊號轉成布林值，不直接外洩 `intent` 這個內部列舉）。

**Banner 要不要自動消失**：這是跟既有的信用卡掛失流程 banner 唯一不同的地方——掛失流程 banner 會消失是因為**後端**主動把 `workflow_step` 重置成 0；但「轉真人客服」沒有對應的後端狀態可以追蹤「現在是不是還在轉真人客服」，Router 每輪都是重新分類。決定讓前端自己把這個旗標設成「一旦觸發就持續到使用者主動清除對話」——真正的轉真人客服不應該被後續一句不相關的 FAQ 問題悄悄取消掉。

## ③ Implementation & Iteration

`backend/main.py` 加欄位、`frontend/app.py` 加 `handoff_active` session state、比照既有 `workflow` banner 樣式加一段 `st.warning`，並在「清除對話」「登入」「登出」三個既有的「重置成全新對話」的地方，一併加上重置這個新旗標——後兩個不是硬性要求，但跟 `messages`／`welcomed` 已經在同樣的地方重置是同一個理由：不重置的話，同一瀏覽器分頁換一個測試帳號登入，會看到上一個人的轉真人客服 banner 殘留。用瀏覽器實測整個流程：觸發轉真人客服、確認 banner 在下一輪對話時出現、問一般問題確認 banner 不會消失、按清除對話確認 banner 消失。

## ④ Evaluation & Reflection

banner 第一次觸發時沒有立即出現、要等下一輪對話才顯示——一開始以為是 bug，後來確認這是 Streamlit 由上到下逐行執行腳本的正常行為（本輪對 session_state 的修改，要下一次重新渲染才會反映在畫面上），跟既有的信用卡掛失流程 banner 是同樣的特性，不是這次改動特有的問題。清理測試資料時，意外在真實資料庫裡發現兩筆使用者自己測試留下的真實服務單（不是我的測試產生的）——正確地沒有刪除，只清掉自己這次驗證產生的部分，這是「先看清楚是誰的資料，再決定要不要清」的具體案例。

---
---

# Sprint 12：FAQ Node 導入獨立核實（Grounding Verifier）

## ① Requirement & Discovery

使用者主動提出一個架構構想：把「回答」跟「核實這個回答有沒有依據」拆成兩個獨立角色，直接針對診斷案例研究裡發現的那個監控盲點——RAG 相似度分數只能判斷「有沒有東西超過門檻」，判斷不了「這東西真的答得了這個問題嗎」。這個構想的價值討論過程本身值得記錄：一開始用「多代理協作」描述，但實際上這是「先生成、後獨立核實」的序列管線，不是有協商互動的多代理系統——這個用詞precision 上的修正，讓後續的技術決策更精準。

## ② Design Decision

**只在分數落在模糊地帶時才呼叫 Verifier**：案例研究實測「好答案」最低分 0.482、「已知缺口」最高分 0.500，中間本來就重疊，沒有一個閾值能完美切開兩邊。設閾值 0.60（高於所有已知缺口分數，留安全邊界），分數 ≥ 0.60 直接信任 Draft、跳過 Verifier；< 0.60 才觸發，讓多數清楚的問題完全不用多付延遲成本。

**順序倒過來：先驗證 chunk，再決定要不要生成 Draft**——不是「先生成 Draft、再核實」。這樣設計在「答不出來」的情境下反而更快：實測 Draft 生成本身要 3.75~6.69 秒，是三個呼叫裡最貴的一步，提前判斷不夠格就直接跳過，不用白白付這筆成本。

**範圍：套用在所有 FAQ 流量，不分登入狀態**——原本的提案想比照舊版 `rag_low_similarity` 排除已登入使用者（理由是他們有帳務資料安全網），但討論中發現這個理由站不住腳：FAQ Node 處理的定義上就是 `intent="faq"`，帳務相關問題會被 Router 分流到 Account Node，帳務資料安全網對一般性知識庫問題完全幫不上忙。收回這個排除條件，讓範圍更單純。

**取代而非並存舊機制**：新的 Verifier 觸發條件完全涵蓋舊的 `rag_low_similarity` 判斷範圍，兩者並存只會對同一次失敗重複記錄兩筆意思相同的 log，沒有額外資訊量——移除舊的 `has_relevant_results()`／`SIMILARITY_THRESHOLD`，改用新的 `verifier_unresolved`。

**轉真人客服時要讓前端也看得到**：Verifier 判定不夠格時，把 `intent` 覆寫成 `"handoff"`——這樣 Sprint 11 剛做的「已轉接真人客服」banner 才會正確顯示，兩個 Sprint 的產出接得上。回傳的文字訊息一開始沿用既有的 `HANDOFF_MSG`，但使用者實測後指出這樣不對：`HANDOFF_MSG` 是「很抱歉我沒能完全解決您的問題」這種道歉語氣，是回應「使用者主動要求或抱怨著要轉真人客服」的情境；但 Verifier 觸發的轉真人客服，是 AI 自己主動判斷答不出來，使用者只是正常問了一題，並沒有抱怨——套用道歉語氣讀起來像是在暗示使用者剛剛在跟系統爭執，並不符合實際情境。改成獨立的 `VERIFIER_ESCALATION_MSG`（「此問題我為您轉接真人客服回覆，轉接中，請稍候」），語氣是「主動幫你轉接」而不是「我很抱歉」。

## ③ Implementation & Iteration

新增 `backend/src/agent/verifier.py`（比照 `intent.py` 的 `tool_choice` 強制結構化輸出手法），`qa_node` 改成「檢索 → 依分數決定要不要驗證 → 驗證不足就提早回傳轉真人客服、足夠才生成 Draft」。清理 `retriever.py` 裡因此變成死代碼的 `has_relevant_results()`／`SIMILARITY_THRESHOLD`／`above_threshold`（順手移除了一個原本就沒在用的 `import numpy` 殘留）。新增 `tests/test_verifier.py` 直接測 `verify_chunks_sufficient()`（一個明確有依據、一個明確沒依據——就是案例研究裡外幣兌換那組真實 chunk），並在 `tests/test_faq.py` 加一個打完整 `/chat` 的回歸測試，鎖定案例研究發現的那個確切案例：現在應該正確轉真人客服並記錄 `verifier_unresolved`。

延遲影響有實際測量：Verifier 本身呼叫約 2.2~3.8 秒（多次測量），但因為「先驗證再生成」的順序設計，答不出來的情境反而比正常路徑更快——實測正常 FAQ 一輪約 8.9 秒，轉真人客服的一輪只要 3.5 秒，因為省下了最貴的 Draft 生成那一步。

## ④ Evaluation & Reflection

端到端重跑了案例研究裡發現問題的那個確切輸入（「外幣現鈔要去哪裡換，匯率怎麼算?」），這次正確記錄成 `verifier_unresolved`，相似度分數 0.421——跟案例研究裡量測到的數字完全吻合，代表這次的修復是直接對準當初發現的具體盲點，不是憑空想像的改善。

過程中修正了自己一次不夠嚴謹的判斷：一開始提案排除已登入使用者，是照抄舊機制的既有界線，沒有重新檢查這個界線的理由在新設計底下還站不站得住腳——後來被問「登入的使用者會出現什麼狀態」才發現自己漏想了。這跟 Sprint 6 沿用既有模式時的態度不同：沿用既有模式（例如比照 `intent.py` 的 tool_choice 手法）是好的重用，但沿用既有的「排除條件」如果沒有重新驗證背後的理由是否還成立，就是照抄而非重用。

下一步如果要讓這個機制更完整，比較明確的候選是：(1) 幫 Verifier 補上快取，銀行 FAQ 天生高度重複，同樣問題+同樣 chunk 組合不需要每次都重新呼叫；(2) 把 `verifier_unresolved` 的優先度在 Dashboard 上跟使用者主動要求的 `handoff_intent` 分開處理——前者是 AI 自己確認救不了，理論上更該優先被人工介入。

**上線後追加的三個修正**（同一 Sprint 內，使用者實測發現）：

1. **知識庫真的補上外幣現鈔兌換**——`data/knowledge_base/{zh,en}/foreign_currency_exchange.md`，Verifier 機制本身沒問題，但案例研究發現的那個具體缺口（外幣兌換完全沒有內容）本來就該補，不是只靠 Verifier 擋著就結束。

2. **「即時匯率是多少」這類問題，補上即時匯率查詢網址，而不是繼續轉真人客服**——這裡發現 Verifier 有一個原本沒設計到的邊界案例：知識庫內容補齊「怎麼兌換」之後，「美金匯率『現在』是多少」這種問題還是被判定「不足」，因為 Verifier 很嚴格地認定「chunk 沒有寫死一個具體數字」＝不足。但匯率本來就每天變動，寫死一個數字才是真正的問題（過期資訊）。修法是雙管齊下：知識庫內容加上即時查詢網址並明講「網址本身就是完整答案」，同時修改 `VERIFIER_SYSTEM_PROMPT` 明確排除這種情況——「會員每天變動、本質上不該寫死的資料，chunk 只要提供查詢管道就算足夠」。這是一個好的提醒：Verifier 的「嚴格」要對準「答非所問」，不能嚴格到把「這是動態資料、本來就該給查詢入口」也當成缺口。

3. **轉真人客服轉太久的延遲問題，暫緩處理**——使用者要求一般 FAQ 3 秒內要回覆，但目前架構是「分類器→（可能）Verifier→Draft」三次依序呼叫 Claude，光 Draft 生成單獨一次實測就要 4~7 秒，物理上不可能穩定壓到 3 秒內。誠實回報現況、提出串流（Streaming）作為對的解法方向（讓文字即時逐字顯示，體感速度快，但不改變總生成時間），留給使用者決定要不要投入這個範圍較大的架構改動，沒有為了「應付要求」硬做一個治標的假修復。

**這次收穫最大的一課**：發現與修復的過程本身，剛好完整示範了 Sprint 這幾輪一直在講的原則——不要一次把所有假設都做完，要讓使用者實測、抓出真正的邊界案例，再一項一項對準修。Verifier 補了知識庫缺口，卻沒想到「動態資料」是另一種邊界；補了動態資料的例外規則，又冒出真實世界的效能限制。三個問題疊在同一次使用者驗證裡浮現，剛好是「先讓核心邏輯正確、再處理邊界案例、最後才是效能」這個優先順序的具體案例。

---
---

# Sprint 13：FAQ Node 串流回覆

## ① Requirement & Discovery

Sprint 12 的使用者驗證裡，第一點回報是「一般 FAQ 內容回覆應該 3 秒內完成」。實測目前架構（分類器 → 可能還有 Verifier → Draft 生成）三次依序呼叫 Claude API，光 Draft 生成單獨一次就要 4~7 秒，物理上不可能穩定壓到 3 秒內完成整段回答。老實跟使用者講清楚這個限制後，選擇了業界標準解法：串流（Streaming）——不是縮短總生成時間，而是讓文字一個字一個字即時顯示，使用者體感上從「等到全部生成完才看到」變成「很快就看到開始有反應，然後看著它打字」。

## ② Design Decision

**新增 `/chat/stream`，不改動既有的 `/chat`**：這是這次最重要的範圍決定。`/chat` 的 JSON 回應格式已經被 Sprint 8 建立的整套 pytest 套件依賴（`resp.json()["response"]` 這種用法），如果讓 `/chat` 直接改成串流回應，所有測試都要重寫。改用「新增一個平行的串流端點」，兩個端點共用同一個 LangGraph、同一套路由/檢索/驗證邏輯，只有「最後生成答案」這一步的呼叫方式不同——`/chat` 照舊阻塞等待完整回答，`/chat/stream` 用 `client.messages.stream()` 逐字回傳。驗證方式很直接：改完之後**完全沒有動任何測試檔案**，25 個測試照樣全過，證明 `/chat` 的行為真的沒被影響到。

**只有 FAQ Node 的「正常生成答案」這一步延後執行**：`qa_node` 原本在自己內部呼叫 Claude 生成 Draft，現在改成回傳 `pending_stream`（組好的 system prompt + messages），把「真的呼叫 Claude 生成文字」這件事交給呼叫它的端點決定要阻塞還是串流。Verifier 判定不足時的轉真人客服分支（回傳 `VERIFIER_ESCALATION_MSG`）維持不變——那本來就是固定文字，沒有生成的必要，也就沒有串流的意義。Account Node 的 tool-calling 迴圈這次刻意沒有處理——迴圈中間每一步都要先看是不是 tool_use 才知道要不要繼續，沒辦法像 FAQ Node 這樣乾脆地「準備好、交給後面串流」，硬做的話範圍會大很多，這次先不碰。

**metadata 用 HTTP Header 傳，不跟文字混在同一個串流裡**：一開始想過在串流結尾夾一個特殊分隔符號、後面接 JSON metadata，但這樣前端要在文字流裡即時偵測分隔符號、還要正確處理分隔符號剛好被切在兩個網路封包中間的邊界情況，複雜度不必要地高。既然 `language`／`workflow`／`is_handoff`／`rag_sources` 這些欄位在 `agent_graph.invoke()` 完成的當下就已經確定（串流只影響「答案文字」怎麼送出，不影響這些欄位何時知道），乾脆放進 HTTP Header——`requests` 這類 client 在串流回應開始時就能立刻讀到 Header，不用等內文流完，前端邏輯簡單很多。Header 必須是 ASCII-safe，`json.dumps` 預設的 `ensure_ascii=True` 剛好符合這個限制，中文字會被跳脫成 `\uXXXX`，不會有 Header 編碼問題。

## ③ Implementation & Iteration

`backend/src/agent/state.py` 新增 `pending_stream` 欄位。`nodes.py` 的 `qa_node` 正常路徑改成回傳 `pending_stream`（不再自己呼叫 `client.messages.create()`）。`main.py` 拆出共用的 `_build_initial_state()` 和 `_finish_pending_stream_blocking()`，`/chat` 用後者把 `pending_stream` 補完成完整回答（跟改動前行為完全一致），新增的 `/chat/stream` 用 `client.messages.stream()` 逐字 `yield`，並把 metadata 放進回應 Header。前端 `frontend/app.py` 改叫 `/chat/stream`，用 `st.write_stream()` 顯示；串流的位元組要手動用 `codecs.getincrementaldecoder("utf-8")()` 逐塊解碼，不能直接用 `requests` 的 `decode_unicode=True`——這個系統幾乎所有回覆都是中文，一個多位元組字元剛好被切在兩個網路封包中間就會亂碼，這個細節不能省。

實測時間：一般高信心問題（跳過 Verifier）現在**首個文字約 2.5 秒內出現**（總生成時間仍要 4 秒左右，但使用者不用整段等完），比 Sprint 12 之前實測的「等 8.9 秒看到全部答案」明顯改善。落在模糊地帶、需要先過 Verifier 的問題，首個文字要等 5 秒左右才出現——這點要誠實承認：串流讓「已經算出答案」的等待感消失了，但「決定要不要生成答案」這個分類+驗證的前置步驟本身還是要花時間，串流沒辦法讓這段完全消失。

## ④ Evaluation & Reflection

這次的範圍決定（新增端點而非改既有端點）是直接從 Sprint 8 建立的測試投資裡拿到的回報——如果沒有那 25 個測試把 `/chat` 的行為釘住，我可能會選擇直接改造 `/chat`，然後花大把時間手動確認每個既有情境有沒有被串流改動波及。有測試在，這次的驗證方式就是「跑一次，看還是不是全過」，把改動的信心建立在真正可重跑的證據上，不是憑感覺。

瀏覽器實測時也剛好印證了一個容易被忽略的細節：`st.write_stream()` 回傳完整拼接後的文字，直接拿來存進 `st.session_state.messages`，不需要額外處理——串流只影響「怎麼顯示」，不影響「存起來的內容長什麼樣」，這個介面設計得剛好，沒有額外的轉換成本。

下一步如果要讓串流更完整，比較明確的候選是：(1) Account Node 的 tool-calling 迴圈也導入串流，需要先想清楚「迴圈中間還在決定要不要呼叫工具」跟「準備好交給前端串流」這兩件事要怎麼共存；(2) 模糊地帶的 Verifier 呼叫，能不能想辦法讓使用者在等待期間也看到一些進度提示（例如「正在確認資料是否足夠...」），而不是純粹的轉圈圈。

---
---

# Sprint 14：Handoff 業務觸發規則

## ① Requirement & Discovery

Phase 5（Sprint 1 之前）寫的 `docs/agent_design.md` §3.5 就列了一條 Handoff 觸發條件「涉及金額爭議 > NT$10,000 的描述」——但從 Sprint 1 到 Sprint 13，這條規則從來沒有真的被實作過，Handoff Node 的觸發條件實際上只有「使用者主動要求真人客服／投訴」跟「連續 3 次 Fallback」兩種。使用者這次直接給了一份完整的業務規則清單（未授權交易/盜刷、帳務爭議/退款、費用減免/貸款核准、敏感資料變更、情緒激動、跨帳戶複雜案件），把這個一直沒兌現的規格補齊，同時大幅超出原本 §3.5 只寫了一條的範圍。

## ② Design Decision

**擴充同一次分類呼叫，不加一次新的 LLM 呼叫**：`classify_intent()` 已經在判斷 `intent`，這次讓同一次 `tool_choice` 強制呼叫多回傳一個 `handoff_category` 欄位（僅在 `intent="handoff"` 時有意義）。這樣新增七種判斷規則的代價是零——不用多一次 API 呼叫，只是同一次呼叫的結構化輸出多一個欄位。

**每個類別各自記一個獨立的 `trigger_reason`，不共用一個籠統的 `handoff`**：使用者主動生氣要求轉真人客服、系統判定疑似盜刷、系統判定需要人工核准貸款——這三件事對負責分類處理的客服團隊來說是完全不同的優先度和處理方式，統計成同一個 bucket 會讓 Dashboard 失去分辨能力。所以設計成 `HANDOFF_CATEGORY_REASON` 對照表，`handoff_urgent_fraud`／`handoff_dispute`／`handoff_approval_required`／`handoff_sensitive_data`／`handoff_emotional_distress`／`handoff_cross_account` 各自獨立記錄，Dashboard 的標籤也一併補上。

**盜刷/詐騙類別用獨立的訊息文字，不是因為技術需要，是業務需求**：使用者的規則寫「立即轉人工，標記為緊急」——「標記」這件事本身已經靠獨立的 `trigger_reason` 做到了，但客戶當下看到的文字如果還是通用的「很抱歉我沒能完全解決您的問題」，讀起來像是 AI 技窮道歉，沒有傳達「這件事被優先處理」的安心感。新增 `URGENT_FRAUD_HANDOFF_MSG`，明確講「已標記為緊急案件」，並提示「如果卡片被盜用，可以直接說『我要掛失』」——把這條規則跟既有的信用卡掛失工作流程連起來，讓使用者不用等真人客服才能先做停用卡片這個當下最要緊的動作。

**信用卡/金融卡遺失或被盜，維持既有的 `card_loss` 意圖，不歸進這批新規則**：使用者原始清單裡有這條，但這已經是從 Sprint 3 就存在、跑得很順的工作流程（驗證身分→選卡→確認掛失→建立服務單），沒有理由改成單純轉真人客服再讓真人客服重新問一次同樣的驗證問題。分類器的 `handoff_category` enum 描述裡明確排除這個情境，避免模型把「我的卡不見了」跟「fraud_or_security」搞混。

**費用減免/貸款申請這類規則，最容易誤判成一般 FAQ，要在 prompt 裡明確畫線**：「信用卡年費怎麼算」是資訊性問題（留在 FAQ），「可以幫我減免年費嗎」是要求核准的動作（轉真人客服）——兩者共用「年費」這個詞，分類器很容易把後者也當成前者處理。在 `handoff_category` 的說明裡针對每個類別都寫了「跟 XX 不同」的對照句（例如 approval_required 明確寫「不同於單純詢問費率/條件」），並且測試時特別設計了成對的正反案例（「信用貸款的利率是多少」該留 FAQ vs「我要申請一筆信用貸款」該轉真人客服）。

## ③ Implementation & Iteration

`backend/src/agent/intent.py` 的 `INTENT_CLASSIFIER_TOOL` 新增 `handoff_category` 欄位（七個列舉值），`classify_intent()` 的回傳值從單純的 `str` 改成 `tuple[str, str | None]`。`nodes.py` 的 `router_node` 解構這個 tuple，用 `HANDOFF_CATEGORY_REASON` 對照表決定 `handoff_reason`；`handoff_node` 依 `handoff_reason` 是否為 `handoff_urgent_fraud` 決定要用哪一則訊息模板。`frontend/pages/1_Dashboard.py` 的兩個 label 對照表補上六個新類別的顯示文字。

`tests/test_router_intent.py` 因為 `classify_intent()` 回傳值改變，既有的 5 個測試斷言都要跟著解構 tuple；新增 8 個測試，七個新類別各一個代表性案例，加上一組刻意設計的正反配對（貸款利率問法 vs 貸款申請問法）驗證分類器真的分得清楚，不是巧合答對。13 個測試（含既有 5 個）第一次跑就全部通過，跑第二次確認穩定。實際打 `/chat` 測了盜刷跟退款爭議兩個案例，確認 `is_handoff=True`、訊息文字正確（盜刷案例用新的緊急訊息、退款案例用原本的 `HANDOFF_MSG`），Dashboard 記錄的 `trigger_reason` 也對得上。

## ④ Evaluation & Reflection

這次最直接的收穫，是看到「先寫規格、隔了 13 個 Sprint 才真正實作」這件事本身沒有造成任何技術債——`docs/agent_design.md` 從 Phase 5 就寫著 Handoff 該有更細的觸發條件，中間 13 個 Sprint 都沒有動它，是因為當時的優先序（先讓核心 Node 邏輯跑通，見 ADR-002）判斷更重要的事先做。等真正要補的時候，因為 Router 的分類器架構（Sprint 9）跟結構化輸出手法（`tool_choice`）都已經是現成的，擴充七個新規則的成本只是「多寫一個欄位的 enum 說明」，沒有要重新設計呼叫方式或加一次新的 API 呼叫。這印證了 ADR-002 當初的判斷是對的：把架構先做對，之後要加規則就是加規則，不用重新蓋一次地基。

比較值得記錄的一個小細節：使用者提供的規則清單裡，「信用卡/金融卡遺失或被盜」跟「連續2-3次問同一題仍未解決」這兩條，其實都已經被既有機制涵蓋（`card_loss` 工作流程、`fallback_threshold`），不需要新增任何邏輯——辨認出「這條規則其實已經做了」跟「這條規則需要新做」同樣重要，避免重複造輪子或誤解既有設計的涵蓋範圍。

下一步如果要讓這套規則更完整，比較明確的候選是：(1) 「需要修改高敏感資料或安全設定」目前是直接轉真人客服，使用者原始描述裡有提到「或二次驗證後」，代表未來也許可以讓部分敏感操作走二次驗證自助完成，不必每次都轉真人客服；(2) `handoff_urgent_fraud` 目前只有文字上標記緊急，沒有實際的優先佇列機制——正式環境應該串接真正的客服工單系統，讓「緊急」這個標記能反映在真人客服看到的排隊順序上。

---

# Sprint 15：真人客服對話（Handoff Conversation）

## ① Requirement & Discovery

使用者先請我列出目前所有功能讓他做一輪人工測試，接著提出這次的需求：「建立一個轉真人客服回覆的對話框，我要有真人客服回覆問題的部份，處理問題的記錄仍要呈現在後台。」

這一句話點出了 Sprint 11（已轉接真人客服 Banner）留下的缺口——Banner 只解決了「讓客戶知道自己被轉接了」，但轉接之後呢？`handoff_node` 回傳的訊息模板講完就結束了，`tickets` 表從 Sprint 4 開始就是 insert-only（Sprint 14 反思裡也提到這件事還沒做），沒有任何機制讓真人客服真的「回覆」客戶，也沒有任何地方讓客戶「看到」真人客服的回覆。這次要補的不是一個 UI 裝飾，是一段完整缺失的資料流：轉接之後的對話要存在哪裡、真人客服在哪裡看、客戶在哪裡收到回覆、案件處理完了要怎麼標記。

## ② Design Decision

在動工前用 `AskUserQuestion` 確認三個會決定整體架構的問題，而不是自己假設：

**Q1：客戶怎麼知道有新回覆？** 選項是「手動按鈕重新整理」vs「自動輪詢（polling）」。使用者選手動按鈕——範圍最小，也不用在 Streamlit 這種非常態連線的框架裡硬做輪詢機制（Streamlit 每次互動都是整個 script 重新跑一次，真正的自動輪詢需要 `st.rerun()` 搭配計時器或 WebSocket，超出這個 demo 該有的複雜度）。

**Q2：轉接後客戶還能問 AI 其他問題嗎？** 選項是「完全鎖定，直到真人客服結案」vs「允許客戶繼續問 AI，真人客服回覆另外顯示」。使用者選完全鎖定——這其實也是比較貼近真實銀行客服的行為：一旦轉接真人客服，客戶不會又跳回去跟機器人聊，而是專心等真人客服處理。這個決定直接簡化了前端邏輯，不用處理「AI 對話串」跟「真人客服對話串」交錯顯示的問題。

**Q3：真人客服要用什麼介面？** 選項是「新增一個獨立頁面」vs「整合進現有 Dashboard 頁面」。使用者選新增獨立頁面——`frontend/pages/1_Dashboard.py` 目前的角色是唯讀的診斷/分析視圖（找知識庫缺口、看轉接趨勢），跟「即時處理案件、回覆客戶」是完全不同的使用情境（一個是事後分析，一個是即時操作），混在同一頁會讓兩者的資訊架構互相干擾。

這三個答案直接決定了整個 Sprint 15 的形狀：**ticket + 對話串（thread）的資料模型**——`tickets` 表記錄案件本身（狀態、優先度），新的 `handoff_messages` 表記錄完整對話紀錄（含轉接前的 AI 對話歷史、觸發訊息、AI 的轉接回覆、之後雙方的每一則訊息），一個共用的 `escalate_to_human()` helper 同時被 `handoff_node`（使用者主動要求）跟 `qa_node` 的核實失敗分支（Sprint 12 的 Verifier 判定知識庫不足）呼叫，避免兩個觸發點各自重複寫一遍建立案件的邏輯。`tickets` 表的 status 也是這次才第一次變得有意義——Sprint 8/11 的日誌就提過它永遠停在 `open`，這次加了 `update_ticket_status()`，`/stats` 的 `open_tickets` 數字終於會隨著案件解決而真的減少。

## ③ Implementation & Iteration

新增 `backend/src/agent/handoff.py`（`escalate_to_human()`），`database.py` 補 `handoff_messages` 表、`get_ticket`/`update_ticket_status`/`add_handoff_message`/`get_handoff_messages`，`get_tickets()` 擴充可選的 `type`/`status` 篩選（維持向後相容，既有呼叫點不受影響）。`main.py` 新增 `/handoff/tickets`、`/handoff/{id}/messages`（GET/POST）、`/handoff/{id}/resolve` 四個端點，`ChatResponse` 跟 `/chat/stream` 的 header 都補上 `handoff_ticket_id`。前端 `frontend/app.py` 用一個 `if handoff_active and handoff_ticket_id` 分支完全取代原本的 AI 對話流程（對應 Q2 的「完全鎖定」決定），新增 `frontend/pages/2_客服人員介面.py` 作為真人客服的獨立頁面（對應 Q3）。

`tests/test_handoff.py` 新增 4 個測試涵蓋案件建立時的對話串內容、雙方往來訊息的順序、狀態篩選、未知案件的 404，加上既有 2 個測試補上 `handoff_ticket_id` 的斷言，全部 37 個測試（33 既有 + 4 新增）第一次跑就全部通過。之後做了完整的瀏覽器操作驗證（非自動化，是實際點擊）：客戶端輸入「我要投訴」觸發轉接、Banner 立即出現在下一次 rerun（第一次 rerun 因為 Streamlit script 是「由上到下執行一次」的模型，設定 `session_state` 的程式碼在畫面判斷式之後，所以要等下一次互動才會真的顯示鎖定畫面跟 Banner——這是 Streamlit 這個框架本身的執行順序特性，不是 bug）、客戶端追加訊息、真人客服頁面看到案件並回覆、客戶端按重新整理看到真人客服回覆、真人客服標記已解決、客戶端重新整理看到「已解決」的成功提示。全程一次到位，沒有出現非預期行為。測試過程產生的真實資料（`T-20260727-001` 這筆 ticket、對應的 4 筆 `handoff_messages`、1 筆 `unresolved_queries`）事後從 `data/banking.db` 清除，沒有留在正式的展示資料庫裡。

## ④ Evaluation & Reflection

這次最有價值的部分不是程式碼本身，是動工前的三個澄清問題——如果沒問，我大概率會做「自動輪詢」（因為技術上比較炫）、「允許客戶繼續問 AI」（因為感覺比較有彈性）、「整合進 Dashboard」（因為省一個新頁面）。這三個都是可以說得通的技術選擇，但都不是使用者真正想要的最小可行版本，也都會讓實作複雜度往上跳一截。這印證了一件事：這種會決定資料模型形狀的分岔路口，寧可先問清楚，不要用「技術上比較完整」當理由自己替使用者做決定。

Sprint 14 反思裡寫的「正式環境應該串接真正的客服工單系統，讓緊急標記能反映在真人客服看到的排隊順序上」，這次算是往前補了一半——真人客服頁面現在會顯示 `優先度：🚨 緊急` 或 `一般`，但只是顯示，還沒有真的把緊急案件排到清單最前面（目前是照 `created_at` 排序）。下一步如果要延續這個方向，比較明確的候選是：(1) `/handoff/tickets` 依優先度排序，緊急案件永遠排最前；(2) 目前客戶端「查看最新回覆」是純手動按鈕，如果要更即時，可以考慮輕量的 polling（例如每次互動順便檢查一次，而不是常駐計時器），但這已經超出這次「範圍最小」的決定，等真的有人反應手動按鈕不夠用再做；(3) 真人客服目前沒有登入機制，任何人都能開啟 `客服人員介面` 頁面處理任何案件——demo 階段沒問題，但若要更貼近真實場景，會需要客服帳號跟案件指派的概念。

---

# Sprint 15 續：真人客服測試修復（2026-08-01）

## ① Requirement & Discovery

延續 Sprint 10 的做法——請使用者親自用前台測試 Sprint 15 剛做完的真人客服功能，而不是只信任我自己的瀏覽器煙霧測試。這次測試回報三個問題：(1) 客戶要求更改基本資料時，AI 回覆「很抱歉我沒能完全解決您的問題」，但這不是 AI 失敗，是政策規定要轉真人客服，語氣不準確；(2) 未登入的訪客觸發轉真人客服時，系統沒有提醒他們可以先登入；(3) 使用者原本希望 Sprint 14 的 9 項業務規則觸發轉真人客服前，強制要求先登入，理由是登入後客服才知道是哪個客戶，不用重頭查詢。

## ② Design Decision

問題 (3) 動手前，我先反問使用者一個安全疑慮：9 項規則裡的盜刷/可疑登入類別本身就是緊急案件，如果帳戶已經被盜用或鎖定，強制客戶先登入才能轉真人客服，反而可能讓真正需要幫助的人卡在登入畫面進不去。使用者聽完這個疑慮後，把原本「強制登入」的要求改成「全部類別都只是軟提醒，不硬擋」——這是本次測試回報中，唯一在動工前又被進一步修正的部分。

三個問題最後的處理方式：
- **問題 (1)**：只改「更改基本資料」（`sensitive_data_change`）這一類的訊息，不擴大到其他政策轉接類別——使用者刻意選了範圍最小的選項，維持「一次回報、一次修復」的節奏，不要在同一輪一次順便重寫所有訊息文字。
- **問題 (2)**：在所有轉真人客服的回覆末端加一句軟性提醒（`LOGIN_REMINDER`），未登入時才顯示，不影響轉接本身是否發生。
- **問題 (3)**：不做硬性擋門，但把使用者原本的訴求（「登入後客服知道是哪個客戶」）用另一個機制達成——如果訪客在轉真人客服「之後」才登入（例如就是看到提醒才去登入），系統會把已經開好的工單自動關聯到他剛登入的身份，客服不用重新驗證。這比「先擋、再開單」多了一個好處：不管訪客最後有沒有登入，工單都不會卡著等待，永遠是「立即開單，身份資訊隨後補上（如果有）」。

## ③ Implementation & Iteration

`nodes.py` 新增 `SENSITIVE_DATA_HANDOFF_MSG`、`LOGIN_REMINDER` 常數與 `_with_login_reminder()` helper，`handoff_node` 依 `handoff_reason` 選對應訊息（盜刷 > 敏感資料變更 > 一般）後一律經過這個 helper；`qa_node` 的 Verifier 轉接分支也套用同一個 helper，讓「AI 主動轉真人客服」路徑一樣有登入提醒。`database.py` 新增 `link_ticket_user()`（只填空的 `user_id`，不覆蓋已存在的值，避免案件被錯誤重新指派給別的帳號），`main.py` 新增 `POST /handoff/{id}/link-user` 端點。`frontend/app.py` 的登入成功處理邏輯拆成兩條路：如果登入當下客戶已經處於轉真人客服鎖定畫面（`handoff_active` 且有 `handoff_ticket_id`），就呼叫新端點關聯身份、**不**重置對話與轉接狀態；否則維持原本「登入即開新對話」的行為。

新增 5 個測試（`test_handoff.py`）涵蓋敏感資料訊息、已登入用戶不顯示提醒、關聯身份成功、關聯不覆蓋既有身份、對不存在工單關聯回 404；既有 4 個測試因為訊息內容多了提醒句而更新斷言，`test_faq.py` 的 Verifier 逃逸測試同樣更新。42 個測試（37 既有 + 5 新增）全部通過。之後做了完整的瀏覽器驗證：訪客觸發轉真人客服 → 確認提醒句出現在畫面上 → 從側邊欄登入 → 確認畫面完全沒有被重置（同一個轉真人客服對話串還在，只是多了登入身分顯示）→ 切到客服人員介面 → 確認「客戶」欄位從「未登入訪客」變成登入後的 `user_id`。過程中產生的測試資料（含一筆意外重複使用到已刪除工單編號的新工單）事後從 `data/banking.db` 清除，過程中特別核對了時間戳與 session_id，避免誤刪使用者自己測試留下的其他工單記錄。

## ④ Evaluation & Reflection

這次比較有意思的是問題 (3) 的處理過程：使用者原始的訴求（強制登入）跟我提出的疑慮（緊急案件不該被登入卡住）表面上互相矛盾，但實際上兩者要的核心結果是一樣的——「客服知道客戶是誰」。找到「工單先開、身份隨後關聯」這個機制之後，兩個看似衝突的目標同時被滿足了，不用二選一。這也印證了在改動使用者明確提出的需求前，先問一句「你要的其實是什麼結果，還是就是這個做法」是值得的——如果我直接照單全收做了硬性登入闸門，反而會在盜刷這個最需要即時處理的情境上引入一個新的風險。

比較小但值得記錄的細節：這次沒有把登入提醒套用到 Handoff 訊息以外的地方（例如 Account Node 的「請先登入」提示），因為那些本來就已經是「因為沒登入所以不能做」的明確阻擋訊息，跟「登入是加分但不阻擋」的 Handoff 情境性質不同，混在一起處理反而會模糊掉兩種訊息各自的語意。

---

# Sprint 16：滿意度評分（CSAT）

## ① Requirement & Discovery

使用者提出一批新需求（滿意度評分、知識庫維護介面、AI 優化真人客服回覆的知識優化流程），這是三個以上、彼此有依賴的 Sprint。分析後發現一個關鍵事實:管線（未來的 Feature C）的原料大多已經備好——「負評」在 `unresolved_queries` 有記錄、「轉真人客服對話含真人客服實際回覆」在 `handoff_messages` 有存（Sprint 15），唯一缺的原料就是「低品質評分」。所以評分不只是一個獨立功能，它是整條知識優化流程的第一塊基石，先做它最合理。

評分本身的需求:每次對話結束後讓客戶評 1-5 分，依分數顯示笑臉/哭臉。

## ② Design Decision

動手前用 `AskUserQuestion` 確認兩個會定義後續架構的岔路:

**評分時機**——聊天機器人沒有明確的「對話結束」點。選項是「對話結束時評一次」vs「每則回覆都能評」vs「兩者都要」。使用者選「對話結束時評一次」，最貼近原始需求，範圍最小。

**KB 儲存**（為了 Feature B/C 先問清楚）——選「新增內容存獨立 DB table，與 markdown 一起索引」，現有 markdown 當「官方知識」不動，UI/AI 新增的補充知識進 `kb_entries`，可追蹤來源/作者/時間、可回溯。這題雖然是 Sprint 17 才用到，但先確認能讓整個藍圖成形。

實作上一個關鍵決定跟 Streamlit 的執行模型有關:**「結束對話並評分」按鈕放在主對話區底部（答案下方），不放在側邊欄**。原因是 Streamlit 的 script 由上到下跑一次，側邊欄在主區之前渲染，而訊息是在主區最後才 append 進 session_state——側邊欄的按鈕會慢一個 rerun 才反映「已經有對話了」。這對 Sprint 15 的轉真人客服 Banner 只是小瑕疵（使用者還會繼續打字，下一輪就顯示了），但對評分按鈕是實質問題:一個滿意、對話已經結束的使用者不會再互動，慢一輪的按鈕對他可能永遠不出現。放在主區、在 append 之後渲染，就能在同一輪、答案正下方立即出現。

低分（≤2）才追問原因（選填文字框），這是動工前給使用者的建議之一——分數只知道「不滿意」，原因才知道「為什麼」，而「為什麼」正是 Feature C 聚類知識缺口的燃料。所以 schema 直接留了 `comment` 欄位並實作條件式追問。

## ③ Implementation & Iteration

`database.py` 新增 `satisfaction_ratings` 表與 `add_rating()`/`get_ratings()`（`get_ratings` 有 `max_score` 參數，讓 Dashboard 只撈低分＋原因），`get_stats()` 擴充 `avg_rating`/`rating_count`/`rating_distribution`。`main.py` 新增 `POST /rating`（驗證 1-5，空白 comment 存成 NULL）與 `GET /ratings`。`frontend/app.py` 新增分數→表情對照（😢😕😐🙂😄）、`render_rating_flow()`、`reset_conversation()` helper（三個重置點共用），評分卡片:五個表情按鈕、選低分才出現原因框、送出後謝謝＋開始新對話。`frontend/pages/1_Dashboard.py` 新增 CSAT 區塊:平均分（帶最接近的表情）、評分則數、低分比例、1-5 分布圖、低分回饋表。

`tests/test_rating.py` 新增 5 個測試（送出反映在 stats、低分＋原因可撈回、max_score 過濾、空白 comment 存 NULL、超範圍分數回 422），全部通過;完整套件 47 個測試（42＋5）全過。瀏覽器實測完整走一遍:打一題 FAQ → 答案下方出現「結束對話並評分」→ 點 😢（1 分）→ 原因框出現 → 填原因送出 → 謝謝畫面 → 後端確認評分與原因入庫 → Dashboard CSAT 區塊正確顯示平均、分布、低分回饋表。過程中發現並修掉了「按鈕慢一輪」的問題（見上），測試資料事後從 `data/banking.db` 清除。

## ④ Evaluation & Reflection

這次最值得記錄的不是評分功能本身（它很單純），而是**辨認出它在更大藍圖裡的位置**。使用者一次丟了三個大功能，很容易急著全做;先停下來看資料流，發現「其實只缺評分這一塊原料，其餘管線的輸入前面幾個 Sprint 都存好了」，就能把一個看似龐大的需求拆成「先補這一小塊、後面自然接得上」。這也回頭印證了 Sprint 15 把真人客服回覆完整存進 `handoff_messages`（而不是只存最後一則）的價值——當時是為了讓客服有上下文，現在這份完整轉錄剛好成了 Feature C 生成 FAQ 草稿的直接輸入。

「按鈕放哪」這個看似 UI 細節的決定，其實是被 Streamlit 的執行順序模型逼出來的正確答案——同樣一個「慢一輪」的特性，在 Banner 上可以忍、在「結束就評分」上不能忍，因為兩者對「使用者是否還會再互動」的假設相反。把框架特性跟功能語意擺在一起看，才會發現該不該忍。

下一步（Sprint 17）是 KB 維護介面:`kb_entries` table、可放入 data 的 UI、以及最關鍵的「新增後熱重建 FAISS 索引並讓 retriever 立即生效」。之後 Sprint 18 才是把評分低分＋負評＋轉真人客服對話聚類、生成草稿、審核入庫、追蹤成效的完整管線。

---

# Sprint 17：知識庫維護介面 + 熱重建索引

## ① Requirement & Discovery

使用者三大需求的第二塊:當 chatbot 的知識庫不完整時，要能新增知識來加強回覆——需要一個維護知識庫的介面，能「放入 data」。這是 Feature C（AI 優化真人客服回覆入庫）的前置:C 的「一鍵審核入庫」要有個「庫」可以寫進去、而且寫進去要能生效。所以先把「人可以手動維護 KB、而且立即生效」這條路打通，C 之後只是把「人手動新增」換成「AI 生成草稿、人審核後新增」，走的是同一條入庫管線。

發現的核心技術問題:目前 KB 是 `data/knowledge_base` 的 markdown，開機時由 `build_index.py` 建成 FAISS 索引、`main.py` startup 載入 retriever 各一次。新增知識後，索引不會自己更新——要嘛重跑 `build_index.py` 再重啟 server，要嘛想辦法讓它「熱重建」。對一個要給非工程人員用的維護介面來說，「改完要重啟後端」是不能接受的。

## ② Design Decision

**KB 儲存用獨立 DB table，不直接改 markdown**（Sprint 16 動工前就跟使用者確認過的岔路）:現有 markdown 當「官方知識」維持不動，UI/AI 新增的進 `kb_entries` table，索引時兩者合併。理由:(1) 每條補充知識要帶 source（manual/pipeline）、status、時間戳，markdown 檔存不了這些治理資訊;(2) archive 當軟刪除就給了回溯路徑（改壞了、AI 生成的草稿事後發現不好，都能封存退回，不必真的刪檔）;(3) UI 直接編輯檔案脆弱、容易誤改既有內容。

**熱重建 + 就地熱抽換 retriever**，這是這個 Sprint 的技術重點。關鍵發現在讀 `nodes.py` 時:`make_qa_node(client, retrievers, ...)` 的閉包抓的是 `retrievers` 這個 **dict 物件**，而 qa_node 每次執行時才 `retrievers.get(language)` 去取當下的 retriever。所以只要在同一個 dict 物件裡把值換掉（`retrievers[lang] = RAGRetriever(...)`），正在跑的 graph 下一次呼叫就會拿到新的 retriever——不需要重建 graph、更不需要重啟 server。`POST /kb/reindex` 就是:重新組 docs（markdown + active kb_entries）→ 重算向量寫回索引檔 → 就地換掉 `retrievers` 的兩個值。因為 uvicorn 的 `--reload` 只監看 `.py` 檔、不看 `.index`/`.json` 資料檔，寫索引不會觸發 reload，熱抽換在同一個 process 裡穩定生效。

**全量重建而非增量**:每次 reindex 都把整個索引（所有 markdown + 所有 active entries）重算。對 demo 規模（幾十個 chunk）這只是幾秒的重算成本，換來的是正確性——增量 append 向量雖然可行（`IndexFlatIP.add()`），但封存/編輯造成的刪改要維護 meta 對齊很容易出錯。生產環境 KB 大時才需要考慮增量或快取，這裡刻意選簡單且正確的做法。

**附一個「測試檢索」工具**:維護介面裡可以輸入問題，看目前索引檢索到什麼、相似度多少，並用 🟢/🟡 標示有沒有跨過 0.60 信心門檻。這直接對應到之前給使用者的建議——「新增後不用等 N 天，把原本答不出來的問題重丟進新索引，看分數有沒有跳上門檻」就是入庫成效的即時證明，也是 Feature C 成效追蹤的雛形。

## ③ Implementation & Iteration

`database.py` 新增 `kb_entries` 表與 CRUD（create/get/update/set_status，archive 與 restore 共用 set_status）。`build_index.py` 重構:`load_documents` 拆成 `_markdown_docs` + `_kb_entry_docs`，合成 `assemble_docs(language)`;kb_entry 的 title＋content 一起嵌入（title 帶問句措辭幫助檢索命中，content 是 FAQ Node 要 grounding 的答案），title 同時當 source 讓前端「參考來源」讀起來自然;新增 `reindex_all()`，不傳 model 時重用 retriever 已載入的嵌入模型單例，所以從 app 內呼叫只是重算成本、不是重新載入模型。`main.py` 新增 `/kb/entries`（POST/GET/PUT）、`/kb/entries/{id}/archive`＋`/restore`、`/kb/reindex`（重建＋熱抽換）、`/kb/retrieve`（測試工具）。前端新增 `pages/3_知識庫維護.py`:新增表單、重建按鈕、現有條目清單（可編輯/封存、可切換顯示已封存並復原）、測試檢索工具;順手把 Dashboard 那段還在講「跑 build_index.py 重建」的舊提示改成指向新頁面。

`tests/test_kb.py` 新增 5 個測試:CRUD 全生命週期、驗證（語言限 zh/en、空白 title/content 擋掉）、未知 id 404、語言隔離、以及 `assemble_docs` 正確合併 markdown＋active entry 且排除 archived（純函式、不嵌入、不碰真實索引）。**刻意不在 pytest 裡跑真正的 reindex**——它會重算向量並覆寫真實的 `data/faiss_index`，而整個測試套件其他檢索測試都依賴那份真實索引。全部 52 個測試（47＋5）通過。

熱重建則用 curl 實測（因為它會動到真實索引檔）:先確認「可以預約分行的貴賓理財專員嗎」這題目前最高分 0.547（低於 0.60，會走 verifier）→ 新增一條答這題的 kb_entry → `POST /kb/reindex` → 同一題重檢索，最高分跳到 **0.830**（來源是新條目的標題）→ 再打 `/chat`，確認 `is_handoff=False`、直接用新知識回答、不再逃逸。之後瀏覽器實測維護頁面:表單、重建按鈕、條目清單、測試檢索工具（用另一種問法「有理財專員可以談嗎」檢索，得 0.595、🟡 正確標示剛好在門檻下）。測試結束後刪掉測試 kb_entry 並再 reindex 一次，把真實索引還原成 markdown-only（zh 從 11 回到 10 chunk，同一題檢索分數回到原本的 0.547），確認沒有殘留。

## ④ Evaluation & Reflection

這個 Sprint 最漂亮的地方是「熱抽換」那個發現——它不是靠加一個複雜的 reload 機制，而是靠**看懂既有程式碼的閉包語意**:qa_node 早就是每次 call 才 `retrievers.get(language)`，所以「就地換 dict 的值」這個最簡單的做法本來就會被正在跑的 graph 看到。如果沒讀懂這點，很可能會去做「重建整個 graph」或「加一個全域 flag 讓 node 每次檢查要不要 reload」這類更重的東西。這再次印證，動手加機制前先把既有資料流看清楚，往往能發現「其實不用加那麼多」。

另一個值得記錄的取捨是測試邊界。真正的 reindex 因為會覆寫全域唯一的真實索引、且要跑嵌入模型，硬放進 pytest 會既慢又危險（污染其他測試依賴的索引）。所以把可測的純函式部分（`assemble_docs` 的合併/排除邏輯）單獨抽出來測，重的部分用 live 驗證——這跟前面幾個 Sprint 對「LLM 依賴的部分不寫進斷言、用 live 驗證」是同一個判斷原則:測試要測「邏輯對不對」，不是把整條重管線硬塞進單元測試。

下一步 Sprint 18 就是把三塊接起來的完整管線:把 Sprint 16 的低分評分＋既有的負評（`unresolved_queries`）＋轉真人客服對話（`handoff_messages` 含真人客服實際回覆）聚類成「待補知識主題」，用對話上下文＋真人客服回覆生成 FAQ 草稿，客服一鍵審核後透過這個 Sprint 打通的入庫管線寫進 `kb_entries` 並重建索引，最後用「入庫前後該主題的轉真人客服/負評率」＋「即時檢索分數」量化成效。

---

# Sprint 18：知識優化流程（聚類 → 草稿 → 審核入庫 → 成效追蹤）

## ① Requirement & Discovery

使用者三大需求的壓軸:把「人工回覆的內容，由 AI 優化後生成回覆話術並放入 chatbot」，拆成四塊——自動聚類（低分/負評/轉真人客服對話 → 待補主題）、草稿生成（對話上下文＋真人客服回覆 → FAQ 問答＋標籤）、一鍵審核入庫（核准/編輯/略過）、成效追蹤（入庫前後解決率變化）。這是把前兩個 Sprint 備好的東西接起來:Sprint 16 的低分評分、既有的負評（`unresolved_queries`）、Sprint 15 存下的真人客服對話（`handoff_messages` 含真人客服實際回覆）都是輸入;Sprint 17 打通的 `kb_entries` 入庫 + 熱重建是輸出。這個 Sprint 只是中間那段「把訊號變成可入庫草稿」的智慧。

## ② Design Decision

**聚類用 LLM 主題分群，不用 embedding 分群**（動工前先跟使用者講過）:這個規模（十幾筆訊號）用 k-means/HDBSCAN 要選 k、群沒名字還要再命名、小資料不穩;直接一次 `tool_choice` 強制呼叫，回傳「主題＋成員＋代表問句」，自帶命名、可解釋、小資料也穩，跟 `classify_intent`/`verify_chunks_sufficient` 同一手法。生產環境上千筆才需要換 embedding 分群（見 ADR-013）。

**一個關鍵的正確性護欄:`kb_actionable`**。使用者原始需求把「轉真人客服對話」列為聚類來源，但**不是每個轉真人客服都是知識缺口**——「我要改聯絡電話」是政策上必須真人客服處理的正確轉接，把它變成自助 FAQ 是錯的（而且有風險）。所以聚類的每個主題都要 LLM 判斷 `kb_actionable`:只有「加一篇知識庫文章就能自助解決」的資訊性問題才為真;需要人工裁量的（費用減免、資料/安全變更、盜刷、爭議、投訴、核准）為假、不生成草稿。實測 14 筆訊號分成 7 個主題，只有 3 個是 kb_actionable，其餘 4 個政策類被正確排除——這條護欄直接對應到 Sprint 12/14 一路以來「該轉真人客服的就該轉真人客服，不要硬答」的原則。

**用「目前檢索得到嗎」當缺口過濾器，順便當成效指標**。聚類前，每筆訊號先用當前索引檢索一次:已經被 KB 答得好（top score ≥ 0.60）的就不是缺口、剔除。這一個設計同時解決三件事:(1) 已入庫的主題下次分析自動不再出現（不用另建去重表）;(2) 定義了「什麼叫解決」——代表問句檢索分數跨過 0.60 門檻;(3) 成效追蹤因此有了乾淨的量化錨點:入庫前分數 vs 入庫後分數。至於「略過」的主題會一直答不好、每次都重新冒出來，所以 skipped 草稿要記住、用嵌入相似度把相近的新訊號濾掉。

**草稿生成強制去識別化**:真人客服的實際回覆常含客戶個資，草稿 prompt 明確要求「改寫成通用 FAQ、移除個人資料、不得捏造未提供的費率數字」。實測「今日美金匯率」這題，草稿正確地沒有編一個匯率數字，而是導向即時查詢管道——因為官方 KB 的外幣文件本來就有即時匯率 URL，草稿 grounding 在既有事實上。

**成效追蹤的量化指標 = 檢索信心 before/after**，不是抽象的「解決率」。核准入庫後立刻重算代表問句的檢索分數:實測 0.531 → 0.700，跨過門檻。這是當場、可量化、不用等 N 天的證明。另加一個「入庫後同類問題是否再發生」（用嵌入相似度比對入庫時間後的 unresolved）當長期輔助指標。

## ③ Implementation & Iteration

`database.py` 新增 `kb_gap_drafts` 表（topic/question/answer/tags/representative_query/signal_summary/signal_count/status/pre_score/kb_entry_id）與 CRUD、`clear_pending_gap_drafts`、`get_skipped_representative_queries`、`get_unresolved_since`（成效用）。`backend/src/agent/gap_pipeline.py`:`gather_signals`（拉 unresolved〔verifier/negative/fallback〕＋低分評論＋有真人客服回覆的轉真人客服對話，用檢索過濾已答＋嵌入排除略過）、`cluster_gaps`（`CLUSTER_TOOL`，含 kb_actionable）、`write_faq_draft`（`DRAFT_TOOL`，去識別化）、`analyze`（清 pending → gather → cluster → 對 actionable 主題生草稿 → 存 pre_score）、`count_recurrence`。`main.py`:`/gap/analyze`、`/gap/drafts`（GET/PUT）、`/skip`、`/approve`（建 kb_entry source=pipeline → 重建熱抽換 → 回傳 pre/post 分數）、`/effectiveness`;把 Sprint 17 的重建邏輯抽成共用的 `_rebuild_and_swap_index()`。前端 `pages/4_知識優化流程.py`:分析按鈕、待審核草稿卡（可編輯、核准/略過）、已入庫成效區（入庫前/目前信心＋delta＋再發生數＋跨門檻提示）、已略過摺疊區。

`tests/test_gap.py` 新增 4 個測試:草稿列出/編輯、略過移出 pending、編輯驗證、未知 id 404——刻意只測確定性的審核 plumbing，**不在 pytest 裡跑 analyze（LLM 不確定）或 approve（會覆寫真實索引）**，跟 Sprint 17 同一條測試邊界。56 個測試全過（52＋4）。

完整管線 live 驗證:`POST /gap/analyze` → 14 筆缺口訊號 → 7 主題 → 3 份 actionable 草稿（4 個政策主題被 kb_actionable 正確排除）→ 草稿內容檢查（「今日美金匯率」正確導向查詢管道、沒編數字）→ 核准 draft #2 → **pre 0.531 → post 0.700**（跨門檻）→ `/chat`「今日美金匯率多少？」確認 `is_handoff=False`、直接回答 → 成效端點回傳 pre/live/recurrence → 瀏覽器實測整頁（草稿卡、成效指標、跨門檻綠色提示都正確渲染）。測試後刪掉 kb_gap_drafts 與 pipeline kb_entry、再 reindex 還原成 markdown-only（zh 回到 10 chunk、該題檢索回到 0.554），並保留使用者自己累積的 unresolved/handoff 原始資料不動。

## ④ Evaluation & Reflection

這個 Sprint 把整個專案收成一個閉環:**AI 答不好 → 轉真人客服 → 真人客服回覆被存下來 → AI 把真人客服回覆變成 FAQ → 客服審核入庫 → 同樣的問題 AI 以後自己答得出來**。每一環都是前面某個 Sprint 鋪好的，Sprint 18 只是把最後一段智慧補上——這也回頭證明了前面幾個看似獨立的決策（Sprint 15 存完整轉錄而非最後一則、Sprint 16 低分追問原因、Sprint 17 KB 存 table 且可熱重建）其實都在為這個閉環鋪路。

最重要的設計判斷是 `kb_actionable` 這條護欄。使用者的需求字面上是「把轉真人客服對話聚類」，但照字面全做會把「改電話號碼」這種必須真人客服的操作變成公開 FAQ——那是把 Sprint 14 好不容易建立的「該轉真人客服就轉真人客服」原則給拆了。辨認出「來源要廣、但入庫要嚴」，讓 LLM 在聚類時就分辨「這是知識缺口，還是正確的轉接」，是這個管線不會製造錯誤自助知識的關鍵。這再次呼應整個專案反覆出現的主題:照字面實作需求之前，先想清楚「這個做法會不會破壞別的地方已經做對的事」。

成效追蹤這塊，我刻意沒有做成一個會唬人的「解決率儀表板」，而是釘在一個誠實、可當場驗證的量化事實上:代表問句的檢索信心從門檻下跨到門檻上。「解決率」聽起來漂亮但需要定義、需要時間、容易造假;「這題本來檢索 0.53 答不好、入庫後 0.70 答得好、而且入庫後沒再有人問倒」是每一步都能被獨立驗證的。給 demo 一個能當場證明、經得起追問的數字，比給一個好看但說不清怎麼算的數字重要。

生產環境的延伸很明確:聚類上千筆時換嵌入分群或先粗篩;approve 目前逐筆重建索引，批次核准應該收斂成一次重建;`kb_actionable=false` 的政策主題目前只是排除，其實可以回饋去補強 Router 的轉真人客服規則或人力配置分析;成效的「同類再發生」目前用固定相似度門檻，可以再校準。

---

# Sprint 19：即時對話更新 + 訪客轉接前資料收集 + 橫向圖表

## ① Requirement & Discovery

使用者手動測試後回報三件事:(1)「當客戶回覆後，客服介面多久會更新？看畫面一直無更新」;(2) Dashboard 直條圖的中文標籤方向不對，要統一改橫向;(3) 未登入的使用者若直接要找客服，應該先問「您是 1. 銀行帳戶客戶 2. 信用卡客戶 3. 非本行客戶？」並請對方簡單描述問題。

第一題的答案其實是「永遠不會自動更新」——Streamlit 的 script 只在互動時才重跑，Sprint 15 的客戶端還放了一顆「🔄 查看真人客服最新回覆」要人自己按，客服端則連按鈕都沒有。這在單人 demo 時看不出來，一旦兩邊同時開著就變成致命傷:客服回了、客戶不知道;客戶回了、客服畫面停在上一輪。

第三題的動機跟 Sprint 15 續的登入提醒是同一條線:讓接手的專員一坐下就知道「這是誰、要問什麼」。登入提醒解決「是誰」，但訪客不一定願意登入;而「我要找真人客服」這句話本身完全沒有資訊量，開出來的工單說明只有「轉真人客服：使用者主動要求真人客服」，專員還是得從零問起。

## ② Design Decision

**自動更新用 `st.fragment(run_every=...)`，不是整頁 auto-rerun。** 這是這個 Sprint 最重要的判斷。整頁自動 rerun 最直覺（`st_autorefresh` 之類），但它會**清掉客服正在打到一半的回覆**——一個每 5 秒清空輸入框的客服系統比不會自動更新更糟。fragment 只重跑被標記的那一塊，輸入框和選到一半的案件都不受影響。相對地要付出兩個限制:`st.chat_input` 放進 fragment 會失去釘在底部的版位，所以刻意留在外面;fragment 內的按鈕要用 `st.rerun(scope="app")` 才能跳出 fragment（客戶端「為這次服務評分」就是這種情況）。

**案件佇列只提示、不自動切換。** 對話串 5 秒更新，新案件則 15 秒檢查一次、只顯示「🔔 待處理案件有變動，重新整理後可看到」＋一顆按鈕。如果自動重整列表，會在客服正在回覆某案件時把選中的案件抽掉——同樣是「自動化不該搶走使用者手上的東西」。

**轉接的那一輪就切進真人客服對話畫面。** 順手修掉一個 Sprint 15 就存在、但在「畫面不更新」的抱怨下才浮出來的問題:Streamlit 由上而下跑一次，畫面分支在開頭就決定了，所以「這一輪才觸發轉接」時使用者仍停在 AI 輸入框，要再送一則訊息才會進真人客服畫面——而此時客服端早就收到案件了。在 handoff 觸發後補一次 `st.rerun()`，不會掉任何訊息（`escalate_to_human()` 已經把這則回覆寫進對話串了）。

**訪客轉接前資料收集只用在「主動要求真人客服」這一類。** 使用者的字面需求是「未登入的 user 若直接要找客服」，實作時把範圍收得更緊:只有 `explicit_request` 且未登入才問。理由是其他類別都不該被表單擋——盜刷、爭議、敏感資料變更的觸發訊息**本身就寫著問題是什麼**，再問一次是重複;而已登入的客戶身份早就掛在工單上，問「您是哪種客戶」純粹是摩擦。這跟 Sprint 15 續拒絕「硬性登入門檻」是同一個原則:**收集資訊的價值必須大於它造成的延遲，急件優先。**

**表單不能變成迴圈。** 收集流程最多問兩輪，兩輪後不管收到什麼都照樣轉接（客戶類別記成「未指明」）。一個已經開口要真人客服的客戶，最糟的體驗就是被機器人卡在填表迴圈裡。另外「取消」隨時可退回一般 AI 對話，兩個半題（類別、描述）分開累積——回答「1」之後只會被追問描述，不會把已經給的答案丟掉重問。

**Dashboard 圖表改用 Altair 而非 `st.bar_chart(horizontal=True)`。** 先用內建參數改成橫向，實測發現兩個問題:y 軸標籤被截成「🔍AI 判定知識…」，而且軸標題本身還是被轉 90 度的中文。改用 Altair 才能設 `labelLimit`、拿掉軸標題、並用 `alt.Step` 讓圖高隨列數成長（固定高度時 Vega 會為了避免重疊**默默丟掉**標籤——實測 4 個類別只顯示 2 個）。刻度也釘成整數，否則資料只有 1 筆時 Vega 會產生 0/0.5/1 三個刻度、`format="d"` 把它們印成「0 1 1」。

## ③ Implementation & Iteration

後端新增 `handoff_intake_node`（`backend/src/agent/nodes.py`）與對應的 graph 節點。Router 的兩處改動:`workflow_step > 0` 時用 `workflow_data["type"]` 區分掛失流程與資料收集流程（掛失流程本來就沒有 `type` 鍵，天然相容）;`explicit_request` ＋未登入 → `intent="handoff_intake"`。收集流程用既有的 `workflow` 欄位在前後端來回，不需要新的 state 欄位或前端改動。`_parse_customer_type()` 支援半形/全形數字、括號、以及用文字描述（「我是信用卡客戶」）——「非本行」關鍵字刻意排在信用卡/帳戶之前，否則「我不是本行客戶，想問信用卡」會被判成信用卡客戶。`escalate_to_human()` 加一個 `intake` 參數:客戶類別與描述寫進工單 description（佇列那一行就能分流），並以結構化區塊寫進對話串（專員不用往上捲）。

前端:`frontend/pages/2_客服人員介面.py` 把對話串包進 `@st.fragment(run_every=5)`、案件佇列 watcher 包進 `run_every=15`，加一個可關閉的「自動更新」開關;`frontend/app.py` 的真人客服對話畫面同樣包成 fragment，並在 handoff 觸發後補 `st.rerun()`。`frontend/pages/1_Dashboard.py` 把兩張圖換成共用的 `horizontal_bar()` helper。

測試:`tests/test_handoff.py` 因為訪客路徑從一輪變兩輪，改用共用的 `guest_escalate()` 驅動;新增 4 個測試（先問不開單、答完帶著類別＋描述開單、可取消、已登入者跳過收集）。59 個測試全過（56＋4 新增，原本的 explicit_request 測試改寫成上述兩個）。

Live 驗證走完整流程:訪客問「我想找真人客服幫忙」→ 收到 1/2/3 選單 → 只回「1」→ 只被追問描述（沒有重問類別）→ 回「我的網銀轉帳一直失敗」→ **同一輪就切進真人客服對話畫面**，對話串裡有「📋 轉接前資料收集：客戶類別/問題描述」→ 客服端不用任何操作就看到新案件與完整脈絡 → 客服回覆 → **客戶端 5 秒內自己冒出來** → 客戶再回覆 → **客服端自己冒出來** → 客服標記已解決 → 客戶端自動出現已解決提示與評分按鈕 → 評 5 分 → Dashboard CSAT 橫向圖表正確渲染。

## ④ Evaluation & Reflection

「多久會更新？」這個問題的正確答案是「不會」，但更值得記下來的是**為什麼之前沒發現**:Sprint 15 的驗證是我自己在兩個分頁間切換、每次切過去都會觸發互動，所以畫面「看起來」總是最新的。測試者的操作習慣（切過去就按東西）遮住了真正的使用情境（開著等對方回覆）。真人客服系統的預設狀態是「兩邊都在等」，這正是 script-rerun 模型最不擅長的狀態。

fragment vs 整頁 rerun 這個選擇，表面上是 Streamlit API 細節，實際上是一個產品判斷:**自動化不能破壞使用者當下的操作**。整頁 rerun 每 5 秒清空輸入框，功能上「有自動更新」，體驗上完全不能用。同樣的判斷也出現在「新案件只提示不自動切換」上。

訪客資料收集則是又一次「照字面實作前先想清楚範圍」。使用者說的是「未登入的 user 若直接要找客服」，全套照做的話會變成每個轉真人客服（包含盜刷）都先跳表單——把 Sprint 14 特地為緊急案件設計的「立即轉接」給抵銷掉。收窄到「主動要求真人客服且未登入」，才是既滿足需求、又不破壞既有正確行為的解。這跟 Sprint 18 的 `kb_actionable` 護欄是同一種思考。

圖表那題則是個提醒:「改成橫向」聽起來是一個參數的事，但真正要交付的是「標籤看得懂」。內建參數確實把圖轉了 90 度，卻同時帶來截斷、標籤被默默丟掉、刻度重複三個新問題——如果只改參數就交，等於把一個問題換成三個更難發現的問題。動手改完一定要**打開來看**。

生產環境的延伸:5 秒輪詢在多人同時使用時會變成可觀的請求量，正式環境應該換 WebSocket 或 SSE 推播;資料收集目前用規則解析 1/2/3，選項若增加或客戶用更自由的說法回答，可以換成一次輕量的 LLM 抽取（跟 `classify_intent` 同一手法）;客戶類別目前只寫進工單說明，之後可以拿來做真正的分流路由（不同類別派給不同組別）。

---

# Sprint 20：常見問題快捷路徑（起始捷徑 + 依主題延伸的追問）

## ① Requirement & Discovery

使用者需求:「在對話框中，bot 提供常見問題快捷路徑，讓客戶可以立即點選。並依據客戶詢問的問題延伸可能會詢問的問題來建立問題捷徑。」拆成兩件事——**空白對話時的起始捷徑**（客戶不知道能問什麼），和**每次回答後的延伸追問**（客戶知道還想問，但懶得打字）。

動手前先確認一件事:捷徑的價值在於「省下打字」，但它的風險在於**點下去答不出來**。客戶自己亂問答不出來，那是知識庫的極限;照著我們給的按鈕點卻被轉真人客服，那是 chatbot 自己造的死路——而且會讓人覺得這個 bot 連自己推薦什麼都不知道。所以整個功能的設計約束只有一條:**只提供保證答得出來的題目**。

## ② Design Decision

**題庫人工策劃 + 執行期可答性過濾，不用 LLM 生成。** 最直覺的做法是每輪多打一次 LLM「請根據這次對話生成 3 個相關問題」。否決的理由是 LLM 會生出「看起來很合理但知識庫沒內容」的題目，而且要在客戶正在等回覆時多花一次模型往返。改成:題庫人工寫（依知識庫來源檔分組），每個候選在顯示前對當前索引跑一次檢索，**分數沒過 FAQ Node 那條 0.60 信心門檻就不顯示**。這條線正是既有程式用來決定「直接回答」還是「交給 verifier 覆核（可能轉真人客服）」的同一條線，直接複用、不另外發明信心定義。

**一開始的假設被實測推翻，這是這個 Sprint 最重要的一段。** 原本的想法很漂亮:知識庫每個檔案都有 `## 常見問題` 段落，裡面現成的 `**Q：…**` 就是「知識庫保證答得出來的題目」，直接抓來當捷徑即可，零維護成本。實際跑一遍才發現不成立——**抽 5 題實測，4 題轉真人客服**:「年費已扣款，可以退費嗎？」「轉錯帳號了怎麼辦？」被 Router 正確判成退費/爭議類轉真人客服（那是對的路由，只是不適合當自助捷徑）;「定存到期會自動續存嗎？」「收不到 OTP 怎麼辦？」則是檢索命中錯誤檔案、verifier 判定資料不足。掃描全部 62 題，中文 31 題有 19 題、英文 31 題有 23 題分數低於門檻。

**「知識庫裡有寫」不等於「chatbot 答得出來」**——這句話寫下來很像廢話，但它推翻的正是我原本自認很聰明的設計。

**過濾放在執行期而不是寫死清單。** 知識庫會變:新增知識，更多捷徑自動亮起來;封存知識，依賴它的捷徑在下次重建索引後自動消失，而不是留著變死路。清單因此會隨知識庫一起維護，不需要人記得回來改。成本是每個候選一次 embedding 編碼，依索引版本快取，並在啟動與 reindex 後預熱——**回應路徑上零額外 LLM 呼叫**。

**追問從「這次實際檢索到的來源」延伸**，順序即相關性順序。該主題沒有可用題目時（例如只命中維護介面新增的 kb_entry，那些沒有策劃題庫）退回熱門起始題——一個「別的主題但能用」的捷徑，仍優於空白或死路。

## ③ Implementation & Iteration

新增 `backend/src/agent/suggestions.py`:`TOPIC_FOLLOWUPS`（依來源檔的策劃題庫）、`FAQ_STARTERS`、`ACCOUNT_SUGGESTIONS`、`_answerable`（檢索門檻過濾＋快取）、`suggest_followups`、`starters`、`account_followups`。`qa_node` 回傳 `suggestions`（在生成前算好，才能搭 `/chat/stream` 的 header 一起送出，那些 header 在第一個 token 之前就發出去了）;`account_node` 回傳帳務追問。`main.py` 新增 `GET /suggestions`（起始捷徑）、`ChatResponse.suggestions`、`X-Suggestions` header，並在 startup 與 `_rebuild_and_swap_index()` 後預熱/清空分數快取。前端 `render_suggestions()` 把題目畫成一排按鈕，`on_click` 回呼把題目寫進 `pending_suggestion`，下一輪當成一般輸入處理——**點按鈕和自己打字走完全同一條路徑**。

實測驅動的三次修正:
1. **策劃題庫本身也被實測砍過**。先寫候選、跑分數、把「分數沒過門檻」或「命中錯誤檔案」的刪掉或改寫。例如中文「定期存款利率是多少？」最高分命中 `loan_overview.md`（貸款利率，不是存款利率），直接刪掉而不是硬留。
2. **帳務追問刪掉兩題**:「我的信用卡額度還剩多少？」（Account Node 根本沒有查額度的 tool，只會回帳單＋道歉）、「繳款截止日是什麼時候？」（單獨問會被分類成 FAQ 而非 account，然後轉真人客服）。兩題讀起來都非常合理——正因如此才必須實測，不能憑直覺寫。
3. **近似題過濾從單邊重疊率改成 Jaccard**。中文問句共用大量虛字（我/的/是/多少），單邊比率把「我的帳戶餘額還有多少？」誤判成「我這個月帳單多少」的重複而藏起來;改用聯集當分母後，8 個邊界案例（4 個該排除、4 個該保留）全部正確。

驗證:全部 33 題 FAQ 捷徑（中文 22＋英文 11）逐題打真實 `/chat`，**全部 `is_handoff=False` 且有檢索來源**;帳務 3 題用正確的 `user_id` 實測都答出真實資料。瀏覽器實測:起始捷徑 → 點「信用卡年費」→ 答出年費表 → 追問變成「國外刷卡手續費 / 預借現金 / 帳單分期」→ 再點 → 正常接續。新增 `tests/test_suggestions.py` 10 個測試（69 個全過），其中 `test_every_curated_faq_suggestion_clears_the_threshold` 是這個功能的保命符:知識庫改動讓哪一題失效，它會直接指出來。

## ④ Evaluation & Reflection

最值得記的是那個被推翻的假設。「從知識庫的 FAQ 段落抓題目」在紙上完全說得通——資料就在知識庫裡、零維護、自動同步——我甚至先把整個模組照這個想法寫完了。真正讓它站不住的不是更好的推理，是**跑了 5 個真實請求**。如果沒跑，這功能會帶著「4/5 機率點下去被轉真人客服」的缺陷出貨，而且因為程式碼看起來很合理，code review 也不會發現。

第二點:**這功能的難處不在「怎麼做出來」，在「怎麼保證它不會騙人」**。畫幾顆按鈕、把題目送出去，一小時就能寫完。真正花時間的是那條「只顯示答得出來的題目」的護欄，以及為了證明它成立而跑的 33 次逐題實測。這跟 Sprint 18 的 `kb_actionable` 是同一種工作:功能本身很快，讓它不製造錯誤的東西才是主體。

第三點:**執行期過濾比人工維護清單更誠實**。我大可以測完就把通過的題目寫死，程式更簡單。但那樣的清單在知識庫改動後會靜靜地爛掉，而且爛的方式最糟——顯示一個看起來正常、點下去卻進轉真人客服流程的按鈕。讓它每次都對當前索引檢查一遍，等於把「這個承諾還成立嗎」變成執行期的事實，而不是寫程式當下的假設。

順帶發現兩個既有問題（本 Sprint 未處理，已記錄）:Account Node 沒有查詢信用卡剩餘額度的工具;中文知識庫每個 markdown 檔目前被切成一整個 chunk（`CHUNK_SIZE` 以「詞」計，中文沒有空格可切），導致主題解析度粗糙——「跨行轉帳手續費」的最高分來源會是 `foreign_currency_exchange.md` 而不是 `transfer_rules.md`。後者是這次題庫策劃時好幾題被刷掉的根因，值得單獨開一個 Sprint 處理中文 chunking。

---

# Sprint 21：中文切塊修復（標題感知 + CJK 感知）

## ① Requirement & Discovery

Sprint 20 策劃捷徑題庫時，量測結果透露出一個更底層的問題:好幾題明明知識庫裡寫得清清楚楚，卻檢索不到正確的檔案——「跨行轉帳手續費」的最高分來源是 `foreign_currency_exchange.md`、「定存利率」命中 `loan_overview.md`（貸款利率，不是存款利率）、「收不到 OTP 簡訊怎麼辦」直接被轉真人客服。當時把它記成待辦，這個 Sprint 處理。

根因只有一行程式:

```python
CHUNK_SIZE = 400   # words per chunk
words = text.split()
```

**中文沒有空格，所以整份中文 markdown 被算成 1 個「詞」、變成 1 個 chunk。** 一份文件一個向量，回答的是「這份文件大致在講什麼」，不是「哪一段能回答這個問題」。實際檢查索引:中文 9 個檔案只產生 10 個 chunk（其中一個檔案 2 塊），英文因為有空格切成 14 塊。這也解釋了為什麼中文的分數普遍偏低又難以分辨——所有題目都在跟 9 個「整份文件」的平均語意比對。

## ② Design Decision

**先建 benchmark，再動程式。** 這次改動會影響整個 App 的檢索行為（FAQ 回答、verifier 是否放行、捷徑題庫是否過門檻、知識優化流程的分數），沒有量測就等於盲改。所以先寫了 67 題（中文 39 / 英文 28）並標註每題「應該命中哪個檔案」，跑出 before 基準:中文 top-1 只有 54%。

**標題就是最好的邊界。** 這批文件的一個 `##`／`###` 段落剛好就是一個主題（「跨行 ATM 手續費」「年費」「轉帳限額」），比任何字數切點都準。超長段落才退回依大小切窗，而且整行切，不切斷表格列。

**標題路徑必須跟著本文一起嵌入。** 每塊前面掛上 `轉帳與匯款說明＞國內轉帳＞轉帳方式與手續費`。理由:一個講「年費」但內文從沒再出現「信用卡」三個字的段落，若沒有麵包屑，會輸給一份反覆提到「信用卡」的整份文件。

**長度改用 unit = CJK 字元數 + 拉丁詞數**，這樣同一個數字在兩種語言代表差不多的內容量。

**`###` 要不要也切？量測決定，不用直覺。** 只切 `##` → 英文 top-1 89%;連 `###` 一起切 → 96%。代價是中文 recall@3 掉約 3 個百分點，用 `TOP_K` 3 → 5 補回來（chunk 體積縮小約 6 倍，取 3 塊的內容量遠少於過去的 3 份完整文件;實測中文 recall@5 97%）。

## ③ Implementation & Iteration

`build_index.py` 的 `chunk_text` 換成 `split_markdown`:掃描每一行、追蹤 `#`/`##`/`###` 標題層級、以 `##`/`###` 為界切段、掛上麵包屑、超長才呼叫 `_window()` 依行數切窗（帶重疊）。新增 `count_units()`。`retriever.py` 的 `TOP_K` 3 → 5。kb_entries 沒有標題結構，會原樣成為單一 chunk（有測試涵蓋）。

三次量測驅動的修正:
1. **合併文件開頭的引言**。第一版把第一個 `##` 之前的內容獨立成塊，結果產生一個只有 14 unit 的「文件標題塊」——什麼都沒說卻佔用檢索名額。改成併入第一個真正的段落。
2. **`###` 實驗第一次做錯了**。我在實驗版本加了「太短的段落併入前一塊」的邏輯，結果把段落併到**不相干的前一個段落**、麵包屑因此說謊，量出來的數字自然很差（recall 下降）。發現後拿掉合併邏輯重測，才得到可信的比較（英文 top-1 89% → 96%）。差點就用一個有 bug 的實驗結果否決了正確的設計。
3. **`# 標題` 那一行不該留在內文**。寫測試時才發現:標題已經在麵包屑裡，又被 append 進 body，導致「沒有引言的文件」產生 `轉帳與匯款說明＞國內轉帳\n# 轉帳與匯款說明` 這種只有標題重複兩次的塊。拿掉之後，**中文 top-1 又從 79% 跳到 85%、英文從 96% 到 100%**——一個為了讓測試通過而做的清理，剛好是這次最後一段增益。

量測結果（before → after）:

| | 中文 | 英文 |
|---|---|---|
| 正確檔案排第一 | 54% → **85%** | 71% → **100%** |
| 正確檔案在前三 | 74% → **92%** | 82% → **100%** |
| 最高分 ≥ 0.60 門檻 | 64% → **87%** | 43% → **89%** |

chunk 數:中文 10 → 84、英文 14 → 79。

Live 驗證:原本失敗的五題全部改正——「跨行轉帳手續費」現在答出 NT$15 即時轉帳費、「定存利率」答出完整利率表、「收不到 OTP」給出排除步驟（原本轉真人客服）、「行動 APP 功能」「提前還款違約金」也都正確。順帶讓 Sprint 20 的捷徑題庫多出一大批可用題目（英文的外幣、轉帳兩個主題原本掛零，現在各有 4 題），已擴充並逐題重新實測。新增 `tests/test_chunking.py` 10 個測試。

## ④ Evaluation & Reflection

**這個 bug 存在了 16 個 Sprint。** 從 Sprint 5 建索引以來一直都在，中間經過 verifier、知識優化流程、捷徑題庫好幾輪跟檢索品質直接相關的工作，都沒被發現。原因很清楚:每一輪都是「拿幾個問題試試看，覺得還行」，而檢索的失敗模式恰好最擅長偽裝成「這題比較難、答不出來很正常」。真正讓它現形的是 Sprint 20 那個機械化的動作——**逐題標註「應該命中哪個檔案」再逐題比對**。有標準答案的量測，和沒有標準答案的試用，看見的東西完全不同。

**先建 benchmark 再改程式，這次至少三次派上用場**:它證明了改動有效（54% → 85%）、否決了我的直覺（`###` 到底要不要切）、也抓出了我自己實驗程式裡的 bug（合併邏輯讓麵包屑說謊）。如果只是改完跑幾題「感覺變好了」，第 2 點會做錯方向，第 3 點根本不會發現。

**最後那段增益來自寫測試**。`test_each_chunk_carries_its_heading_trail` 失敗，才發現 `# 標題` 行被重複塞進內文。這不是「補測試」的例行公事——測試逼我為一個乾淨的最小輸入寫出預期輸出，而真實的知識庫檔案剛好都有引言，把這個瑕疵遮住了。**用真實資料看不出來的問題，最小案例會直接指著它。**

生產環境的延伸:把這份 benchmark 納入 CI，知識庫每次變更自動跑回歸（現在還是手動）;跨語言分別調 TOP_K;加一層 rerank 處理剩下 3 題「多份文件都有手續費段落」的跨主題混淆;文件若改成無標題長文，需要語意切塊。

# Sprint 22：Mingis 改版 + 帳單問題先追問

**日期**：2026-11-18
**起因**：準備 3 分鐘 demo 影片時，使用者逐項實測並提出一批調整。所有改動先在獨立的測試副本與測試埠（後端 8001／前端 8502）驗證，確認後才合併進正式專案，合併前另做整份備份。

## 這一輪改了什麼

1. **助理更名 Mingis**（原名小豐）：畫面、提示詞與文件中的名稱統一。
2. **吉祥物重新渲染**：原圖是 Three.js 的 3D 模型（`frontend/design-prototype/mascot-3d.html`），複製成 `mascot-mingis.html` 後加上耳機麥克風（麥克風臂貼著臉頰彎到嘴邊）；Dashboard 另做「坐在電腦桌前」的場景（瞇眼、冒汗、頭上漩渦與問號、桌上文件與便利貼、波浪形疑惑嘴型），再用 headless Chrome 輸出透明 PNG／WebP。
3. **帳單問題先追問**（見 ADR-017）。
4. **「真人」統一為「真人客服」**：只改客戶與客服人員看得到的文字；給分類器辨識用的關鍵字（「我要真人」）不動，因為那是使用者輸入。
5. **銀行名稱** XX 銀行 → Future銀行；知識庫內容跟著改，因此重建了向量索引。電話與地址的 `XX` 是佔位符，保留。
6. **客戶端轉接畫面頂端固定 Mingis 狀態列**：之前轉接後畫面整個換成真人客服對話，Mingis 消失。現在頂端固定一張卡片（頭像＋狀態標籤＋一句話），狀態隨工單變化：等待客服專員接手 → 客服專員服務中 → 已結案。選頂端固定而非角落浮動，是因為不會擋輸入框與長訊息。
7. **知識缺口管線 → 知識優化流程**（Knowledge Improvement Pipeline）。英文最初考慮 Optimization，後改為 Improvement，語意更貼近「把答不好的地方補起來」。程式內部識別名稱（`gap_pipeline.py`、`/gap/*`、`kb_gap_drafts`）沿用舊名，避免動到資料庫與 API。
8. **Dashboard**：AI 呼叫成本與延遲是給開發與維運人員看的，客服人員日常不需要，因此收進最下方「開發者資訊」摺疊區塊；客服人員不需要的 Session 欄從「最近未解決查詢」與「低分回饋」移除（資料庫仍保留 session_id；開發者資訊裡的呼叫明細保留，用來把慢或貴的呼叫追到對話）。
9. **順手修的一處**：多輪流程進行中，畫面一律顯示「信用卡掛失進行中」橫幅，連轉接資料收集與帳單追問時也會跳出。改為只有掛失流程（`workflow_data` 沒有 `type`）才顯示。

10. **「你好！」不再被轉真人客服**：客戶打招呼，系統去知識庫查，相似度僅 0.24，Verifier 判定資料不足就轉接（10 月的「Hi」是同一個舊問題）。新增 Smalltalk Node，整句只是招呼／道謝／道別時由 Router 規則直接回覆，不轉接也不記入未解決（見 ADR-018）。
11. **案件可以直接點開**：
    - **客服人員介面**：維持上下排列（對話在上、案件列表在下，對話可用滿版寬度，閱讀較清楚）。原本點下方的案件後，上方的對話換了，但畫面還停在下面，看起來像沒反應。改成點選後自動捲回上方的對話。（中途曾改成左右並排，使用者認為上下排列比較清楚，已改回。）
    - **點哪格都算點選**：改用「單一儲存格」選取。原本的「整列選取」要點最左邊的小方框，點文字不會有反應，這是「點了沒反應」的另一半原因。
    - **Dashboard「最近未解決查詢」與「最近服務單」**：點一列開啟「案件」對話框，內容是工單資訊、完整對話、同一段對話的未解決紀錄與滿意度評分；案件還在待處理時可直接回覆、標記已解決，或跳到客服人員介面並自動選中該案件。
    - **沒有服務單的未解決查詢**（Mingis 自己處理的，例如被評低分）：只顯示當時的對話與紀錄，沒有可以回覆的案件，並明確說明。
    - **後端**：新增兩支只有客服人員能呼叫的查詢，`GET /tickets/{id}/record` 與 `GET /cases/by-session/{session_id}`（測試見 `tests/test_case_record.py`）。session_id 不再顯示在畫面上，只用在這兩支查詢內部。
12. **Dashboard 版面與配色**：使用者覺得 Dashboard 全是藍色太單調，提供 7 張參考圖。評估後以 Insights 的版型（大卡片放角色、數字壓在卡片下緣）為骨架，借 Fincheck 的「每張 KPI 一種顏色」，借 NIKITIN 的狀態標籤，其餘（粉彩卡通、3D 磨砂質感）不採用。底色（淺青白頁面、深藍側欄）不變。
    - **KPI 由 3 張變 4 張**：Tickets總數（藍）、待處理（琥珀）、**已完成**（綠，新增，後端 `/stats` 加 `done_tickets`）、未解決查詢（紫）。
    - **顏色只用在有意義的地方**：藍是結構色；琥珀＝需注意、珊瑚＝緊急/低分、綠＝完成/滿意、紫＝AI 與知識。「未解決原因 Top 5」長條改為依原因上色（原本是兩種藍交替）；滿意度圓環由綠到紅；表格狀態用 🟠待處理／🟢已解決，緊急優先度用 🔴，每個狀態都有文字，不靠顏色辨識。
    - **版面順序**：Mingis 大卡片＋Top 5 → 最近未解決查詢 → 最近服務單 → 客戶滿意度＋低分回饋 → 兩個收合區塊。理由：客服人員最常做的是點案件處理，所以案件表往上移，品質指標往下。
    - **未採用**：Mingis 小提醒卡（把「知識庫優化流程提示」做成角色小卡），留待使用者決定。
13. **整個平台支援中文／English 切換**：
    - **一個切換器**：每頁側邊欄最上方「中文｜English」，語言存在 session 並寫進網址（`?lang=en`），重新整理不會跳回中文。文字集中在 `frontend/strings.py`（中英並列），沒有英文版時退回中文。
    - **導覽列自己畫**：Streamlit 依檔名產生的選單無法翻譯，所以隱藏它，改用 `st.page_link` 畫（`i18n.render_nav`）。
    - **客戶端首頁**：原本跟著客戶輸入的語言自動切換；現在「手動切換優先，沒切換才跟著對話」。Mingis 回覆的語言仍依客戶輸入，不受介面語言影響。
    - **不翻譯的是真實內容**：客戶對話、客服人員自己打的回覆、知識庫條目（本來就分中英兩份）。
    - **服務單的「原因」**：後端是用中文文字存進資料庫（例如「轉真人客服：帳務爭議/退款｜…」）。為了不動資料庫，前端用對照表翻譯固定標籤，客戶自己打的內容原樣保留（`i18n.ticket_reason`）。知識優化草稿的「訊號組成」同理（`i18n.signal_summary`）。
    - **防漏翻的測試**（`tests/test_i18n.py`）：每個字串都有中英文、佔位符一致、英文不能殘留中文、程式用到的字串都存在、後端新增原因代碼而前端沒翻譯會直接失敗。
14. **客服人員介面**：解決前先確認，並可「復原」或之後在案件記錄「重新開啟」（新增 `POST /handoff/{id}/reopen`）；案件列表緊急優先、顯示「已等多久」、可依原因篩選與排序；服務單資訊從三張大數字卡縮成一行標籤；移除副標的 Sprint 字樣；轉接前訊息標示改為 Mingis。
15. **知識庫維護**：頁首狀態列顯示「有 N 筆變更尚未套用到索引」（新增 `GET /kb/status`，以索引檔寫入時間為基準，重啟後仍正確），重建索引成為主按鈕；補充知識改為可搜尋、可依語言與來源篩選的表格，點一列開啟編輯對話框；封存從「儲存」旁邊移到獨立的次要區塊；語言選項用文字而非國旗。
16. **知識優化**：分析結果顯示為漏斗（訊號 → 主題 → 草稿 → 已核准），並列出被排除的主題（`/gap/analyze` 回傳 `excluded_topics`）；「已入庫」用前後對照條配 0.60 門檻線取代三個裸數字；案件對話框、客服人員介面、知識庫維護與知識優化之間加上互相連結，讓「客服處理 → 知識優化 → 知識庫」這個閉環在畫面上是連起來的。
17. **核實改為每次都做**（ADR-020）：測試海外退款題時發現，知識庫沒有答案卻得到 0.664 的高分，跳過核實後模型自己補了理由。量測 62 題可答題與 12 題真缺口，原規則只擋下 5/12，每次都核實擋下 12/12（代價：首字多約 3 秒、轉人比例升到 11/62）。同時：核實改 `temperature=0`（同一輸入曾得到相反結果）、回答規則加「不得補充知識庫沒提到的理由」、7 題會變死路的捷徑移除並加測試把關。詳細數字與限制見 `docs/evaluation.md`。
18. **不明款項要走緊急盜刷流程**：Dashboard 上「帳單裡有一筆不明款項，我未消費過此筆金額」被歸為一般的帳務爭議，沒有標緊急。量測（12 種說法各跑 4 次）：這句話 4/4 判成爭議，"I don't recognize this transaction on my bill" 4/4 判成查詢帳務，其餘 10 種說法都正確（40/48）。盜刷完全由分類器的提示詞判斷，沒有關鍵字規則，所以修的是提示詞：「客戶說不是自己消費、沒花過、不認識的款項，一律算盜刷，即使說得很委婉或像在問帳單」，並補上反向說明「自己消費過但被重複扣款、金額錯誤、退款沒收到，是爭議不是盜刷」，另外分類器改 `temperature=0`。第一版修正後這 48 句全中，但「商家對我扣了兩次款」被誤判成盜刷（0/4），補反向說明後連跑兩輪都是 76/76（盜刷說法 48/48、其他類別 28/28）。新增 `tests/test_fraud_intent.py`（呼叫真實 API）。限制：這是人工挑的 19 種說法，不代表所有說法都能判對。
19. **祕密與帳密不再有內建預設值**：整理架構文件時發現 `auth.py`、`staff_auth.py` 在沒設環境變數時會退回寫死的 JWT 密鑰與員工帳密。對公開的 repo 來說，寫死的預設值就是公開的密碼。改成缺少、仍是範例值或 JWT 密鑰短於 32 字元時一律拒絕啟動，並說明如何產生；測試改用僅供測試的假值，不碰開發者的 `.env`。新增 `tests/test_secrets_required.py`（用乾淨的子行程驗證會停止啟動，並確認舊預設字串不在原始碼中）。

## 過程中學到的

**先量測再設計**：一開始以為「帳單金額有問題」是被分類成轉接。實際把同一句話連跑 6 次分類器，才發現它在 `account` 與 `dispute_or_refund` 之間搖擺。如果當初直接在轉接節點加追問，會有 5/6 的機率完全沒觸發。這也是追問規則放在分類器之前的原因。

**測試的取捨**：新增 `tests/test_bill_clarify.py`，全部不呼叫 LLM（規則先於分類器、第二輪是進行中的流程）。全專案目前 192 個測試。`en_handoff_006`（情緒激動的英文句）偶爾判成別的類別，是分類器在邊界案例上的機率性行為，與本輪改動無關；搭配會初始化資料庫的測試一起跑，多次都通過。

**量測也會量到自己的盲點**：標記缺口題時，我把「保險箱」當缺口，但測試副本裡有我先前演練核准的補充知識，核實判斷「足夠」其實是對的。這提醒我，量測用的標準答案本身也要檢查，並在文件裡說明這 12 題缺口是人工挑選的。

**合併流程**：正式專案當時有兩個尚未提交的修改。做法是先複製整份專案成測試副本，所有改動與測試都在副本上完成，合併前確認正式專案自複製後沒有被動過、備份整份，再用 rsync 合併（排除 `.env`、`banking.db`、向量索引），最後在正式專案重建索引、重跑測試。

---

*後續 Sprint 依此格式持續新增*
