[English](evaluation.md) · **繁體中文**

# Evaluation Framework

Sprint 19 — 先建一份可重複跑、低成本、deterministic 的 golden set，才有基準可以證明「這次調 RAG／prompt／模型是不是真的變好」。設計上刻意先不用 LLM-as-Judge：分數的可信度來自「有標準答案可比對」，不是來自另一個模型的主觀評分。

跟 `tests/security/` 的分工：安全測試是硬性 gate（有漏洞就是 fail，不接受部分分數）；這裡是品質基準（單一 case 波動可以接受，但整體聚合指標要守住門檻），兩者故意不共用同一批 case——安全測試的 injection 字串只在 `tests/security/test_prompt_injection.py` 維護一份，這裡的「Safety pass rate」指標直接引用那個套件的通過率，不重造第二份。

## golden_cases.jsonl

`tests/eval/golden_cases.jsonl`，每行一個 JSON case，共 33 題（2026-09-01 建立基準時為 30 題，之後新增 3 題）：

| 分類 | 題數 | 檔案 |
|---|---|---|
| FAQ（檢索來源是否有依據） | 12 | `zh_faq_*` / `en_faq_*` — 涵蓋全部 9 份知識庫文件 |
| 帳務／掛失（登入、工具、workflow） | 8 | `zh_acct_*` / `en_acct_*` / `zh_cardloss_*` / `en_cardloss_*` |
| Handoff（9 條業務規則中 classify_intent 涵蓋的 7 類） | 9 | `zh_handoff_*` / `en_handoff_*`，8 正例（7 類各一題，其中 dispute_or_refund 兩題）+ 1 負例（「你搞錯了」邊界案例，precision 需要真負例才有意義） |
| 多輪對話（代名詞子句是否延續前文） | 4 | `zh_multi_*` / `en_multi_*` |

欄位（依 case 類型而定，非全部欄位都出現在每一行）：

```json
{"id": "zh_fraud_001", "category": "handoff", "language": "zh",
 "query": "我的信用卡有一筆不是我刷的消費",
 "expected_intent": "handoff", "expected_handoff_category": "fraud_or_security",
 "should_handoff": true}
```

`category` 決定跑哪個 runner；`should_handoff` 在每一行都存在（即使是 faq/account/card_loss，也明確標 `false`），這樣 handoff 的 precision/recall 才有全體 29 個單輪 case 當分母（2026-09-01 基準時為 26 個），不是只在 9 題 handoff bucket 裡自己跟自己比。

`multi_turn` 用 `"turns": [...]` 取代單一 `"query"`，最後一輪的期望值放在 `expected_intent`/`expected_sources`。

## 三個 runner

| 檔案 | 怎麼測 | 成本 |
|---|---|---|
| `test_intent_regression.py` | 直接呼叫 `classify_intent()`（跟 `tests/test_router_intent.py` 同一支函式），不跑到 FAQ/Account Node | 1 次分類 LLM call / case，每個 case 只分類一次（cache），per-case + aggregate 測試共用同一份結果 |
| `test_retrieval_regression.py` | 直接呼叫 `RAGRetriever.retrieve()`，完全不碰 LLM | 免費，跑最快 |
| `test_conversation_regression.py` | 完整走 `/chat`，依序送出 `turns`，`history`/`workflow` 像真的前端一樣接力傳遞 | 每輪一次完整生成，4 個 case 最貴 |

跑法：
```bash
pytest tests/eval/                          # 全部
pytest tests/eval/test_retrieval_regression.py   # 只跑檢索（最快、免費）
```

## v1 四個指標（2026-09-01 基準）

| 指標 | 結果 | 算法 |
|---|---|---|
| Intent accuracy | **100%**（26/26） | `test_aggregate_intent_accuracy_meets_threshold`，門檻 90% |
| Handoff precision / recall | **100% / 100%** | `test_aggregate_handoff_precision_recall_meet_threshold`，門檻各 85% |
| Retrieval hit rate（Top-5） | **100%**（14/14） | `test_aggregate_retrieval_hit_rate_meets_threshold`，門檻 90% |
| Safety pass rate | **100%**（27/27，引用 `tests/security/`） | `pytest tests/security/ -q` 的通過率 |

> 註：上表是 2026-09-01 在 30 題版本上量到的基準（單輪 26 題、檢索案例 14 題）。題庫現為 33 題（單輪 29 題、檢索案例 15 題）；所有彙總門檻測試在最近一次完整測試（2026-11-25，269 項）中通過，但上表的分子與分母**沒有**重新計算。

四個指標都在門檻之上，這份基準線可以拿來對照未來的 prompt／RAG／模型調整有沒有真的變好或變差——低於門檻時 CI 應該紅，而不是「感覺變差了」。

## RAG retrieval 升級（2026-09-03）

5 項待辦清單裡「RAG retrieval 升級：reranker／hybrid search／cache」寫的是「在有評估資料後，再決定是否真的需要」。現在有資料了——結論是**只做了一項最小修復，reranker 和 hybrid search 目前都不做**，理由如下。

### 已修：多輪對話代名詞子句遺失檢索上下文

起點是 `en_multi_003` 這組對話：
1. 「What is the daily ATM withdrawal limit?」→ 正確答出 NT$20,000（含加碼管道），`rag_sources=[atm_services.md]`。
2. 「And the per-transaction limit?」→ 有時**轉真人客服**（`atm_services.md` 裡其實有單筆提款限額的答案），有時正確回答。

根因：`qa_node`（`backend/src/agent/nodes.py`）的 `retriever.retrieve(message)` 只嵌入**當輪**的原始文字，不含對話歷史。三個多輪 case 的最後一輪單獨拿去測，分數都落在 `HIGH_CONFIDENCE_THRESHOLD`（0.60）附近或以下：

| Case | 最後一輪 | 單獨檢索分數 |
|---|---|---|
| `zh_multi_001` | 那年費呢? | 0.475 |
| `en_multi_003` | And the per-transaction limit? | 0.592 |
| `zh_multi_002` | 那匯率是用哪一種? | 0.620 |

低於門檻就會觸發 verifier，由 verifier 自己的 LLM 判斷「這些 chunk 夠不夠回答」——**這個判斷本身在多次重跑之間會變動**。同一份測試檔案連續整套跑了三次：第一次 3/4 過（`en_multi_003` 沒過）；第二次 2/4 過（換成 `zh_multi_001`、`zh_multi_002` 沒過，`en_multi_003` 反而過了）；第三次 4/4 全過。沒有任何一個 case 是「每次都掛」或「每次都過」。

一開始把 `en_multi_003` 用 `xfail(strict=True)` 標記、當成跟 `tests/security/test_authorization.py` 記錄已知漏洞一樣的手法——但這個假設是錯的：`strict=True` 預設「這個 case 會穩定失敗」，實際跑起來它反而在某一輪意外通過，`strict=True` 因此把「模型這次判對了」也算成失敗，等於誤報。已經拿掉該標記，改成誠實記錄現況——這跟 `tests/test_verifier.py` 既有的 3 個 verifier 判斷測試（同樣呼叫真實 LLM 做 sufficient/insufficient 二元判斷，同樣接受偶發雜訊）是一致的做法。

**修法**：`nodes.py` 新增 `_retrieval_query()`，把「上一輪使用者的話」接到這輪查詢前面再做 embedding（只接使用者自己的話，不接 AI 回覆，避免稀釋）。不用額外的 LLM query-rewriting call，純字串接合。修完的分數：

| Case | 修前 | 修後 |
|---|---|---|
| `zh_multi_001` | 0.475 | 0.804 |
| `en_multi_003` | 0.592 | 0.805 |
| `zh_multi_002` | 0.620 | 0.804 |

三個 case 全部從貼著門檻（甚至門檻下）推到 0.80 附近，穩穩過線。`test_conversation_regression.py` 連續乾跑 3 次都是 4/4，不再是本節上面描述的那種忽好忽壞。新增 `test_retrieval_query_folds_in_prior_user_turn`／`test_retrieval_query_unchanged_on_first_turn`（`tests/test_faq.py`）用純函式鎖住這個邏輯，不用等 LLM。

### 評估但不做：reranker

用 golden set 量了 Top-1 準確率（不只是 Top-K 有沒有命中，而是**排第一名的是不是對的**，因為 Top-1 準不準才是 reranker 真正在解的問題）：

```
Top-1 準確率：11/13 = 85%（Top-5 命中率仍是 100%，見上方四個核心指標）
```

兩個 miss 都是同一組混淆：「換外幣手續費」類問題，`transfer_rules.md` 排到 `foreign_currency_exchange.md` 前面。查了實際被檢索到的內文才發現：**「外幣」這個關鍵字兩份文件都有**（`transfer_rules.md` 的國際匯款段落也提到外幣），所以這不是「embedding 語意飄掉」或「關鍵字對不上」，是兩份文件本來就有主題重疊——跟 Sprint 21（`docs/design_journal.md`）當時記錄的「多份文件都有手續費段落的跨主題混淆」是同一類問題，只是換了兩個新問法重新量到。

**不做的理由**：Top-5 命中率已經 100%，代表正確文件永遠有進到 LLM 的 context，兩個 miss 只影響「排序好不好看」跟 `rag_sources` 徽章準不準，不影響客戶拿到的答案對不對。Reranker 要嘛加一個 cross-encoder 模型（多一次推論延遲、多一個模型要維護），要嘛額外呼叫一次 API（多一筆成本），換來的是一個目前對答案正確性沒有實質影響的排序優化。n=13 也太小，不足以評斷「加了 reranker 真的能穩定解決這個混淆」還是「剛好這兩題被修好、換兩題被弄壞」。

比 reranker 便宜的下一步（如果之後真的要動）：像 Sprint 21 那樣直接改善這兩份文件的內容切分/標題，讓「換外幣現鈔」和「國際匯款」的段落語意更分開——這是內容問題，不一定要用模型架構解決。

### 評估但不做：hybrid search（BM25 + embedding）

原本預期 hybrid search（關鍵字比對 + 向量語意）能補上「embedding 語意類似但關鍵字對不上」的案例。但上面那組 miss 剛好反過來證明了這條路對這個語料庫沒什麼用——**兩份混淆的文件關鍵字是重疊的**，BM25 一樣會給兩份文件都打高分，不會比純 embedding 更會分辨。知識庫目前只有 84（中）+ 79（英）個 chunk，內容也都是自然語言 FAQ，沒有商品代碼、帳號、精確數字這種「embedding 抓不到但關鍵字抓得到」的查詢類型——這正是 hybrid search 真正該解決的場景，而這個語料庫幾乎不存在。

**結論**：目前資料不支持做 hybrid search。如果之後知識庫擴充到需要查精確代碼/條款編號等關鍵字敏感內容，這個結論要重新評估。

### cache

原始待辦裡也提過 cache。這輪沒有評估，因為它解的是成本/延遲問題，不是這次 benchmark 在量的正確性問題——跟前面兩項不同類，等 tracing/成本監控那個待辦項目做了、有實際延遲/花費數字之後再評估比較合理。

## 核實政策量測：什麼時候該檢查「資料夠不夠答」（2026-11-21）

**起因（第一手實測）**：一題很長的海外退款問題（「退款台幣比原本少、1.5% 手續費沒退，為什麼？」），在知識庫**沒有**退款規則時，檢索最高分是 **0.664**，高於 0.60 的核實門檻，於是跳過核實，模型用鬆散相關的段落回答，還補了知識庫沒有的理由（「這是大多數銀行的共同做法」）。這正是核實機制本來要擋的「看似合理、其實不一定正確」。

**量測**（`claude-haiku-4-5`，核實 `temperature=0`）：

- 可回答的題目：知識庫自己的 62 題 Q&A（中 39／英 23）。
- 知識庫確定沒有答案的題目：12 題（用關鍵字確認主題不在知識庫內；另 2 題原本也算缺口，後來確認其實有相關內容，排除）。

| 何時核實 | 擋下的真缺口 | 答得出來卻轉人 | 核實次數 |
|---|---|---|---|
| 分數低於 0.60（原本） | **5 / 12** | 3 / 62 | 15 / 62 |
| 分數低於 0.75 | 11 / 12 | 10 / 62 | 53 / 62 |
| **每次都核實（現在）** | **12 / 12** | 11 / 62 | 62 / 62 |

- **缺口題的分數是 0.54–0.76，答得出來的題目中位數 0.66，兩邊重疊**，任何單一分數門檻都分不開（與 Sprint 12 的結論一致，這次是更大樣本）。分得開的只有核實本身的判斷：12 題真缺口它全部判定「資料不足」。
- 「答得出來卻轉人」的 11 題裡，4 題是檢索根本沒找到那篇（此時轉人其實是對的），7 題（約 11%）是核實較嚴格。
- 代價：每則 FAQ 回答多一次小型模型呼叫，實機首字時間約 3 秒（演練：年費、ATM 題首字 2.9–3.2 秒）。

**決策**：每次 FAQ 回答前都核實（`VERIFY_ALWAYS`，預設開，設 `0` 可退回舊行為），見 ADR-020。

**更嚴的核實順便挖出的檢索弱點**（尚未修）：77 題人工整理的捷徑裡，有 7 題檢索把**錯的段落**排第一，例如「國內轉帳的手續費怎麼算？」排第一的是**國際匯款**手續費。核實判斷「資料不足」是對的（同一輸入連跑 6 次結果一致）。這 7 題已從捷徑清單移除，檢索本身的改善（例如 rerank 或針對性切塊）列為待辦；`tests/test_shortcuts_verified.py` 確保剩下的捷徑都通過核實。

**限制（請如實引用）**：樣本小（62 + 12），缺口題由我依「知識庫沒有這個主題」人工挑選，不是隨機抽樣；「答得出來」的題目用的是知識庫自己的 Q&A 原句，比真實客戶的問法容易，所以誤擋比例在真實流量上可能更高。這是方向性證據，不是準確率。

## 盜刷判斷量測：「我沒有消費過的款項」這類說法（2026-11-23）

**起因（第一手實測）**：Dashboard 上「帳單裡有一筆不明款項，我未消費過此筆金額」被歸為一般的帳務爭議，沒有標成緊急盜刷。盜刷完全由 LLM 分類器的提示詞判斷（沒有關鍵字規則），所以要量測、要修的是提示詞。

**量測**（`claude-haiku-4-5`；12 種盜刷說法與 7 種非盜刷說法，各跑 4 次）：

| 階段 | 盜刷說法被判成盜刷 | 其他說法維持在正確類別 |
|---|---|---|
| 修正前 | 40 / 48 | 28 / 28 |
| 第一版修正（凡是客戶說不是自己消費、不認識的款項一律算盜刷） | 48 / 48 | 24 / 28 |
| 第二版修正（另加：自己消費過但被重複扣款，仍是爭議） | **48 / 48** | **28 / 28** |

- 修正前的漏判集中在兩種說法，每次都錯（4/4）：上面那句（被歸為爭議），以及 "I don't recognize this transaction on my bill"（被歸為查詢帳務）。其他十種說法本來就正確。
- 第一版修正帶來一個副作用：「商家對我扣了兩次款」開始被判成盜刷（4/4）。第二版修正消除了它，之後連續兩輪完整測試都是 76 次分類全中。
- 分類器現在也以 `temperature=0` 執行，同一句話永遠走同一條路。`tests/test_fraud_intent.py`（會呼叫真實模型）防止它退步。

**限制**：19 種人工挑選的說法。這證明「這些說法現在被正確分流」，不證明所有說法都能判對（口語、方言、打錯字的寫法沒有測）。

## 怎麼加新 case

1. 在 `golden_cases.jsonl` 加一行，`id` 前綴用語言（`zh_`/`en_`）+ 類別，例如 `zh_faq_011`。
2. `category` 決定會被哪個 runner 撿到：`faq`/`account`/`card_loss`/`handoff` 進 `test_intent_regression.py`；有 `expected_sources` 的（faq 或 multi_turn）額外進 `test_retrieval_regression.py`；`multi_turn` 進 `test_conversation_regression.py`。
3. FAQ/multi_turn 案例的 `expected_sources` 建議先手動跑一次 retriever 確認 Top-K 真的命中（`tests/eval/test_retrieval_regression.py` 開頭有 `RETRIEVERS` 可以直接在 REPL 裡試），避免寫一條從一開始就是錯的期望值進版本庫。

## 之後：LLM-as-Judge（尚未實作）

第一版四個指標都是 deterministic 比對（intent 字串相等、來源字串包含、handoff 布林值）。之後要加的是針對**答案品質**本身的評分——groundedness、relevance、completeness、tone，各 1–5 分。設計上會遵守幾個原則，避免 v1 的 deterministic 特性被稀釋：

- Judge 的 model、prompt 版本、呼叫成本、原始回覆（不只是分數）都要保留，才能事後複查「是 judge 判錯還是真的答錯」。
- Judge 分數是輔助訊號，不是絕對真實答案——不能拿它去覆蓋 deterministic 指標的紅燈，只能在 deterministic 都綠的情況下，用來比較「這個答案有沒有比較好」這種光靠字串比對測不出來的差異。
- 不會跟 v1 的四個指標混在同一個聚合門檻裡；會是獨立的第五個指標，獨立報告、獨立門檻。
