---
id: autonomous-trading-agents-architecture-pipeline-notes-day-3
title: "Autonomous Trading Agents - Architecture & Pipeline Notes Day 3"
sidebar_label: "Architecture & Pipeline Notes Day 3"
description: "Ghi chú ngày 3 về autonomous trading agents, bổ sung kiến trúc và pipeline đề xuất để review."
tags:
  - autonomous-trading-agents
  - llm-agent
  - market-simulation
  - stockbench
  - reinforcement-learning
  - multi-agent
  - algorithmic-collusion
  - architecture
  - pipeline
---

# Autonomous Trading Agents - Architecture & Pipeline Notes Day 3

**Người note:** Phúc  
**Thời gian:** 27/05/2026  
**Mục tiêu:** Ghi chú lại các paper đã đọc hôm nay, đồng thời bổ sung thêm phần **kiến trúc**, **pipeline** và **insight** để review lại sau này.

> Lưu ý: Đây là ghi chú phục vụ research, không phải lời khuyên đầu tư.

---

## 1. Bối cảnh hôm nay

Hôm nay em tiếp tục tìm hiểu về chủ đề **Autonomous Trading Agents**, với 4 paper:

1. **ABIDES: Towards High-Fidelity Market Simulation for AI Research**
2. **StockBench: Can LLM Agents Trade Stocks Profitably in Real-world Markets?**
3. **A Multi-agent Deep Reinforcement Learning Framework for Optimizing Financial Trading Strategies**
4. **AI-Powered Trading, Algorithmic Collusion, and Price Efficiency**

Sau khi đọc các paper này, em thấy trọng tâm hôm nay không chỉ là agent tự trade, mà còn mở rộng sang:

- Cách **mô phỏng thị trường** để test agent.
- Cách **benchmark LLM trading agent** trong môi trường gần thực tế.
- Cách dùng **multi-agent reinforcement learning** để tối ưu chiến lược.
- Rủi ro khi nhiều AI trading agents cùng hoạt động, ví dụ **algorithmic collusion** và ảnh hưởng đến **price efficiency**.

---

## 2. Tóm tắt nhanh 4 paper

## 2.1. ABIDES: Towards High-Fidelity Market Simulation for AI Research

### Paper nói gì?

ABIDES là một framework mô phỏng thị trường tài chính theo hướng **agent-based discrete-event simulation**.

Mục tiêu chính là tạo ra một môi trường mô phỏng đủ chi tiết để nghiên cứu AI trading agents, thay vì chỉ backtest đơn giản trên dữ liệu giá lịch sử.

### Ý chính cần nhớ

ABIDES mô phỏng thị trường bằng nhiều thành phần:

- Trading agents.
- Exchange agent.
- Order book.
- Message passing.
- Network latency.
- Cơ chế gửi lệnh, khớp lệnh và ghi nhận giao dịch.

### Usage

Dùng khi muốn test trading agent trong môi trường gần thị trường thật hơn, đặc biệt khi cần nghiên cứu:

- Market microstructure.
- Order book.
- Latency.
- Market impact.
- Tương tác giữa nhiều agents.

### Điểm hay

Điểm hay của ABIDES là nó giúp chuyển từ tư duy **backtest đơn giản** sang tư duy **market simulation**.

Một trading agent nếu chỉ test bằng dữ liệu lịch sử thì chưa đủ. Nếu muốn nghiêm túc hơn, cần môi trường mô phỏng có exchange, order book, nhiều agents và tương tác thị trường.

---

## 2.2. StockBench: Can LLM Agents Trade Stocks Profitably in Real-world Markets?

### Paper nói gì?

StockBench là một benchmark để đánh giá liệu **LLM agents có thể trade stock có lợi nhuận trong môi trường gần thực tế hay không**.

Paper này đặt vấn đề rằng nhiều benchmark tài chính trước đây chủ yếu test kiến thức tài chính dạng hỏi đáp, nhưng trading lại là bài toán động, phải ra quyết định liên tục theo thời gian.

### Ý chính cần nhớ

StockBench cho agent trade theo từng ngày trong nhiều tháng.

Agent nhận các thông tin như:

- Market data.
- News.
- Fundamentals.
- Market signals.

Sau đó agent đưa ra quyết định:

```text
Buy / Sell / Hold
```

Kết quả được đánh giá bằng các metric như:

- Cumulative return.
- Maximum drawdown.
- Sortino ratio.
- So sánh với baseline như buy-and-hold.

### Usage

Dùng khi muốn benchmark LLM trading agents, xem agent có thực sự trade tốt không, thay vì chỉ trả lời câu hỏi tài chính tốt.

### Điểm hay

StockBench giúp trả lời câu hỏi rất thực tế:

> LLM giỏi hiểu tài chính có đồng nghĩa với việc trade tốt không?

Điểm quan trọng là paper cho thấy cần đánh giá agent bằng môi trường động và metric tài chính, không chỉ bằng financial QA.

---

## 2.3. A Multi-agent Deep Reinforcement Learning Framework for Optimizing Financial Trading Strategies

### Paper nói gì?

Paper này đề xuất một framework **multi-agent deep reinforcement learning** để tối ưu chiến lược giao dịch tài chính.

Ý tưởng là thay vì chỉ dùng một RL agent, hệ thống dùng nhiều agent với các **investment preference** khác nhau, sau đó tổng hợp chiến lược bằng một cấu trúc phân cấp.

### Ý chính cần nhớ

Các agent khác nhau có thể học các chiến lược khác nhau, ví dụ:

- Agent ưu tiên lợi nhuận.
- Agent ưu tiên giảm rủi ro.
- Agent phản ứng với biến động ngắn hạn.
- Agent quan tâm xu hướng dài hạn.

Sau đó hệ thống tổng hợp output của các agent để đưa ra quyết định cuối cùng.

Paper cũng dùng mô hình xử lý time-series như **TimesNet** để trích xuất đặc trưng từ dữ liệu tài chính.

### Usage

Dùng khi muốn nghiên cứu autonomous trading agent theo hướng **RL-based strategy learning**, không phụ thuộc chính vào LLM.

### Điểm hay

Paper này cho thấy multi-agent không chỉ xuất hiện trong LLM, mà cũng rất quan trọng trong reinforcement learning.

Nó giúp em thấy một hướng khác:

```text
LLM agent → mạnh về reasoning và dữ liệu text
RL agent → mạnh về học chiến lược từ dữ liệu/time-series
```

---

## 2.4. AI-Powered Trading, Algorithmic Collusion, and Price Efficiency

### Paper nói gì?

Paper này nghiên cứu rủi ro khi nhiều AI trading agents cùng hoạt động trên thị trường.

Ý chính là các AI agents, đặc biệt là reinforcement learning agents, có thể tự học ra hành vi giống **algorithmic collusion** dù không có giao tiếp trực tiếp hoặc thỏa thuận rõ ràng.

Điều này có thể làm giảm cạnh tranh và ảnh hưởng đến **price efficiency**.

### Ý chính cần nhớ

Paper không chỉ hỏi:

> AI trading agent có kiếm tiền được không?

Mà hỏi thêm:

> Nếu nhiều AI trading agents cùng tối ưu lợi nhuận, chúng có thể làm thị trường kém cạnh tranh hơn không?

### Usage

Dùng để bổ sung góc nhìn về:

- Risk.
- Ethics.
- Regulation.
- Market fairness.
- Tác động hệ thống của AI trading.

### Điểm hay

Paper này giúp mở rộng chủ đề autonomous trading agents từ góc độ kỹ thuật sang góc độ thị trường và quản lý rủi ro.

Một trading agent tốt không chỉ cần profitable, mà còn cần xem xét tác động đến thị trường nếu nhiều agent cùng hoạt động.

---

# 3. Kiến trúc tổng hợp sau khi đọc các paper

Dựa trên 4 paper hôm nay, em thử tổng hợp một kiến trúc chung cho hệ thống nghiên cứu **Autonomous Trading Agents** như sau.

## 3.1. High-level Architecture

```text
+----------------------+
|  Data Sources         |
|----------------------|
| Price / Volume        |
| News                  |
| Fundamentals          |
| Macro events          |
| Order book            |
+----------+-----------+
           |
           v
+----------------------+
| Data Processing Layer |
|----------------------|
| Cleaning              |
| Feature extraction    |
| Time-series features  |
| News summarization    |
| Signal generation     |
+----------+-----------+
           |
           v
+-----------------------------+
| Agent Layer                  |
|-----------------------------|
| LLM Trading Agent            |
| RL Trading Agent             |
| Multi-agent RL Agents        |
| Risk / Monitoring Agent      |
+-------------+---------------+
              |
              v
+-----------------------------+
| Decision Layer               |
|-----------------------------|
| Buy / Sell / Hold            |
| Position sizing              |
| Portfolio update             |
| Risk check                   |
+-------------+---------------+
              |
              v
+-----------------------------+
| Evaluation / Simulation      |
|-----------------------------|
| StockBench-style benchmark   |
| ABIDES-style simulation      |
| Backtesting metrics          |
| Market impact analysis       |
+-------------+---------------+
              |
              v
+-----------------------------+
| Insight & Governance Layer   |
|-----------------------------|
| Performance analysis         |
| Collusion detection          |
| Price efficiency analysis    |
| Regulation / risk notes      |
+-----------------------------+
```

## 3.2. Giải thích kiến trúc

Kiến trúc này chia hệ thống thành 6 lớp:

### 1. Data Sources

Đây là nơi lấy dữ liệu đầu vào.

Có thể gồm:

- Giá cổ phiếu.
- Khối lượng giao dịch.
- Tin tức.
- Báo cáo tài chính.
- Dữ liệu vĩ mô.
- Order book nếu muốn mô phỏng sâu hơn.

### 2. Data Processing Layer

Lớp này biến dữ liệu thô thành tín hiệu có thể dùng được.

Ví dụ:

- Làm sạch dữ liệu giá.
- Tạo technical indicators.
- Tóm tắt tin tức.
- Trích xuất đặc trưng time-series.
- Chuẩn hóa input cho agent.

### 3. Agent Layer

Đây là phần lõi của hệ thống.

Có thể có nhiều loại agent:

- **LLM Trading Agent:** đọc news, fundamentals, market signals và đưa ra reasoning.
- **RL Trading Agent:** học chiến lược giao dịch từ dữ liệu và reward.
- **Multi-agent RL Agents:** nhiều agent có preference khác nhau.
- **Risk Agent:** kiểm tra rủi ro trước khi quyết định được chấp nhận.

### 4. Decision Layer

Lớp này chuyển output của agent thành hành động cụ thể.

Ví dụ:

- Buy.
- Sell.
- Hold.
- Mua bao nhiêu.
- Bán bao nhiêu.
- Có vượt risk limit không.

### 5. Evaluation / Simulation Layer

Đây là lớp đánh giá.

Có thể đánh giá theo 2 hướng:

- **StockBench-style:** agent trade từng ngày trên dữ liệu lịch sử, sau đó tính metric.
- **ABIDES-style:** mô phỏng thị trường có exchange, order book và nhiều agents.

### 6. Insight & Governance Layer

Lớp này dùng để phân tích sâu hơn sau khi chạy agent.

Ví dụ:

- Agent trade có lời không?
- Drawdown có lớn không?
- Agent có overfit không?
- Nếu nhiều agent cùng trade thì có collusion-like behavior không?
- Agent có làm giảm price efficiency không?

---

# 4. Pipeline đề xuất sau khi đọc các paper

## 4.1. Pipeline 1: LLM Trading Agent Benchmark Pipeline

Pipeline này lấy cảm hứng từ **StockBench**.

Mục tiêu là đánh giá LLM agent trong môi trường trading theo ngày.

```text
Step 1: Chọn danh sách cổ phiếu
        ↓
Step 2: Thu thập dữ liệu theo ngày
        - Price
        - Volume
        - News
        - Fundamentals
        ↓
Step 3: Tạo input cho LLM agent mỗi ngày
        ↓
Step 4: LLM agent đưa ra quyết định
        - Buy
        - Sell
        - Hold
        - Reasoning
        ↓
Step 5: Cập nhật portfolio
        - Cash
        - Holdings
        - Portfolio value
        ↓
Step 6: Lặp lại trong nhiều ngày/tháng
        ↓
Step 7: Tính metrics
        - Cumulative return
        - Maximum drawdown
        - Sharpe / Sortino
        - Win rate
        ↓
Step 8: So sánh với baseline
        - Buy and hold
        - Random strategy
        - Moving average strategy
```

### Insight từ pipeline này

Pipeline này phù hợp nhất nếu muốn làm prototype sớm, vì không cần mô phỏng order book quá phức tạp.

Có thể bắt đầu bằng bản đơn giản:

```text
Daily data → LLM → Buy/Sell/Hold → Portfolio update → Metrics
```

Sau đó mới nâng cấp thêm news, fundamentals, risk check.

---

## 4.2. Pipeline 2: ABIDES-style Market Simulation Pipeline

Pipeline này lấy cảm hứng từ **ABIDES**.

Mục tiêu là test agent trong môi trường mô phỏng thị trường chi tiết hơn.

```text
Step 1: Khởi tạo market simulator
        ↓
Step 2: Tạo exchange agent
        - Order book
        - Matching engine
        - Transaction records
        ↓
Step 3: Tạo nhiều trading agents
        - Noise agent
        - Value agent
        - Momentum agent
        - AI trading agent
        ↓
Step 4: Thiết lập latency và message passing
        ↓
Step 5: Agents gửi order đến exchange
        ↓
Step 6: Exchange xử lý và khớp lệnh
        ↓
Step 7: Cập nhật trạng thái thị trường
        - Best bid / ask
        - Price
        - Volume
        - Order book depth
        ↓
Step 8: Ghi log hành vi agents
        ↓
Step 9: Phân tích kết quả
        - PnL
        - Market impact
        - Liquidity
        - Volatility
```

### Insight từ pipeline này

Pipeline này phù hợp cho nghiên cứu nghiêm túc hơn, nhưng sẽ khó hơn pipeline StockBench-style.

Nếu mới bắt đầu prototype thì chưa nên nhảy ngay vào ABIDES đầy đủ. Nên hiểu logic trước:

```text
Agent → Order → Exchange → Order book → Trade → Market state update
```

---

## 4.3. Pipeline 3: Multi-agent RL Trading Strategy Pipeline

Pipeline này lấy cảm hứng từ bài **Multi-agent Deep Reinforcement Learning**.

Mục tiêu là dùng nhiều RL agents để học các chiến lược khác nhau, rồi tổng hợp quyết định.

```text
Step 1: Chuẩn bị dữ liệu time-series
        - Price
        - Volume
        - Technical indicators
        ↓
Step 2: Trích xuất đặc trưng
        - TimesNet / time-series encoder
        ↓
Step 3: Tạo nhiều RL agents
        - Profit-seeking agent
        - Risk-averse agent
        - Short-term agent
        - Long-term agent
        ↓
Step 4: Mỗi agent quan sát state riêng
        ↓
Step 5: Mỗi agent đề xuất action
        - Buy
        - Sell
        - Hold
        - Position weight
        ↓
Step 6: Hierarchical aggregator tổng hợp action
        ↓
Step 7: Environment trả reward
        ↓
Step 8: Update policy của agents
        ↓
Step 9: Backtest và so sánh với baseline
```

### Insight từ pipeline này

Pipeline này mạnh về học chiến lược từ dữ liệu, nhưng khó implement hơn LLM-agent pipeline.

Nó phù hợp nếu mục tiêu là nghiên cứu sâu về RL trading, còn nếu mục tiêu là demo nhanh về autonomous trading agents thì nên để pipeline này ở giai đoạn sau.

---

## 4.4. Pipeline 4: Algorithmic Collusion & Market Impact Pipeline

Pipeline này lấy cảm hứng từ bài **AI-Powered Trading, Algorithmic Collusion, and Price Efficiency**.

Mục tiêu là không chỉ đánh giá profit của agent, mà còn xem nhiều AI agents có tạo tác động xấu lên thị trường không.

```text
Step 1: Tạo market environment
        ↓
Step 2: Tạo nhiều AI trading agents
        - Agent A
        - Agent B
        - Agent C
        ↓
Step 3: Mỗi agent tối ưu profit qua nhiều vòng giao dịch
        ↓
Step 4: Quan sát hành vi agents
        - Có cạnh tranh mạnh không?
        - Có giữ spread cao không?
        - Có tránh cạnh tranh trực tiếp không?
        ↓
Step 5: Đo market-level metrics
        - Price efficiency
        - Trading volume
        - Liquidity
        - Profit level
        - Collusion-like behavior
        ↓
Step 6: So sánh với competitive baseline
        ↓
Step 7: Rút ra risk / regulation insight
```

### Insight từ pipeline này

Pipeline này quan trọng nếu viết phần **risk / governance / regulation**.

Nó nhắc rằng autonomous trading agents không chỉ cần được đánh giá bằng câu hỏi:

```text
Agent có lời không?
```

Mà còn phải hỏi:

```text
Nếu nhiều agent cùng chạy, thị trường có bị ảnh hưởng xấu không?
```

---

# 5. Kiến trúc prototype em nghĩ nên ưu tiên

Sau khi tổng hợp các paper, em nghĩ nếu cần làm prototype nhỏ thì nên đi theo hướng **StockBench-style LLM Trading Agent Benchmark** trước.

## 5.1. Lý do chọn hướng này

So với các hướng khác:

- Dễ làm hơn ABIDES.
- Dễ giải thích hơn multi-agent RL.
- Gần với chủ đề LLM trading agents.
- Có thể đo kết quả bằng metric rõ ràng.
- Có thể mở rộng thêm memory, risk agent hoặc multi-agent sau.

## 5.2. Prototype MVP đề xuất

```text
Input:
- Daily stock price
- Basic market indicators
- Optional: daily news summary

Agent:
- LLM Trading Agent

Decision:
- Buy / Sell / Hold
- Reasoning
- Confidence score

Portfolio:
- Cash
- Holdings
- Portfolio value

Evaluation:
- Return
- Maximum drawdown
- Sharpe / Sortino
- Compare with buy-and-hold
```

## 5.3. Pipeline MVP

```text
Data loader
    ↓
Daily context builder
    ↓
LLM decision maker
    ↓
Risk checker
    ↓
Portfolio simulator
    ↓
Metrics calculator
    ↓
Report generator
```

## 5.4. Sau MVP có thể mở rộng

Sau khi có MVP, có thể mở rộng theo các hướng:

### Thêm memory

Lấy ý tưởng từ FinMem / TradingGPT:

```text
Daily decisions → Memory → Next day context
```

Agent sẽ nhớ:

- Các quyết định cũ.
- Lý do cũ.
- Kết quả lời/lỗ.
- Tin tức quan trọng trước đó.

### Thêm multi-agent

Lấy ý tưởng từ TradingAgents / TradingGPT:

```text
Technical Agent + News Agent + Risk Agent → Final Decision
```

### Thêm simulator sâu hơn

Lấy ý tưởng từ ABIDES:

```text
Agent action → Order → Exchange simulation → Market impact
```

### Thêm risk / governance

Lấy ý tưởng từ bài collusion:

```text
Multiple agents → Detect collusion-like behavior → Market impact analysis
```

---

# 6. Insights mới rút ra sau khi gen architecture/pipeline

## Insight 1: Trading agent không chỉ là LLM trả lời Buy/Sell/Hold

Ban đầu có thể nghĩ trading agent chỉ cần đọc input rồi trả lời buy/sell/hold.

Nhưng sau khi tổng hợp các paper, em thấy một hệ thống đầy đủ cần nhiều lớp:

```text
Data → Agent → Decision → Simulation → Evaluation → Risk/Governance
```

## Insight 2: Evaluation quan trọng gần bằng agent architecture

Một agent nghe có vẻ thông minh nhưng nếu không có benchmark tốt thì rất khó biết nó có thực sự hiệu quả không.

StockBench và ABIDES cho thấy evaluation cần được thiết kế nghiêm túc.

## Insight 3: Có hai hướng đánh giá khác nhau

Có thể chia evaluation thành 2 mức:

```text
Mức 1: Portfolio-level evaluation
- Agent có lời không?
- Drawdown thế nào?
- Có hơn buy-and-hold không?

Mức 2: Market-level evaluation
- Agent ảnh hưởng thị trường ra sao?
- Có gây liquidity problem không?
- Có collusion-like behavior không?
```

## Insight 4: LLM agent và RL agent có thế mạnh khác nhau

LLM agent mạnh ở:

- Đọc news.
- Giải thích quyết định.
- Kết hợp dữ liệu text.
- Reasoning.

RL agent mạnh ở:

- Học chiến lược từ dữ liệu.
- Tối ưu reward.
- Phù hợp với time-series và môi trường lặp lại.

Có thể sau này kết hợp:

```text
LLM Agent: phân tích thông tin
RL Agent: tối ưu action
Risk Agent: kiểm soát quyết định
```

## Insight 5: Simulator là phần rất quan trọng nếu muốn research nghiêm túc

Nếu chỉ backtest đơn giản thì chưa đủ để hiểu hành vi của agent.

ABIDES cho thấy cần nghĩ đến:

- Order book.
- Exchange.
- Latency.
- Message passing.
- Market impact.

Tuy nhiên phần này khá khó, nên có thể để sau MVP.

## Insight 6: Risk không chỉ là rủi ro lỗ tiền

Trước đây em nghĩ risk chủ yếu là drawdown hoặc loss.

Nhưng bài về algorithmic collusion cho thấy risk còn có thể là:

- Agent làm giảm cạnh tranh.
- Agent ảnh hưởng price efficiency.
- Agent tạo hành vi collusion-like.
- Agent gây rủi ro ở cấp độ thị trường.

---

# 7. Những việc cần làm thêm

## 7.1. Về paper reading

Cần đọc kỹ hơn các phần sau:

- Architecture diagram của từng paper.
- Experimental setup.
- Dataset.
- Evaluation metrics.
- Baseline.
- Limitations.

## 7.2. Về research notes

Các notes tiếp theo nên ghi thêm:

- Paper này dùng kiến trúc gì?
- Pipeline thực nghiệm là gì?
- Input/output của hệ thống là gì?
- Có thể implement lại tối giản như thế nào?
- Paper này dùng metric gì?
- Điểm nào có thể dùng cho prototype?

## 7.3. Về prototype

Có thể chọn một hướng prototype nhỏ:

```text
StockBench-style LLM Trading Agent Benchmark
```

Các module cần làm nếu đi theo hướng này:

1. Data loader.
2. Daily context builder.
3. LLM decision maker.
4. Risk checker.
5. Portfolio simulator.
6. Metrics calculator.
7. Report generator.

## 7.4. Về review với mentor

Có thể hỏi mentor:

- Nên đi theo hướng prototype LLM-agent benchmark trước không?
- Có cần tìm hiểu sâu ABIDES ngay không, hay để sau?
- Nên ưu tiên LLM agent, RL agent hay simulator?
- Với mục tiêu hiện tại, nên tập trung architecture hay implementation?
- Các paper tiếp theo nên chọn theo hướng benchmark, simulator hay risk/governance?

---

# 8. So sánh nhanh các hướng sau khi tổng hợp

| Hướng | Paper liên quan | Dễ prototype? | Giá trị research | Ghi chú |
|---|---|---:|---:|---|
| LLM trading benchmark | StockBench | Cao | Cao | Phù hợp MVP nhất |
| Market simulator | ABIDES | Thấp | Rất cao | Mạnh nhưng khó |
| Multi-agent RL | Multi-agent DRL paper | Trung bình - thấp | Cao | Cần hiểu RL tốt |
| Risk / collusion analysis | AI-Powered Trading & Collusion | Trung bình | Cao | Hữu ích cho phần risk/governance |

---

# 9. Kết luận tạm thời

Sau buổi đọc hôm nay và phần tổng hợp architecture/pipeline, em thấy chủ đề **Autonomous Trading Agents** có thể chia thành 4 lớp nghiên cứu chính:

1. **Agent architecture:** agent được thiết kế như thế nào.
2. **Trading pipeline:** dữ liệu đi qua các bước nào để thành quyết định.
3. **Evaluation / simulation:** đánh giá agent bằng benchmark hoặc simulator nào.
4. **Risk / market impact:** agent có gây rủi ro cho thị trường không.

Nếu cần chọn hướng thực tế để làm tiếp, em nghĩ nên bắt đầu từ:

```text
StockBench-style LLM Trading Agent Benchmark
```

Sau đó có thể mở rộng dần:

```text
+ Memory
+ Multi-agent roles
+ Risk checker
+ Market simulation
+ Collusion / market impact analysis
```

Cách đi này vừa đủ đơn giản để prototype, vừa có thể liên kết với nhiều paper đã đọc trước đó.

---

## 10. Link tham khảo

- ABIDES: Towards High-Fidelity Market Simulation for AI Research: https://arxiv.org/abs/1904.12066
- ABIDES GitHub: https://github.com/abides-sim/abides
- StockBench: Can LLM Agents Trade Stocks Profitably in Real-world Markets?: https://arxiv.org/abs/2510.02209
- A Multi-agent Reinforcement Learning Framework for Optimizing Financial Trading Strategies Based on TimesNet: https://www.sciencedirect.com/science/article/abs/pii/S0957417423020043
- AI-Powered Trading, Algorithmic Collusion, and Price Efficiency: https://www.nber.org/papers/w34054
