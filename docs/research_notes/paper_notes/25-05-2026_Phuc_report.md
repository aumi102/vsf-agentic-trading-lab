---
id: autonomous-trading-agents-paper-notes
title: "Autonomous Trading Agents - Paper Notes"
sidebar_label: "Autonomous Trading Agents"
description: "Ghi chú ngắn gọn về các paper đã đọc liên quan đến autonomous trading agents."
tags:
  - autonomous-trading-agents
  - llm-agent
  - trading
  - finance
  - reinforcement-learning
  - multi-agent
---

# Autonomous Trading Agents - Paper Notes

**Người note:** Phúc  
**Thời gian:** 25/05/2026  
**Mục tiêu:** Ghi chú lại nội dung các paper đã đọc để sau này tra cứu nhanh.

> Lưu ý: Đây là ghi chú phục vụ research, không phải lời khuyên đầu tư.

---

## 1. Tổng quan chủ đề

**Autonomous Trading Agents** là hướng nghiên cứu về việc dùng AI agent để hỗ trợ hoặc tự động hóa quá trình phân tích và ra quyết định trong giao dịch tài chính.

Một trading agent thường có thể làm một hoặc nhiều việc sau:

- Thu thập dữ liệu thị trường.
- Đọc tin tức, báo cáo tài chính hoặc dữ liệu liên quan.
- Phân tích xu hướng, rủi ro và cơ hội.
- Đưa ra quyết định như **buy / sell / hold**.
- Đánh giá lại quyết định thông qua backtesting hoặc các chỉ số hiệu quả.

Qua các paper đã đọc, em thấy có 3 hướng tiếp cận chính:

1. **LLM Agent trong trading**  
   Dùng mô hình ngôn ngữ lớn để đọc hiểu, phân tích và suy luận từ dữ liệu tài chính.

2. **Reinforcement Learning trong trading**  
   Cho agent học cách giao dịch thông qua môi trường mô phỏng và reward.

3. **Multi-Agent Trading System**  
   Dùng nhiều agent với các vai trò khác nhau để cùng phân tích, tranh luận và ra quyết định.

---

## 2. Paper 1: Large Language Model Agent in Financial Trading: A Survey

### Thông tin nhanh

- **Tên paper:** Large Language Model Agent in Financial Trading: A Survey
- **Chủ đề chính:** Survey về LLM agent trong tài chính/trading
- **Vai trò trong quá trình đọc:** Dùng để nắm bức tranh tổng quan của lĩnh vực

### Abstract nói gì?

Paper này tổng hợp các nghiên cứu về việc sử dụng **Large Language Model agents** trong giao dịch tài chính.

Ý chính là: trading không chỉ cần dữ liệu giá, mà còn cần hiểu tin tức, báo cáo, sự kiện và các tín hiệu thị trường. Vì LLM có khả năng xử lý ngôn ngữ tốt, nên có thể được dùng như một agent để hỗ trợ phân tích và ra quyết định giao dịch.

Paper cũng nói về:

- Kiến trúc thường gặp của LLM trading agent.
- Các loại dữ liệu đầu vào.
- Cách đánh giá hiệu quả bằng backtesting.
- Các thách thức và hướng nghiên cứu tiếp theo.

### Cách làm / ý tưởng chính

Paper này không đề xuất một model cụ thể, mà đóng vai trò **survey**.

Nó giúp phân loại và tổng hợp các hướng đang có trong LLM-based trading agents, ví dụ:

- Agent đọc tin tức rồi đưa ra nhận định.
- Agent kết hợp dữ liệu giá với dữ liệu ngôn ngữ.
- Agent tạo tín hiệu giao dịch.
- Agent được đánh giá bằng backtest.

Có thể hiểu paper này như một bản đồ tổng quan để biết lĩnh vực này đang có những hướng nào.

### Cách implement có thể hiểu đơn giản

Nếu áp dụng theo hướng paper này, một prototype đơn giản có thể là:

```text
Input:
- Dữ liệu giá cổ phiếu
- Tin tức tài chính
- Báo cáo hoặc sự kiện liên quan

Process:
- LLM đọc và tóm tắt thông tin
- LLM phân tích tác động của thông tin đó
- Agent đưa ra nhận định: tích cực / tiêu cực / trung lập
- Agent đề xuất hành động: buy / sell / hold

Output:
- Tín hiệu giao dịch
- Lý do giải thích quyết định
```

### Usage / dùng trong case nào?

Paper này phù hợp khi muốn:

- Tìm hiểu tổng quan về LLM agent trong trading.
- Biết các hướng research đang có.
- Lấy ý tưởng để thiết kế architecture ban đầu.
- Làm phần literature review cho chủ đề autonomous trading agents.
- So sánh LLM agent với các hướng truyền thống như rule-based hoặc reinforcement learning.

### Có gì hay?

Điểm hay của paper này là nó giúp nhìn trading agent theo hướng **system**, không chỉ là một model dự đoán giá.

Nó nhấn mạnh rằng LLM có thể hữu ích trong phần xử lý thông tin dạng text, ví dụ:

- News.
- Financial reports.
- Market sentiment.
- Analyst comments.
- Economic events.

### Hạn chế / điểm cần chú ý

- Vì là survey nên paper không cung cấp một framework cụ thể để chạy ngay.
- LLM có thể hallucinate, nên không thể tin hoàn toàn vào kết quả phân tích.
- Trading là bài toán rủi ro cao, cần backtesting và risk management nghiêm túc.
- Kết quả tốt trong backtest chưa chắc dùng được trong thị trường thật.

### Ghi chú cá nhân

Paper này nên dùng để hiểu **bức tranh tổng quan** trước. Nếu sau này làm research topic hoặc xây prototype, có thể quay lại paper này để tìm taxonomy, hướng tiếp cận và các challenge chính.

---

## 3. Paper 2: FinRL: Deep Reinforcement Learning Framework to Automate Trading in Quantitative Finance

### Thông tin nhanh

- **Tên paper:** FinRL: Deep Reinforcement Learning Framework to Automate Trading in Quantitative Finance
- **Chủ đề chính:** Deep Reinforcement Learning cho automated trading
- **Vai trò trong quá trình đọc:** Đại diện cho hướng reinforcement learning trong trading

### Abstract nói gì?

Paper này giới thiệu **FinRL**, một framework mã nguồn mở dùng **Deep Reinforcement Learning** để tự động hóa trading trong quantitative finance.

Vấn đề paper muốn giải quyết là: xây dựng một trading agent bằng DRL thường khó, vì cần xử lý dữ liệu, tạo môi trường giao dịch, định nghĩa reward, huấn luyện agent và backtest. FinRL cung cấp một framework theo dạng pipeline để làm các bước này dễ hơn.

### Cách làm / ý tưởng chính

FinRL coi trading như một bài toán reinforcement learning.

Agent sẽ học thông qua vòng lặp:

```text
Quan sát thị trường → Chọn hành động → Nhận reward → Cải thiện chiến lược
```

Các thành phần chính:

- **State:** trạng thái thị trường, ví dụ giá, volume, chỉ báo kỹ thuật, số dư tài khoản.
- **Action:** hành động như mua, bán, giữ hoặc phân bổ danh mục.
- **Reward:** phần thưởng, thường dựa trên lợi nhuận hoặc hiệu quả danh mục.
- **Environment:** môi trường mô phỏng thị trường từ dữ liệu lịch sử.

### Cách implement có thể hiểu đơn giản

Một pipeline dùng FinRL có thể hiểu như sau:

```text
1. Lấy dữ liệu thị trường
2. Tiền xử lý dữ liệu
3. Tạo trading environment
4. Chọn thuật toán DRL
5. Train agent
6. Backtest chiến lược
7. Đánh giá kết quả
```

Ví dụ case đơn giản:

```text
Input:
- Historical stock price
- Technical indicators

Agent:
- Học khi nào nên buy / sell / hold

Output:
- Trading strategy
- Backtest result
```

### Usage / dùng trong case nào?

FinRL phù hợp khi muốn:

- Thử nghiệm trading agent theo hướng reinforcement learning.
- Làm stock trading, portfolio allocation hoặc crypto trading.
- So sánh các thuật toán DRL trong cùng một môi trường.
- Xây dựng baseline thực nghiệm cho automated trading.
- Học cách mô hình hóa trading thành bài toán state-action-reward.

### Có gì hay?

Điểm hay của FinRL là nó cung cấp framework khá đầy đủ, không chỉ nói lý thuyết.

Nó có các điểm hữu ích:

- Có pipeline rõ ràng.
- Có thể dùng cho nhiều loại thị trường.
- Có thể backtest.
- Có thể mở rộng/customize.
- Giúp giảm độ khó khi bắt đầu với DRL trading.

### Hạn chế / điểm cần chú ý

- Agent có thể học quá khớp với dữ liệu lịch sử.
- Reward design không đơn giản.
- Trading ngoài thực tế có nhiều yếu tố khó mô phỏng như phí giao dịch, thanh khoản, trượt giá, tâm lý thị trường.
- Nếu chỉ backtest trên dữ liệu quá khứ thì chưa đủ để kết luận hệ thống tốt.

### Ghi chú cá nhân

FinRL là paper/framework nên đọc nếu muốn hiểu hướng **RL-based trading agent**. Nếu sau này cần làm prototype có code thật, FinRL có thể là điểm bắt đầu tốt hơn so với việc tự build toàn bộ từ đầu.

---

## 4. Paper 3: TradingAgents: Multi-Agents LLM Financial Trading Framework

### Thông tin nhanh

- **Tên paper:** TradingAgents: Multi-Agents LLM Financial Trading Framework
- **Chủ đề chính:** Multi-agent LLM framework cho financial trading
- **Vai trò trong quá trình đọc:** Đại diện cho hướng dùng nhiều LLM agent phối hợp để ra quyết định trading

### Abstract nói gì?

Paper này đề xuất một framework tên là **TradingAgents**, sử dụng nhiều LLM agent để mô phỏng cách một công ty trading hoạt động.

Thay vì để một agent tự phân tích và quyết định, hệ thống chia thành nhiều vai trò khác nhau, ví dụ:

- Fundamental analyst.
- Sentiment analyst.
- Technical analyst.
- Trader.
- Bull researcher.
- Bear researcher.
- Risk manager.

Các agent cùng phân tích, tranh luận và tổng hợp thông tin để đưa ra quyết định giao dịch.

### Cách làm / ý tưởng chính

Ý tưởng chính là trading cần nhiều góc nhìn, nên dùng multi-agent sẽ hợp lý hơn single-agent.

Có thể hiểu workflow đơn giản như sau:

```text
Dữ liệu thị trường / tin tức / báo cáo
        ↓
Các analyst agent phân tích theo từng góc nhìn
        ↓
Bull researcher và Bear researcher tranh luận
        ↓
Trader tổng hợp ý kiến
        ↓
Risk manager kiểm tra rủi ro
        ↓
Đưa ra quyết định cuối cùng
```

Điểm quan trọng là framework này mô phỏng cách làm việc của một trading firm, trong đó mỗi người/agent có một vai trò riêng.

### Cách implement có thể hiểu đơn giản

Nếu build một bản prototype đơn giản theo ý tưởng TradingAgents, có thể làm như sau:

```text
Agent 1: Technical Analyst
- Phân tích giá và indicator

Agent 2: Sentiment Analyst
- Đọc tin tức và đánh giá sentiment

Agent 3: Fundamental Analyst
- Đọc thông tin cơ bản của công ty

Agent 4: Trader
- Tổng hợp các phân tích

Agent 5: Risk Manager
- Kiểm tra rủi ro trước khi ra quyết định

Output:
- Buy / Sell / Hold
- Lý do
- Mức độ rủi ro
```

### Usage / dùng trong case nào?

TradingAgents phù hợp khi muốn:

- Nghiên cứu multi-agent system trong finance.
- Xây dựng trading assistant có nhiều vai trò phân tích.
- Làm prototype agent có khả năng tranh luận và phản biện.
- Kết hợp nhiều nguồn dữ liệu như price, news, financial report, sentiment.
- Thiết kế hệ thống AI có bước risk management trước khi ra quyết định.

### Có gì hay?

Điểm hay nhất là framework này không để một LLM quyết định một mình.

Nó có cơ chế:

- Chia vai trò rõ ràng.
- Có nhiều góc nhìn phân tích.
- Có tranh luận bull/bear.
- Có risk management.
- Có quy trình giống trading firm thật.

Điều này làm hệ thống có vẻ đáng tin hơn so với một single-agent chỉ đọc input rồi trả lời buy/sell/hold.

### Hạn chế / điểm cần chú ý

- Multi-agent có thể phức tạp và tốn chi phí hơn single-agent.
- Nếu các agent đều dựa vào LLM thì vẫn có rủi ro hallucination.
- Chất lượng output phụ thuộc nhiều vào prompt, dữ liệu đầu vào và cách orchestration.
- Cần kiểm chứng kỹ bằng backtesting và baseline.
- Không nên xem kết quả của agent là lời khuyên đầu tư trực tiếp.

### Ghi chú cá nhân

TradingAgents là paper thú vị nhất nếu muốn đi theo hướng **LLM + multi-agent + finance**. Paper này có thể dùng làm cảm hứng để thiết kế prototype nhiều agent, trong đó mỗi agent có vai trò riêng và có bước phản biện/risk check trước khi ra quyết định.

---

## 5. So sánh nhanh 3 paper

| Paper | Hướng chính | Dùng để làm gì? | Điểm đáng nhớ |
|---|---|---|---|
| Large Language Model Agent in Financial Trading: A Survey | Survey về LLM agent trong trading | Nắm tổng quan lĩnh vực | LLM có thể dùng để phân tích dữ liệu text trong tài chính |
| FinRL | Deep Reinforcement Learning | Xây/training trading agent bằng RL | Trading có thể mô hình hóa bằng state, action, reward, environment |
| TradingAgents | Multi-agent LLM | Mô phỏng trading firm với nhiều agent | Nhiều agent cùng phân tích, tranh luận và quản trị rủi ro |

---

## 6. Những ý cần nhớ sau buổi đọc

- Autonomous trading agents không chỉ là model dự đoán giá.
- Một hệ thống trading agent thường cần dữ liệu, phân tích, quyết định, backtest và risk management.
- LLM phù hợp với dữ liệu dạng text như news, reports, sentiment.
- Reinforcement learning phù hợp để học chiến lược từ môi trường giao dịch.
- Multi-agent phù hợp khi muốn hệ thống có nhiều góc nhìn và cơ chế phản biện.
- Backtesting rất quan trọng nhưng không đủ để đảm bảo hiệu quả trong thị trường thật.
- Với trading, cần luôn chú ý rủi ro, data leakage, overfitting và hallucination.

---

## 7. Câu hỏi để research tiếp

- Nếu làm prototype nhỏ thì nên bắt đầu từ FinRL hay TradingAgents?
- Dữ liệu nào dễ dùng nhất cho bản demo đầu tiên?
- Nên đánh giá trading agent bằng metric nào?
- Làm sao kiểm soát hallucination khi dùng LLM trong trading?
- Có nên kết hợp LLM agent với RL agent không?
- Risk manager agent nên kiểm tra những tiêu chí nào?

---

## 8. Link tham khảo

- Large Language Model Agent in Financial Trading: A Survey: https://arxiv.org/abs/2408.06361
- FinRL: Deep Reinforcement Learning Framework to Automate Trading in Quantitative Finance: https://arxiv.org/abs/2111.09395
- TradingAgents: Multi-Agents LLM Financial Trading Framework: https://arxiv.org/abs/2412.20138
- TradingAgents project page: https://tradingagents-ai.github.io/
- TradingAgents GitHub: https://github.com/tauricresearch/tradingagents
