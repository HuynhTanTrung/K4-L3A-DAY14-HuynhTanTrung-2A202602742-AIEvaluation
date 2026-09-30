# Day 14 — Reflection

## Evaluation Report & Failure Analysis

Dùng kết quả thật trong `artifacts/benchmark_results.json` và kiểm tra lại
answer/context trace trong `artifacts/actual_answers.json` trước khi kết luận.

---

## 1. Benchmark Results Summary

**Overall pass rate:** 40%

| Metric            | Average |   Min |   Max | Nhận xét                                                 |
| ----------------- | ------: | ----: | ----: | -------------------------------------------------------- |
| Context Recall    |   0.875 | 0.083 | 1.000 | Tốt — retriever phủ evidence đầy đủ, trừ A01             |
| Context Precision |   0.915 | 0.000 | 1.000 | Tốt — ranking ổn định, chunk relevant đứng sớm           |
| Faithfulness      |   0.642 | 0.000 | 1.000 | Needs Work — nhiều answer bị cắt cụt hoặc không grounded |
| Relevance         |   0.409 | 0.000 | 0.882 | Significant Issues — answer không khớp trọng tâm         |
| Completeness      |   0.448 | 0.031 | 1.000 | Significant Issues — thiếu thông tin, câu dở dang        |
| Overall Score     |   0.500 | 0.010 | 0.859 | Significant Issues — trung bình ngay ngưỡng pass         |

**Score interpretation**

- Metrics/cases ở mức Good (0.8–1.0): Context Recall (0.875), Context Precision (0.915); cases E01 (0.800), E05 (0.812), M02 (0.859)
- Metrics/cases ở mức Needs Work (0.6–0.8): Faithfulness (0.642), cases E02, E03, E04, M01, H05, A02
- Metrics/cases ở mức Significant Issues (<0.6): Relevance (0.409), Completeness (0.448), Overall (0.500), cases M04, M05, M06, M07, H01, H02, H03, H04, A01, A03

**Failure type distribution**

| Failure Type  | Count | Percentage |
| ------------- | ----: | ---------: |
| hallucination |     3 |        25% |
| irrelevant    |     5 |      41.7% |
| incomplete    |     1 |       8.3% |
| off_topic     |     3 |        25% |
| refusal       |     0 |         0% |

**Chẩn đoán tổng quan:** Vấn đề chính nằm ở retrieval, generation hay cả hai?
Dùng ít nhất hai metrics để bảo vệ kết luận.

> _Câu trả lời:_ Vấn đề chính nằm ở generation, Context Recall (0.875) và Context Precision (0.915) đều ở mức Good,retriever lấy đúng và xếp đúng evidence. Nhưng Relevance (0.409) và Completeness (0.448) ở mức Significant Issues. Kiểm tra trace trong actual_answers.json cho thấy nhiều answer bị cắt cụt giữa câu (E04: "three to five", M04: "For a store-pickup order,", M05: "Based on the retrieved context, the customer should:", H02: "No. The 4", H04: "Diagnosis"), dấu hiệu max_output_tokens=300 quá thấp hoặc model dừng sớm. Retrieval tốt nhưng generation không tận dụng hết context → pipeline có vấn đề ở bước sinh câu trả lời

---

## 2. Top 3 Worst Failures — 5 Whys

Phân loại failure trước khi đề xuất fix. Với mỗi case, kiểm tra cả gold evidence
và retrieved chunks; không suy luận chỉ từ một score.

### Failure 1

**ID và question:**

> _Điền:_ H02 — "An OrbitPlus member placed an order on September 2, 2026 and requests a return for an opened device 20 days after delivery. Does the 45-day membership window make it eligible?"

**Expected answer:**

> _Điền:_ No. Return Policy version 2.0 applies (order placed on/after September 1, 2026), which allows 14 calendar days for opened devices. The 45-day OrbitPlus benefit extends only the unopened-device window, not the opened-device window. At 20 days after delivery, the opened device is outside the 14-day window and is not eligible

**Actual answer:**

> _Điền:_ "No. The 4"

**Scores:** Context Recall: 0.781 | Context Precision: 1.000 | Faithfulness: 0.000 | Relevance: 0.000 | Completeness: 0.031 | Overall: 0.010

**Evidence inspection:**

> _Câu trả lời:_ Retriever lấy đúng evidence: OT-09-P04 (policy versioning — nêu rõ 45-day benefit chỉ áp dụng cho unopened), OT-03-P05 ("It does not extend the 14-day opened-device window"), OT-05-P01 (v2.0 opened window = 14 days). Context Precision = 1.000 nghĩa là chunk relevant đứng đầu. Nhưng model chỉ sinh được "No. The 4" rồi dừng — generation fail, không phải retrieval

| Level   | Question                                                | Answer                                                                                               |
| ------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Symptom | Vấn đề quan sát được là gì?                             | Answer chỉ có "No. The 4", không trả lời được câu hỏi, faithfulness và relevance = 0                 |
| Why 1   | Tại sao symptom xảy ra?                                 | Model dừng sinh giữa câu, không hoàn thành lập luận                                                  |
| Why 2   | Tại sao nguyên nhân trên xảy ra?                        | max_output_tokens=300 quá thấp cho câu hỏi multi-step cần giải thích policy version + window         |
| Why 3   | Tại sao vấn đề đó chưa được ngăn chặn?                  | Prompt không yêu cầu "always finish your response" và không có retry/continuation khi output bị cắt  |
| Why 4   | Tại sao cơ chế hiện tại chưa phát hiện hoặc xử lý được? | Không có guardrail kiểm tra output kết thúc bằng dấu câu hoàn chỉnh, stop_reason không được kiểm tra |
| Why 5   | Root cause có thể hành động được là gì?                 | Token budget quá nhỏ + không có cơ chế detect/retry truncated output                                 |

**Root cause từ `find_root_cause()`:**

> _Paste output:_ "Context is missing or irrelevant — improve retrieval"

**Bạn đồng ý hay không? Dẫn evidence từ trace:**

> _Câu trả lời:_ Không đồng ý. find_root_cause() chỉ so sánh ba score và chọn thấp nhất — nhưng ở đây faithfulness = 0 vì answer rỗng/cụt, không phải vì context thiếu. Context Precision = 1.000 và Recall = 0.781 chứng minh retriever lấy đúng evidence. Root cause thật nằm ở generation token limit, không phải retrieval. Đây là hạn chế của heuristic đơn giản trong lab

**Proposed fix cụ thể:**

> _Câu trả lời:_ Tăng max_output_tokens từ 300 lên 800–1000 trong OpenAIGenerator. Thêm post-check: nếu output không kết thúc bằng ./!/? hoặc finish_reason == "length", retry với continuation prompt. Thêm instruction trong \_build_prompt: "Always complete your final sentence; if running out of space, prioritize the direct answer first."

### Failure 2

**ID và question:**

> _Điền:_ M06 — "An order is already Packing and the customer wants to change its destination country. Can they edit the address, and what is the stated alternative?"

**Expected answer:**

> _Điền:_ No. The shipping address may only be edited while the order is Confirmed. Changing the destination country is never allowed for security reasons — the customer must cancel and place a new order. Since the order is already Packing, cancellation is also no longer guaranteed; support may request carrier interception, but fees are non-refundable and success is not guaranteed

**Actual answer:**

> _Điền:_ "No, they cannot edit the address. The"

**Scores:** Context Recall: 0.950 | Context Precision: 1.000 | Faithfulness: 0.200 | Relevance: 0.200 | Completeness: 0.100 | Overall: 0.167

**Evidence inspection:**

> _Câu trả lời:_ Retriever lấy đúng OT-02-P05 (address edit rules + destination country never allowed + must cancel and re-order) và OT-08-P02 (packing → interception not guaranteed). Context Precision = 1.000 — chunk relevant đứng đầu. Answer bị cắt ở "The" — thiếu hoàn toàn phần alternative (cancel + re-order) và điều kiện Packing

| Level   | Question                                                | Answer                                                                                               |
| ------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Symptom | Vấn đề quan sát được là gì?                             | Answer cụt ở "The", thiếu phần alternative và điều kiện Packing                                      |
| Why 1   | Tại sao symptom xảy ra?                                 | Model dừng sinh sau khi trả lời "No"                                                                 |
| Why 2   | Tại sao nguyên nhân trên xảy ra?                        | Câu hỏi có 2 phần nhưng model ưu tiên phần 1, hết token trước phần 2                                 |
| Why 3   | Tại sao vấn đề đó chưa được ngăn chặn?                  | Prompt không có instruction "answer every part of the question" một cách mạnh mẽ; max_tokens vẫn 300 |
| Why 4   | Tại sao cơ chế hiện tại chưa phát hiện hoặc xử lý được? | Không có check cho multi-part question coverage, completeness metric chỉ tính sau khi đã sinh xong   |
| Why 5   | Root cause có thể hành động được là gì?                 | Prompt không enforce multi-part answer + token budget thiếu                                          |

**Root cause và proposed fix:**

> _Câu trả lời:_ Root cause: token budget + prompt không enforce trả lời đủ các phần. Fix: tăng max_tokens lên 800, thêm instruction cuối prompt: "The question has multiple parts — address each explicitly.", thêm few-shot example cho multi-part question trong prompt

### Failure 3

**ID và question:**

> _Điền:_ M05 — "A customer suspects account compromise and finds an unauthorized order still marked Confirmed. What should they do?"

**Expected answer:**

> _Điền:_ The customer should: (1) reset password from a trusted device, (2) revoke active sessions, (3) enable multi-factor authentication, (4) contact Account Security, and (5) attempt cancellation under 02_orders_and_payments.md since the order is still Confirmed. If it were already packing/dispatched, Account Security would coordinate with Payments and Delivery, but cancellation/interception is not guaranteed

**Actual answer:**

> _Điền:_ "Based on the retrieved context, the customer should:"

**Scores:** Context Recall: 0.920 | Context Precision: 0.950 | Faithfulness: 0.400 | Relevance: 0.143 | Completeness: 0.040 | Overall: 0.194

**Evidence inspection:**

> _Câu trả lời:_ Retriever lấy đúng OT-08-P02 (chứa đầy đủ 5 bước: reset password, revoke sessions, enable MFA, contact Account Security, attempt cancellation) và OT-00-P04 (safety rules). Context Precision = 0.950. Answer chỉ có preamble "Based on the retrieved context, the customer should:" rồi dừng — không liệt kê bước nào

| Level   | Question                                                | Answer                                                                                                     |
| ------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Symptom | Vấn đề quan sát được là gì?                             | Answer chỉ có preamble, không có nội dung actionable                                                       |
| Why 1   | Tại sao symptom xảy ra?                                 | Model sinh phần mở đầu rồi dừng trước khi vào danh sách bước                                               |
| Why 2   | Tại sao nguyên nhân trên xảy ra?                        | Token budget cạn sau preamble; prompt "Answer concisely without a generic preamble" bị model bỏ qua        |
| Why 3   | Tại sao vấn đề đó chưa được ngăn chặn?                  | Prompt instruction mâu thuẫn: vừa "concise" vừa cần liệt kê 5 bước; không có negative example cấm preamble |
| Why 4   | Tại sao cơ chế hiện tại chưa phát hiện hoặc xử lý được? | Không có output validation check "answer phải chứa ít nhất 1 action verb"                                  |
| Why 5   | Root cause có thể hành động được là gì?                 | Prompt chưa enforce "no preamble, start with the answer" + token budget thiếu                              |

**Root cause và proposed fix:**

> _Câu trả lời:_ Preamble chiếm token + instruction "concise" mơ hồ. Fix: đổi prompt thành "Do NOT start with phrases like 'Based on the context'. Start directly with the answer.", thêm few-shot example answer bắt đầu bằng bullet list, tăng max_tokens lên 800

---

## 3. Failure Clustering

Một root cause có thể tạo ra nhiều failures. Nhóm theo nguyên nhân có thể sửa,
không chỉ nhóm theo tên metric.

| Cluster | Root Cause                                                                                                                                               | Failure IDs                                      | Priority |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | -------- |
| 1       | Generation bị cắt cụt do max_output_tokens=300 quá thấp — answer dừng giữa câu, không hoàn thành                                                         | E04, M04, M05, M06, M07, H01, H02, H03, H04, A03 | High     |
| 2       | Prompt không enforce trả lời đủ multi-part + cấm preamble, model sinh phần mở đầu hoặc chỉ trả lời phần đầu                                              | M05, M06, A03                                    | High     |
| 3       | Adversarial out-of-scope không được redirect đúng — A01 trả lời "insufficient evidence" nhưng không redirect sang supported topics như OT-00-P03 yêu cầu | A01                                              | Medium   |

**Nếu chỉ được sửa một cluster, bạn chọn cluster nào và vì sao?**

> _Câu trả lời:_ Chọn Cluster 1 — vì nó ảnh hưởng đến 10/12 failures và là root cause chung của hầu hết các case có Overall < 0.5. Chỉ cần tăng max_output_tokens từ 300 → 800 và thêm retry-on-truncation, dự kiến pass rate sẽ tăng từ 40% lên khoảng 65–75% vì nhiều case có retrieval tốt nhưng generation bị cắt. Đây là fix rẻ nhất, impact lớn nhất — đúng nguyên tắc "fix 1 root cause giải quyết nhiều failures cùng lúc" trong lecture

---

## 4. Improvement Log

Paste output của `generate_improvement_log()`:

```text
| Failure ID | Type | Root Cause | Suggested Fix | Status |
|------------|------|------------|---------------|--------|
| F001 | off_topic | Answer does not address the question — improve prompt clarity | Increase chunk size in RAG pipeline to reduce context fragmentation | Open |
| F002 | off_topic | Answer does not address the question — improve prompt clarity | Add few-shot examples showing complete answers to improve completeness | Open |
| F003 | irrelevant | Answer does not address the question — improve prompt clarity | Improve prompt clarity and intent detection to keep answers on topic | Open |
| F004 | irrelevant | Multiple issues detected — review full pipeline | Add intent classification guardrail to redirect off-topic queries | Open |
| F005 | hallucination | Context is missing or irrelevant — improve retrieval | Review retrieval pipeline and rerank chunks by relevance | Open |
| F006 | off_topic | Answer does not address the question — improve prompt clarity | Expand golden dataset with adversarial cases to catch edge failures | Open |
| F007 | irrelevant | Answer does not address the question — improve prompt clarity | Calibrate LLM judge against human labels to reduce scoring drift | Open |
| F008 | hallucination | Context is missing or irrelevant — improve retrieval | Increase chunk size in RAG pipeline to reduce context fragmentation | Open |
| F009 | incomplete | Answer is missing key information — increase context window or improve generation | Add few-shot examples showing complete answers to improve completeness | Open |
| F010 | irrelevant | Answer does not address the question — improve prompt clarity | Improve prompt clarity and intent detection to keep answers on topic | Open |
| F011 | hallucination | Context is missing or irrelevant — improve retrieval | Implement hallucination checker to filter unsupported claims | Open |
| F012 | irrelevant | Answer does not address the question — improve prompt clarity | Review retrieval pipeline and rerank chunks by relevance | Open |
```

**Ba improvement suggestions ưu tiên**

1. Tăng max_output_tokens từ 300 → 800 và thêm retry-on-truncation — fix Cluster 1
2. Sửa prompt: cấm preamble + enforce multi-part coverage — fix Cluster 2
3. Thêm few-shot example cho adversarial out-of-scope: nêu rõ role + gợi ý supported topics — fix Cluster 3

Với mỗi suggestion, nêu metric dự kiến thay đổi và cách đo lại.

| Suggestion              | Target metric               | Verification method                                                                                                                      |
| ----------------------- | --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Tăng max_tokens + retry | Completeness, Relevance     | Chạy lại python domain_assistant.py + python evaluate_answers.py, so sánh avg Completeness (kỳ vọng ≥ 0.65) và pass rate (kỳ vọng ≥ 65%) |
| Sửa prompt              | Relevance, Faithfulness     | A/B test 2 prompt versions trên cùng golden dataset; so sánh Relevance trung bình (kỳ vọng ≥ 0.60)                                       |
| Few-shot adversarial    | Pass rate của A01, A02, A03 | Chạy lại 3 adversarial cases; kiểm tra A01 có redirect sang supported topics không                                                       |

---

## 5. Regression Testing Strategy

**Câu 1: Khi nào chạy `run_regression()` trong production workflow?**

> _Câu trả lời:_ Chạy run_regression() trong các trigger sau: mỗi code release — bất kỳ thay đổi nào trong retriever, prompt, hoặc generator parameters, mỗi prompt change — vì prompt ảnh hưởng trực tiếp đến faithfulness/relevance, trước demo/launch — chạy full suite để đảm bảo không có regression, định kỳ hàng tuần — để phát hiện drift do model provider cập nhật. So sánh với baseline lưu trong artifacts/benchmark_results.json

**Câu 2: Threshold drop 0.05 có phù hợp OrbitTech Customer Support không? Vì sao?**

> _Câu trả lời:_ Phù hợp cho giai đoạn dev, nhưng nên siết chặt hơn cho production. Với domain customer support, một drop 0.05 ở Faithfulness có thể nghĩa là ~1 câu trả lời bịa thông tin về warranty/refund — hậu quả pháp lý và mất trust. Đề xuất: 0.03 cho Faithfulness, 0.05 cho Relevance và Completeness. Ngoài ra nên dùng absolute threshold song song: block nếu Faithfulness < 0.7 bất kể baseline

**Câu 3: Metric/failure nào phải block deployment, metric nào chỉ alert?**

> _Câu trả lời:_ Block deployment: Faithfulness < 0.70 — hallucination về policy/giá/ngày tháng có thể gây hậu quả thực tế, bất kỳ failure type "hallucination" nào xuất hiện, bất kỳ adversarial case nào fail safety. Chỉ alert: Relevance drop 0.05–0.10 — giảm chất lượng nhưng không gây hại, Completeness drop nhẹ — user có thể hỏi lại, off_topic tăng nhẹ — theo dõi trend, không block

**Câu 4: Điền evaluation stages vào flow.**

```text
Code/prompt/retrieval change → [Offline eval trên golden dataset] → [Regression check vs baseline] → [Human review cho case mới/adversarial] → Deploy
```

> _Giải thích:_ Offline eval chạy 20 QA pairs để đo 5 metrics. Regression check so sánh với baseline — nếu bất kỳ metric nào drop > threshold → block. Human review chỉ cần cho các case mới thêm vào golden dataset hoặc adversarial cases chưa có ground truth tin cậy. Sau khi pass cả 3 bước → deploy. Trong production, tiếp tục online eval để phát hiện drift

---

## 6. Continuous Improvement Loop

```text
Evaluate → Analyze → Improve → Augment benchmark → Repeat
```

| Priority | Action                                                 | Metric dự kiến cải thiện         | Expected impact                              |
| -------: | ------------------------------------------------------ | -------------------------------- | -------------------------------------------- |
|        1 | Tăng max_output_tokens 300 → 800 + retry-on-truncation | Completeness, Relevance, Overall | Pass rate 40% → 65–75%; 10 failures được fix |
|        2 | Sửa prompt: cấm preamble, enforce multi-part answer    | Relevance, Faithfulness          | Relevance 0.41 → 0.60+; giảm off_topic       |
|        3 | Thêm few-shot cho adversarial out-of-scope             | A01 pass, Safety                 | A01 được redirect đúng theo OT-00-P03        |

**Hai hoặc ba failure cases nào cần thêm vào benchmark ở vòng tiếp theo?**

> _Câu trả lời:_

--- (1) Policy version boundary — order đúng ngày Sep 1, 2026 để test xem model có phân biệt "on or after" vs "before" không.
(2) Multi-condition warranty — device mua qua OrbitPay, hỏng trong warranty, nhưng instalment fail → test xem model có phân biệt "account suspended" vs "warranty void"

## 7. Final Reflection

**Điều gì trong kết quả benchmark trái với dự đoán ban đầu của bạn?**

> _Câu trả lời:_ Dự đoán ban đầu là retrieval sẽ là bottleneck vì corpus có 10 documents và BM25 chỉ là lexical retrieval đơn giản. Nhưng kết quả cho thấy ngược lại: Context Recall = 0.875 và Context Precision = 0.915 — retriever làm rất tốt. Bottleneck thật là generation: max_output_tokens=300 quá thấp khiến 10/12 failures có answer bị cắt cụt. Điều này cho thấy trong RAG pipeline, retrieval tốt không đủ nếu generation không được cấu hình đúng — một bài học quan trọng về việc kiểm tra toàn bộ pipeline chứ không chỉ từng component riêng lẻ

**Word-overlap heuristics trong lab có giới hạn gì? Nếu đưa hệ thống vào
production, bạn sẽ thay hoặc bổ sung metric nào?**

> _Câu trả lời:_ Word-overlap không hiểu ngữ nghĩa, không phân biệt đúng/sai, phạt paraphrase đúng, và bỏ qua phủ định. Production nên bổ sung: LLM-as-Judge với rubric domain-specific, NLI-based faithfulness, RAGAS/DeepEval thật với claim-level decomposition, human review định kỳ, và online metrics
