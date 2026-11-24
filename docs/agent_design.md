# AI Agent Design
# AI Banking Customer Assistant

**版本**：v2.0
**對應 Sprint**：Sprint 6（LangGraph 架構）、Sprint 7（Account Node tool-calling）、Sprint 9（Router LLM 意圖分類）、Sprint 12（FAQ Node Grounding Verifier）、Sprint 13（串流回覆）、Sprint 14（Handoff 業務觸發規則）、Sprint 15（真人客服對話）、Sprint 16（滿意度評分 CSAT）、Sprint 17（知識庫維護 + 熱重建索引）、Sprint 18（知識優化流程）、Sprint 19（對話即時更新 + 訪客轉接前資料收集）、Sprint 20（常見問題快捷路徑）、Sprint 21（中文切塊修復），Sprint 1-5 使用函式路由（if/else）模擬相同行為

---

## 1. 設計原則

本文件定義 AI Agent 的完整行為規格。Sprint 1-5 以 if/else 函式路由實作，Sprint 6 將重構為 LangGraph State Machine，兩者的外部行為一致，差異只在內部架構。

**為什麼先用函式路由再升級？**（詳見 ADR.zh-TW.md ADR-02）
> 先讓業務邏輯跑通，再引入框架複雜度。函式路由清晰易 debug，LangGraph 提供可追蹤的 State 和可組合的 Node，適合作最終展示架構。

---

## 2. Agent State 定義

```python
from typing import TypedDict, Optional

class AgentState(TypedDict):
    # 對話歷史（最多 10 輪，rolling window）
    messages: list[dict]          # {"role": "user"/"assistant", "content": str}

    # 意圖與語言
    intent: str                   # credit_card_fee / check_bill / report_card_loss / ...
    language: str                 # "zh" or "en"

    # 身分認證
    user_authenticated: bool
    user_id: Optional[str]        # 登入後設定

    # 多步驟 Workflow（信用卡掛失）
    workflow_step: int            # 0=未開始, 1=身分驗證, 2=選卡片, 3=確認掛失, 4=完成
    workflow_data: dict           # {"card_id": ..., "id_last4": ..., "ticket_id": ...}

    # Fallback 追蹤
    fallback_count: int           # 連續 fallback 次數，達 3 次觸發 Human Handoff

    # Session 管理
    session_id: str               # UUID，每次對話開始時生成
    rag_context: list[dict]       # RAG 搜尋結果 [{"source": ..., "text": ...}]
```

---

## 3. Node 設計

### 3.1 Router Node（意圖路由）— Sprint 9 起為真正 LLM 分類

**職責**：分析用戶輸入，判斷意圖類型，路由到對應 Node。

**輸入**：user message + conversation history
**輸出**：更新 `state.intent` 和 `state.language`，決定下一個 Node

**路由邏輯**：

```
用戶輸入
    │
    ▼
langdetect → state.language = "zh" or "en"
    │
    ▼
Intent Classification（LLM 分類）
    │
    ├── FAQ 類 → FAQ Node
    │   (credit_card_fee, account_rules, loan_info, digital_service, general_service)
    │
    ├── ACCOUNT 類 → Account Node（需登入）
    │   (check_balance, check_bill, check_transactions)
    │
    ├── WORKFLOW 類 → CardLoss Node（需登入）
    │   (report_card_loss)
    │
    └── ESCALATION 類 → Handoff Node
        (request_human, complaint)
```

**Fallback 條件**：
- 意圖分類信心度低 → 反問用戶（最多 2 次）*(v1 未實作——目前用 `tool_choice` 強制模型一定要回傳四類其中之一，沒有「信心度」可讀，也就沒有反問迴圈；見 ADR-009)*
- 連續 3 次無法解決 → 強制觸發 Handoff Node（由前端 `fallback_count` 追蹤、`force_handoff` flag 觸發，這條路徑不經過分類器，見 §7 Q&A）

**實作備註（Sprint 9）**：Sprint 1-8 用關鍵字比對（`is_card_loss`／`is_handoff_trigger`／`is_account_query`）模擬這個 Node，Sprint 9 換成 `backend/src/agent/intent.py` 的 `classify_intent()`——用 Claude 的 `tool_choice` 強制呼叫 `classify_intent` 這個 tool，保證一定拿到 `faq`／`account`／`card_loss`／`handoff` 四選一的結構化結果，不用解析自由文字。以下兩種情況**不會**呼叫分類器，屬於確定性的系統狀態判斷，不是「使用者這句話是什麼意圖」：
1. `workflow_step > 0`（掛失流程進行中）→ 一律路由到 CardLoss Node
2. `force_handoff == True`（前端偵測到連續 fallback）→ 一律路由到 Handoff Node，`trigger_reason="fallback_threshold"`

---

### 3.2 FAQ Node（知識庫查詢）— Sprint 12 起附加 Grounding Verifier

**職責**：使用 RAG 搜尋知識庫，生成回答。

**Sprint 1-4**：Context Stuffing（把所有 FAQ 塞進 System Prompt）
**Sprint 5+**：FAISS RAG（Top-K chunk 搜尋，附來源文件）
**Sprint 21+**：chunk = markdown 的一個 `##`/`###` 段落（含標題路徑），不再是整份文件;Top-K 3→5（見 ADR-016）
**Sprint 12+**：分數落在模糊地帶時，先用獨立的 Verifier 核實 chunk 內容，再決定要不要生成回答
**Sprint 17+**：檢索的索引 = `data/knowledge_base` 官方 markdown ＋ `kb_entries` 表的 active 補充知識（透過維護頁面/知識優化流程新增）;`POST /kb/reindex` 重建並就地熱抽換 retriever，新增知識即時生效不需重啟（見 ADR-012）

**輸入**：user query + `state.language`
**輸出**：回答文字 + 來源文件（Sprint 5 起）

**執行步驟**：
1. 呼叫 `search_knowledge_base(query, language, top_k=3)`
2. top-1 分數 ≥ 0.60 → 信心足夠，跳過步驟 3，直接進步驟 4
3. 分數 < 0.60 → 呼叫 Verifier（見 `backend/src/agent/verifier.py`）核實 chunk 是否真的足以回答；判定不足 → 跳過步驟 4，直接進 Fallback（見下）
4. 呼叫 Claude API，帶入 context chunks，生成 Draft 回答
5. 如為貸款相關意圖，強制插入 Disclaimer
6. 更新 `state.messages`，記錄回答

**Fallback 處理（Sprint 12 起）**：
- Verifier 判定 chunk 不足 → 回傳轉真人客服訊息，不生成 Draft（用字跟 Handoff Node 的 `HANDOFF_MSG` 不同——這裡是 AI 主動判斷答不出來，不是回應使用者主動抱怨/要求轉真人客服，語氣刻意分開，見 `backend/src/agent/nodes.py` 的 `VERIFIER_ESCALATION_MSG`）
- 呼叫 `log_unresolved(query, reason="verifier_unresolved", similarity_score=...)`
- **實作備註**：Sprint 1-11 的 Fallback 判斷只看「有沒有 chunk 超過相似度門檻」，一份診斷案例研究發現這個判斷抓不到「chunk 有超過門檻、但內容答非所問」的中間地帶——Verifier 讀取 chunk 內容本身而非只看分數，正是為了補這個盲點（詳見 ADR-010）

---

### 3.3 Account Node（帳務查詢）— Sprint 7 起為真正 tool-calling

**職責**：驗證登入狀態，呼叫 Mock Banking API，整理成自然語言。

**先決條件**：`state.user_authenticated == True`
若未登入 → Node 內直接回傳登入提示，不呼叫 Claude / 不執行任何 tool

**支援意圖**：

| 意圖 | 呼叫 Tool | 回傳資料 |
|------|-----------|---------|
| check_balance | `get_account_balance` | 帳戶餘額 |
| check_bill | `get_credit_card_bill` | 應繳金額、截止日、最低應繳 |
| check_transactions | `get_transactions` | 近期交易明細列表 |

**實作備註（Sprint 7）**：`user_id` 不放進 Claude 看得到的 tool schema，由 `backend/src/agent/tools.py` 的 `execute_tool()` 在後端注入，避免模型被誘導查詢其他使用者的帳戶（詳見 ADR-008）。一輪對話最多允許 `MAX_TOOL_ITERATIONS=3` 次 tool-calling 迴圈，超過則回覆客服專線並記錄 `trigger_reason="tool_loop_exceeded"`。

**輸出格式**（LLM 整理後）：
```
您本月信用卡應繳金額為 NT$12,450
繳款截止日：2026-07-25
最低應繳：NT$3,500

需要查詢消費明細嗎？
```

---

### 3.4 CardLoss Workflow Node（信用卡掛失）

**職責**：執行多步驟掛失流程，每步都需用戶確認。

**先決條件**：需登入（或在流程中完成身分驗證）

**流程步驟**（`state.workflow_step`）：

```
Step 0: 觸發
  Bot: 「我可以協助您辦理信用卡掛失。為保護您的帳戶安全，
        需要先確認您的身分，請問您的身分證後四碼為何？」

Step 1: 身分驗證
  User: 提供 id_last4
  Tool: verify_identity(user_id, id_last4)
  ✅ 通過 → Step 2
  ❌ 失敗 → 最多 3 次，失敗後轉 Handoff

Step 2: 選擇卡片
  Bot: 列出用戶所有信用卡（card_id, last4, type）
  User: 選擇遺失的卡片
  Tool: get_card_by_id(user_id, card_id)

Step 3: 確認掛失
  Bot: 「確認要掛失末碼 XXXX 的 VISA 白金卡嗎？
        掛失後此卡將立即停用，無法繼續使用。（是/否）」
  User: 確認

Step 4: 執行掛失 + 建立 Ticket
  Tool: block_card(user_id, card_id)
  Tool: create_ticket(type="card_loss", user_id, card_id)
  Bot: 「✅ 掛失完成！
        卡號末碼 XXXX 已鎖定（2026-07-15 14:32）
        服務單號：T-20260715-001
        客服將於 1 個工作日聯繫您處理補發事宜。
        需要立即轉接客服人員嗎？」
```

**中途放棄處理**：
- 用戶說「算了」「取消」→ 詢問確認後結束流程
- Workflow 未完成的 state 不寫入 DB

---

### 3.5 Handoff Node（轉真人客服）— Sprint 14 起有完整的業務觸發規則，Sprint 15 起真人客服可實際回覆

**職責**：結束 AI 對話，引導用戶轉接真人客服。

**觸發條件**（由 Router 的 `classify_intent()` 判斷 `intent="handoff"` 時，一併判斷 `handoff_category`）：

| `handoff_category` | 觸發情境 | `trigger_reason` |
|---|---|---|
| `explicit_request` | 用戶主動要求：「我要真人」「投訴」「申訴」"speak to agent" "complaint" | `handoff_intent` |
| `fraud_or_security` | 未授權交易、盜刷、詐騙、可疑登入 — 立即轉人工，回應模板標記緊急 | `handoff_urgent_fraud` |
| `dispute_or_refund` | 帳務爭議、退款未到、重複扣款、金額錯誤 | `handoff_dispute` |
| `approval_required` | 費用減免、例外核准、貸款審核、額度調整、特殊條件申請——需要人工核准/協商的請求，跟單純查詢費率/條件（留在 FAQ）不同 | `handoff_approval_required` |
| `sensitive_data_change` | 需要修改高敏感資料或安全設定（例如變更預留電話、密碼、雙重驗證） | `handoff_sensitive_data` |
| `emotional_distress` | 使用者情緒明顯激動、辱罵、極度急迫——跟單純的「你回答錯了」不同，後者仍留在原主題 | `handoff_emotional_distress` |
| `cross_account_complexity` | 問題跨多帳戶、多產品或跨部門 | `handoff_cross_account` |
| （前端偵測，非分類器判斷） | 連續 3 次 Fallback（`state.fallback_count >= 3`） | `fallback_threshold` |

信用卡/金融卡遺失或被盜**不算在這裡**——那是既有的 `card_loss` 意圖，走信用卡掛失工作流程，不是轉真人客服（見 §3.4）。

**回應模板**：`fraud_or_security` 用獨立的 `URGENT_FRAUD_HANDOFF_MSG`（明確標示「已標記為緊急案件」，並提示可直接說「我要掛失」啟動卡片停用），`sensitive_data_change`（Sprint 15 續，2026-08-01 測試修復）用獨立的 `SENSITIVE_DATA_HANDOFF_MSG`（「請稍候，我為您轉接真人客服協助處理」，取代原本會誤導成「AI 沒能解決」的道歉語氣），其餘類別共用原本的 `HANDOFF_MSG`：
```
很抱歉我沒能完全解決您的問題。

📞 客服專線：0800-XXX-XXX
   服務時間：週一至週五 08:00–22:00

🌐 線上客服（24小時）：官網右下角聊天按鈕

如您需要緊急服務（卡片掛失、帳戶凍結），
請撥打客服專線並選擇「緊急服務」，全天候有真人客服接聽。

本次對話將記錄供客服人員參考，感謝您的耐心。
```

**未登入提醒（Sprint 15 續）**：以上任一訊息若使用者尚未登入，都會經過 `_with_login_reminder()` 在結尾加一句軟性提醒（`LOGIN_REMINDER`），建議先登入讓客服能更快確認身份——只是提醒，不會阻擋轉接本身。9 項業務規則原本考慮過強制登入才能轉接，但盜刷/可疑登入類別本身就是緊急案件，強制登入可能讓帳戶已被鎖定的客戶卡住，因此改為軟性提醒 + 事後關聯（見下段）。

**訪客轉接前資料收集（Sprint 19）**：若 `handoff_category="explicit_request"` **且使用者未登入**，Router 改路由到 `handoff_intake_node`，先收集兩件事再開單：

1. 客戶類別（1. 銀行帳戶客戶／2. 信用卡客戶／3. 非本行客戶）
2. 一句話的問題描述

收集完成才呼叫 `escalate_to_human(..., intake=...)`，客戶類別與描述會寫進工單 `description`（案件佇列那一行就能分流）與對話串的「📋 轉接前資料收集」結構化區塊。流程用既有的 `workflow` 欄位在前後端來回，靠 `workflow_data["type"] == "handoff_intake"` 與掛失流程區分。

刻意**只**用於這一個類別：其餘類別（盜刷、爭議、敏感資料變更…）的觸發訊息本身就描述了問題，再問一次是重複，還會延遲最該立即轉接的緊急案件；已登入客戶的身份早已掛在工單上。收集最多問兩輪（`MAX_INTAKE_ATTEMPTS`），之後不論收到什麼都照樣轉接（類別記「未指明」），輸入「取消」可隨時退回一般 AI 對話——已經開口要真人客服的客戶不該被卡在填表迴圈裡（見 ADR-014）。

**後置動作**：
- 呼叫 `log_unresolved(trigger_reason=<對應上表>, ...)`——每個類別分開記錄，Dashboard 可以分辨「使用者自己要求轉真人客服」跟「系統判定需要人工處理」是不同性質的訊號
- 記錄 session_id 供客服查詢
- **（Sprint 15）呼叫 `escalate_to_human()`（`backend/src/agent/handoff.py`）**：建立一筆 `tickets`（`type="handoff"`，`fraud_or_security` 對應 `priority="high"`，其餘 `"normal"`），並把「轉接前的對話歷史 + 觸發訊息 + AI 的轉接回覆」一次寫進新的 `handoff_messages` 表，讓真人客服接手時不用叫客戶重講一次。這個 helper 同時被本節的 Handoff Node，以及 §3.3 FAQ Node 的 Grounding Verifier 判定知識庫不足時共用（`trigger_reason="verifier_unresolved"`），避免兩個轉接觸發點各自重複寫一遍建立案件的邏輯。

**真人客服對話流程（Sprint 15）**：轉接之後，`tickets`/`handoff_messages` 是唯一的資料來源，前端不再走 Router/FAQ/Account 這套 Agent 流程：

- 客戶端（`frontend/app.py`）一旦收到 `is_handoff=true`，就完全鎖定進「真人客服對話」畫面，不能再問 AI 其他問題（直到案件被標記為已解決）——這是刻意的產品決策，不是技術限制，理由見 `docs/design_journal.md` Sprint 15 的 Q2。**（Sprint 19 起）**畫面每 5 秒自動更新，收到轉接回應的那一輪就立刻切換進真人客服對話畫面（不必再送一則訊息才看得到）。
- 真人客服用獨立頁面 `frontend/pages/2_客服人員介面.py` 處理案件：列出所有 `status="open"` 的案件、顯示優先度/狀態/客戶，讀寫同一份 `handoff_messages` 對話串，並可呼叫 `/handoff/{id}/resolve` 把案件標記為已解決。**（Sprint 19 起）**對話串每 5 秒自動更新、案件佇列每 15 秒檢查有無新案件（只提示、不自動切換案件）。
- **（Sprint 19）兩邊的自動更新都放在 `st.fragment(run_every=...)` 裡**，不是整頁自動 rerun：Streamlit 的整頁 rerun 會清掉客服正在打到一半的回覆，fragment 只重跑那一塊。`st.chat_input` 刻意留在 fragment 外面（放進 fragment 會失去釘在底部的版位）。
- 後端新增四個端點（`backend/main.py`）：`GET /handoff/tickets`（列出待處理案件）、`GET /handoff/{id}/messages`（讀對話串）、`POST /handoff/{id}/messages`（雙方都用這個端點寫入新訊息，`role` 分 `"user"`/`"agent"`）、`POST /handoff/{id}/resolve`（把 `tickets.status` 改成 `"resolved"`）。
- `tickets.status` 在 Sprint 15 之前永遠停在 `open`（見 Sprint 8/11 的設計日誌），`update_ticket_status()` 是第一個真正會改變它的地方，`/stats` 的 `open_tickets` 統計數字因此第一次變得有意義。
- **（Sprint 15 續）訪客轉真人客服後才登入的身份關聯**：`POST /handoff/{id}/link-user` 讓客戶在轉真人客服對話仍開啟中登入時，把工單的 `user_id` 從 `NULL` 補上（只填空值，不覆蓋既有身份，見 `database.link_ticket_user`）。`frontend/app.py` 的登入處理邏輯會判斷當下是否處於轉真人客服鎖定畫面：是的話呼叫這個端點並保留整段對話，不是的話才照原本邏輯重置成新對話。

---

**帳單問題先追問（Sprint 22）**：客戶只說「我的帳單金額有問題」時，轉接過去的案件看不出是哪一筆、什麼問題，真人客服第一句話就得補問。所以 Router 在呼叫 LLM 分類器**之前**先做一個確定性判斷 `_is_vague_bill_complaint()`：訊息同時含「帳單」與「有問題／不對／怪怪…」類字眼，且**沒有**具體線索（金額數字、「沒刷過」「重複扣款」「年費」「這一筆」等）、長度 ≤ 30 字，就路由到 `bill_clarify_node`，先問：

> 請詳細說明帳單內容哪一筆有問題？讓客服人員能立即了解您的問題及需求。

客戶回覆後才呼叫 `escalate_to_human(..., bill_detail=...)`，回覆內容寫進工單 `description`（「帳單問題｜…」）與對話串的「📋 帳單問題說明」結構化區塊。同樣用 `workflow` 欄位往返，靠 `workflow_data["type"] == "bill_clarify"` 區分。規則跟訪客資料收集一致：最多問兩輪（`MAX_BILL_CLARIFY_ATTEMPTS`）、輸入「取消」可退回一般對話、`force_handoff` 時直接跳過不再追問。客戶一開口就講得很具體（盜刷、重複扣款、有金額），照原本路徑轉接，緊急案件不排在問題後面（見 ADR-017）。

**純招呼語／道謝／道別（Sprint 22）**：「你好！」「Hi」「謝謝」「掰掰」不是銀行問題。原本它們會被當成 FAQ，檢索相似度約 0.24，Verifier 判定資料不足，客戶第一句話就被轉真人客服（見 ADR-018）。現在 Router 在 LLM 分類器之前做確定性判斷 `_match_smalltalk()`：訊息去掉標點、空格、emoji 後，**整句**剛好是招呼語／道謝／道別（可跟著 "Mingis"），就路由到 `smalltalk_node`，回一句固定的親切回覆。不查知識庫、不轉接、不記入未解決，也不會變成知識優化流程的訊號。「你好，年費多少？」這類夾帶問題的訊息不受影響。順序上 `force_handoff` 與進行中的流程優先於它。

### 3.6 Logger Node（記錄未解決）

**職責**：將 Fallback 和 Handoff 事件寫入 SQLite `unresolved_queries` 表。

不直接回應用戶，僅後置執行。

**記錄欄位**：
```python
{
    "session_id": state["session_id"],
    "user_query": original_user_message,
    "language": state["language"],
    "intent": state["intent"],
    "trigger_reason": "verifier_unresolved" | "negative_feedback" | "handoff_intent" | "fallback_threshold" | "tool_loop_exceeded",
    "similarity_score": float or None,
    "created_at": datetime.now()
}
```

---

## 4. Tool 定義規格

符合 OpenAI-compatible tool spec 格式，Claude API 可直接使用。

### 4.1 search_knowledge_base
```json
{
  "name": "search_knowledge_base",
  "description": "Search the FAQ knowledge base using vector similarity. Returns top-K relevant chunks.",
  "parameters": {
    "query": {"type": "string", "description": "User's question"},
    "language": {"type": "string", "enum": ["zh", "en"]},
    "top_k": {"type": "integer", "default": 3}
  }
}
```

### 4.2 get_account_balance
```json
{
  "name": "get_account_balance",
  "description": "Get account balance for authenticated user.",
  "parameters": {
    "user_id": {"type": "string"},
    "account_type": {"type": "string", "enum": ["savings", "checking", "fixed_deposit", "all"]}
  }
}
```

### 4.3 get_credit_card_bill
```json
{
  "name": "get_credit_card_bill",
  "description": "Get credit card billing info (due amount, due date, min payment).",
  "parameters": {
    "user_id": {"type": "string"},
    "month": {"type": "string", "description": "current_month or last_month", "default": "current_month"}
  }
}
```

### 4.4 get_transactions
```json
{
  "name": "get_transactions",
  "description": "Get recent transaction history for authenticated user.",
  "parameters": {
    "user_id": {"type": "string"},
    "limit": {"type": "integer", "default": 5, "description": "Number of recent transactions"}
  }
}
```

### 4.5 verify_identity
```json
{
  "name": "verify_identity",
  "description": "Verify user identity using last 4 digits of national ID.",
  "parameters": {
    "user_id": {"type": "string"},
    "id_last4": {"type": "string", "description": "Last 4 digits of national ID"}
  }
}
```

### 4.6 block_card
```json
{
  "name": "block_card",
  "description": "Block (report lost) a credit card. Immediately disables the card.",
  "parameters": {
    "user_id": {"type": "string"},
    "card_id": {"type": "string"}
  }
}
```

### 4.7 create_ticket
```json
{
  "name": "create_ticket",
  "description": "Create a service ticket (card loss, complaint, general inquiry).",
  "parameters": {
    "type": {"type": "string", "enum": ["card_loss", "complaint", "general"]},
    "description": {"type": "string"},
    "user_id": {"type": "string", "nullable": true},
    "card_id": {"type": "string", "nullable": true},
    "priority": {"type": "string", "enum": ["high", "normal"], "default": "normal"}
  }
}
```

### 4.8 escalate_to_human
```json
{
  "name": "escalate_to_human",
  "description": "Trigger human handoff. Logs session and returns handoff message.",
  "parameters": {
    "reason": {"type": "string", "description": "Why handoff was triggered"},
    "session_id": {"type": "string"}
  }
}
```

### 4.9 log_unresolved
```json
{
  "name": "log_unresolved",
  "description": "Log an unresolved query to the database for human review.",
  "parameters": {
    "user_query": {"type": "string"},
    "language": {"type": "string", "enum": ["zh", "en"]},
    "intent": {"type": "string"},
    "trigger_reason": {"type": "string", "enum": ["verifier_unresolved", "negative_feedback", "handoff_intent", "handoff_urgent_fraud", "handoff_dispute", "handoff_approval_required", "handoff_sensitive_data", "handoff_emotional_distress", "handoff_cross_account", "fallback_threshold", "tool_loop_exceeded"]},
    "session_id": {"type": "string"},
    "similarity_score": {"type": "number", "nullable": true}
  }
}
```

---

## 5. Node 執行流程圖（LangGraph）

```
START
  │
  ▼
Router Node
  │
  ├── intent=FAQ          → FAQ Node ──────────┐
  │                                             │
  ├── intent=ACCOUNT      → Account Node ───────┤
  │   (need auth)                               │
  ├── intent=WORKFLOW     → CardLoss Node ──────┤
  │   (need auth)                               │
  ├── intent=ESCALATION   → Handoff Node ───────┤
  │                                             │
  ├── 純招呼語／道謝／道別    → Smalltalk Node ─────┤
  │   (Sprint 22)          固定親切回覆，不轉接   │
  │                                             │
  ├── 訪客主動要求真人客服    → HandoffIntake Node ─┤
  │   (Sprint 19)          先問類別＋問題描述，   │
  │                        收集完才開單          │
  │                                             │
  └── 籠統的帳單問題        → BillClarify Node ───┤
      (Sprint 22)          先問「哪一筆有問題」， │
                           回覆後才開單          │
         ┌──────────────────────────────────────┘
         │
         ▼
    Logger Node（如有 Fallback / Handoff）
         │
         ▼
        END
```

---

## 6. Sprint 實作路線圖

| Sprint | 實作方式 | Node 行為 |
|--------|---------|-----------|
| Sprint 1 | 函式路由 + Context Stuffing | Router → FAQ（用 System Prompt 內嵌 FAQ）|
| Sprint 2 | 函式路由 + Mock API | + Account Node |
| Sprint 3 | 函式路由 + SQLite | + CardLoss Node（基本版）|
| Sprint 4 | 函式路由 + 觸發偵測 | + Handoff Node + Logger Node |
| Sprint 5 | 函式路由 + FAISS | FAQ Node 升級為真正 RAG |
| Sprint 6 | **LangGraph 重構** | 所有 Node 遷移為 LangGraph Graph |
| Sprint 7 | **Account tool-calling** | Account Node 改為真正呼叫 `get_account_balance`／`get_credit_card_bill`／`get_transactions`，不再與 FAQ 共用 context stuffing |
| Sprint 8 | **測試套件** | pytest + 獨立 test.db，14 個測試案例涵蓋所有 Node |
| Sprint 9 | **Router LLM 意圖分類** | 關鍵字比對換成 `classify_intent()`，用 `tool_choice` 強制結構化分類，兌現 §3.1 一開始就寫好的規格 |
| Sprint 10 | **實測修復** | 語氣贅字、CardLoss 復原偵測、防止 AI 附和錯誤說法三項修復，來自使用者實際扮演真人客服測試的回報 |
| Sprint 11 | **轉真人客服 Banner** | `ChatResponse` 新增 `is_handoff`，前端顯示持久性「已轉接真人客服」提示 |
| Sprint 12 | **FAQ Grounding Verifier** | 相似度分數模糊地帶新增獨立核實角色，補上「chunk 超過門檻但答非所問」這個監控盲點 |
| Sprint 13 | **串流回覆** | 新增 `/chat/stream`，FAQ Node 答案逐字顯示；`/chat` 維持不變 |
| Sprint 14 | **Handoff 業務觸發規則** | Router 新增 `handoff_category`，把盜刷/爭議/需核准/敏感資料/情緒激動/跨帳戶各自獨立分類與記錄 |
| Sprint 15 | **真人客服對話** | 新增 `tickets`+`handoff_messages` 資料模型與 `/handoff/*` 端點，客戶端轉接後鎖定進真人客服對話畫面，新增獨立的真人客服頁面實際回覆並可標記已解決 |
| Sprint 16 | **滿意度評分（CSAT）** | 對話結束時 1-5 分評分（分數→笑臉/哭臉），低分追問原因;新增 `satisfaction_ratings` 表與 `/rating`，Dashboard 加 CSAT 區塊。也是知識優化流程的「低品質評分」原料 |
| Sprint 17 | **知識庫維護 + 熱重建索引** | 新增 `kb_entries` 表與 `/kb/*` 端點、獨立維護頁面（新增/編輯/封存/測試檢索）;markdown 官方知識維持不動，補充知識與其一起索引;`/kb/reindex` 重建並就地熱抽換 retriever，新知識即時生效不需重啟 |
| Sprint 18 | **知識優化流程** | `/gap/*` 端點與獨立頁面:LLM 聚類未解決/負評/轉真人客服訊號成主題（含 `kb_actionable` 護欄排除政策類）、依真人客服回覆生成去識別化 FAQ 草稿、客服核准/編輯/略過、核准即入庫 `kb_entries`(source=pipeline)＋熱重建、成效用代表問句檢索信心 before/after 量化 |
| Sprint 19 | **即時對話 + 訪客轉接前資料收集** | 兩邊的轉真人客服對話改用 `st.fragment(run_every=5s)` 自動更新（不重跑整頁、不清掉正在打的字）;新增 Handoff Intake Node:未登入訪客主動要求真人客服時，先問「1 銀行帳戶/2 信用卡/3 非本行客戶」＋一句問題描述，收集完才開單，客戶類別與描述寫進服務單說明與對話串;Dashboard 直條圖改橫向（中文標籤不再被轉 90 度或截斷） |
| Sprint 20 | **常見問題快捷路徑** | 空白對話顯示起始捷徑、每次回答後依「實際檢索到的來源」顯示延伸追問;候選題目人工策劃並在顯示前對當前索引檢查，未達 0.60 信心門檻者不顯示——捷徑點下去不會變成轉真人客服的死路（見 ADR-015） |
| Sprint 21 | **中文切塊修復（檢索品質）** | `chunk_text` 原以 `text.split()` 算「詞」，中文沒空格導致**整份文件變成 1 個 chunk**;改成以 markdown 標題（`##`/`###`）為邊界、每塊掛上標題路徑一起嵌入、長度改用 CJK 字元＋拉丁詞計算，`TOP_K` 3→5。量測（39 題中文/28 題英文）:正確檔案排第一 中文 54%→85%、英文 71%→100%（見 ADR-016） |
| Sprint 22 | **Mingis 改版 + 帳單問題先追問** | 助理更名 Mingis（耳機加麥克風；Dashboard 改為坐在電腦桌前的版本）、銀行名稱改為 Future銀行、所有「真人」字樣統一為「真人客服」、「知識缺口管線」更名「知識優化流程（Knowledge Improvement Pipeline）」;新增 BillClarify Node 與 Smalltalk Node（Router 先於 LLM 分類器做確定性判斷，後者讓「你好」不再被轉真人客服）;客戶端轉接畫面頂端固定顯示 Mingis 狀態列;Dashboard 的 AI 成本與延遲收進「開發者資訊」摺疊區塊、移除 Session 欄（見 ADR-017） |

---

## 7. 設計問答

**問：為什麼要用 LangGraph？**
> Sprint 1-5 的函式路由已驗證所有業務邏輯。LangGraph 提供三個好處：State 顯式追蹤（每個 Node 的輸入輸出可 log）、Node 邊界明確（新增功能不破壞現有邏輯）、條件邊（Conditional Edge）讓路由邏輯從 if/else 變成宣告式定義，更易維護。

**問：Workflow 中斷怎麼辦？**
> v1 不支援斷點續連，流程中途關閉需重新開始。生產環境的解法是把 `workflow_step` 和 `workflow_data` 存入 Redis（TTL 30 分鐘），重新連線時恢復流程狀態。

**問：同時支援多少用戶？**
> Demo 版本為單用戶展示。生產環境加入 Rate Limiting（每用戶每分鐘限 10 次呼叫）、FAQ 回答 Redis 快取（相同問題不重複呼叫 Claude API）、水平擴展（多個 FastAPI instance + Load Balancer）。

**問：FAQ Node 和 Account Node 是不是真的兩個獨立節點？**
> Sprint 6 剛重構完的時候不是——兩者共用同一個函式（`qa_node`），因為 Sprint 1-5 驗證過的行為就是 system prompt 同時帶 RAG chunks 和帳務資料，拆成兩次真正獨立的 LLM 呼叫會改變外部行為，違反那次重構「只換架構、不換行為」的前提。這是刻意先欠的技術債，不是沒想到。Sprint 7 把這筆債還了：Account Node 現在是獨立的 tool-calling Agent，只在真正需要帳務資料時才呼叫對應的 tool，FAQ Node 的 context stuffing 則保留下來當作 Router 誤判時的安全網（詳見 ADR-008、Sprint 7 design journal）。

**問：Router 現在是不是每一輪對話都要多打一次 API？**
> 不是每一輪，只有需要「理解使用者這句話是什麼意圖」的時候才打。掛失流程進行中（`workflow_step > 0`）和前端強制轉真人客服（`force_handoff`）這兩種情況是確定性的系統狀態判斷，直接跳過分類器；例如信用卡掛失走完整四步驟，只有第一句觸發訊息會呼叫一次分類器，後續三步都不用。真正每輪都會多付一次分類器成本的，是 FAQ／Account／首次要求真人客服這三種情境——換來的是不再有「信用卡年費」被關鍵字誤判成帳務查詢這類問題（詳見 ADR-009）。

**問：意圖分類信心度低、需要反問用戶的邏輯做了嗎？**
> 沒有。目前用 Claude 的 `tool_choice` 強制模型一定要從四個分類裡選一個，拿到的是確定的分類結果，沒有信心分數可以判斷「模型是不是在瞎猜」。§3.1 提到的「信心度低 → 反問（最多 2 次）」是 v1 尚未實作的功能，如果要做，需要換一種呼叫方式（例如讓模型輸出信心分數，或看 `tool_choice` 拿掉後模型會不會遲疑），目前判斷這個功能對展示核心 Agent 架構的邊際效益不高，先不做。
