---
id: autonomous-trading-agents-paper-notes-day-2
title: "Autonomous Trading Agents - Paper Notes Day 2"
sidebar_label: "Autonomous Trading Agents Day 2"
description: "Ghi chú ngày 2 về các paper liên quan đến LLM trading agents, layered memory, character design và stock trading simulation."
tags:
  - autonomous-trading-agents
  - llm-agent
  - trading
  - finance
  - layered-memory
  - multi-agent
  - stockagent
---

# Autonomous Trading Agents - Paper Notes Day 2

**Người note:** Phúc  
**Thời gian:** 26/05/2026  
**Mục tiêu:** Ghi chú lại nội dung các paper đã đọc hôm nay để sau này tra cứu nhanh.

---

## 1. Tổng quan buổi đọc hôm nay

Hôm nay em tiếp tục tìm hiểu về chủ đề **Autonomous Trading Agents**, tập trung nhiều hơn vào các hệ thống dùng **LLM agent** trong trading.

Các paper em đã tìm hiểu gồm:

1. **FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design**
2. **TradingGPT: Multi-Agent System with Layered Memory and Distinct Characters**
3. **StockAgent: LLM-based Stock Trading in Simulated Real-world Environments**

So với các paper hôm trước, hôm nay em thấy có một số ý nổi bật hơn:

- Các LLM trading agent cần có **memory** để nhớ thông tin cũ, giao dịch cũ và tín hiệu thị trường trước đó.
- Memory không nên chỉ là một đoạn context dài, mà có thể chia thành nhiều tầng như short-term, medium-term, long-term.
- Agent có thể được thiết kế với **character/personality** khác nhau, ví dụ agent thận trọng, agent ưa rủi ro, agent phân tích kỹ thuật.
- Multi-agent system giúp nhiều agent cùng phân tích hoặc tranh luận trước khi đưa ra quyết định.
- Stock trading simulation giúp kiểm tra hành vi của agent trong môi trường gần với thị trường thật hơn.

---

## 2. Paper 1: FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design

### Thông tin nhanh

- **Tên paper:** FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design
- **Chủ đề chính:** LLM trading agent với layered memory và character design
- **Vai trò trong quá trình đọc:** Hiểu cách một trading agent có thể dùng bộ nhớ nhiều tầng để cải thiện quyết định giao dịch

### Abstract nói gì?

Paper này giới thiệu **FinMem**, một framework LLM-based trading agent phục vụ financial decision-making.

Ý chính của paper là: nếu muốn LLM trở thành một agent giao dịch tốt hơn, thì chỉ dùng prompt hoặc context đơn giản là chưa đủ. Agent cần có một kiến trúc hợp lý để:

- Xử lý nhiều nguồn thông tin tài chính.
- Tạo chuỗi suy luận.
- Lưu và chọn lọc thông tin quan trọng.
- Chuyển thông tin đã nhớ thành quyết định đầu tư.

FinMem có 3 phần chính:

1. **Profiling:** thiết lập đặc điểm/character của agent.
2. **Memory:** bộ nhớ nhiều tầng để xử lý dữ liệu tài chính theo cấu trúc.
3. **Decision-making:** dùng thông tin từ memory để đưa ra quyết định đầu tư.

### Cách làm / ý tưởng chính

Ý tưởng quan trọng nhất của FinMem là **layered memory**.

Thay vì để LLM xử lý toàn bộ lịch sử như một đoạn context dài, FinMem tổ chức memory theo nhiều tầng. Cách này giống với cách con người ghi nhớ:

- Có thông tin ngắn hạn cần phản ứng nhanh.
- Có thông tin trung hạn giúp hiểu xu hướng.
- Có thông tin dài hạn giúp hình thành kinh nghiệm và chiến lược.

Ngoài ra, FinMem còn dùng **character design**, tức là thiết kế tính cách hoặc phong cách cho agent. Ví dụ một agent có thể thận trọng hơn, hoặc phản ứng mạnh hơn với tín hiệu thị trường.

### Cách implement có thể hiểu đơn giản

Một prototype đơn giản theo ý tưởng FinMem có thể như sau:

```text
Input:
- Giá cổ phiếu
- Tin tức tài chính
- Lịch sử giao dịch
- Các tín hiệu thị trường

Memory:
- Short-term memory: thông tin mới nhất
- Medium-term memory: xu hướng gần đây
- Long-term memory: kinh nghiệm và pattern quan trọng

Agent:
- Đọc thông tin từ memory
- Phân tích tình hình hiện tại
- Đưa ra quyết định buy / sell / hold

Output:
- Quyết định giao dịch
- Lý do
- Trạng thái memory được cập nhật
```

Nếu code một bản đơn giản, có thể chia thành các module:

```text
1. Data Collector
2. Memory Manager
3. Agent Profile / Character
4. Decision Maker
5. Backtesting / Evaluation
```

### Usage / dùng trong case nào?

FinMem phù hợp khi muốn:

- Xây trading agent có khả năng nhớ và học từ lịch sử.
- Thiết kế agent có phong cách giao dịch khác nhau.
- Nghiên cứu memory mechanism cho LLM agent.
- Làm prototype về LLM trading agent có memory rõ ràng.
- So sánh agent có memory và agent không có memory.

### Có gì hay?

Điểm hay của FinMem là nó không chỉ dùng LLM để phân tích một lần, mà cố gắng biến LLM thành một agent có trí nhớ.

Các điểm đáng chú ý:

- Có **layered memory**.
- Có **character design**.
- Có khả năng cập nhật theo tín hiệu thị trường mới.
- Dễ liên hệ với cách trader con người ghi nhớ thông tin và kinh nghiệm.
- Tập trung vào việc cải thiện decision-making chứ không chỉ sinh text.

### Hạn chế / điểm cần chú ý

- Thiết kế memory có thể phức tạp.
- Nếu memory lưu thông tin sai hoặc nhiễu, agent có thể ra quyết định sai.
- Character design có thể ảnh hưởng mạnh đến hành vi agent, nên cần kiểm soát kỹ.
- Cần backtesting nghiêm túc để kiểm tra hiệu quả.
- Không nên hiểu kết quả của agent là lời khuyên đầu tư thật.

### Ghi chú cá nhân

FinMem rất đáng chú ý vì nó đưa ra một hướng rõ ràng: **LLM trading agent cần memory tốt**.

Nếu sau này muốn làm prototype, có thể học theo ý tưởng này bằng cách build memory manager trước, rồi cho agent đọc memory để ra quyết định.

---

## 3. Paper 2: TradingGPT: Multi-Agent System with Layered Memory and Distinct Characters

### Thông tin nhanh

- **Tên paper đầy đủ:** TradingGPT: Multi-Agent System with Layered Memory and Distinct Characters for Enhanced Financial Trading Performance
- **Chủ đề chính:** Multi-agent trading system với layered memory và character khác nhau
- **Vai trò trong quá trình đọc:** Hiểu cách kết hợp multi-agent, memory và distinct character trong trading

### Abstract nói gì?

Paper này giới thiệu **TradingGPT**, một hệ thống multi-agent dùng LLM để hỗ trợ trading.

Vấn đề paper nêu ra là: GPT/LLM có khả năng xử lý instruction tốt, nhưng memory của LLM thông thường chưa giống cách con người ghi nhớ theo tầng. Điều này có thể khiến LLM khó ưu tiên các thông tin quan trọng và khẩn cấp trong trading.

TradingGPT giải quyết bằng cách:

- Dùng nhiều agent.
- Mỗi agent có layered memory.
- Mỗi agent có character hoặc trading trait khác nhau.
- Các agent có thể giao tiếp hoặc tranh luận với nhau.
- Hệ thống dùng thông tin lịch sử và tín hiệu thị trường để đưa ra quyết định giao dịch.

### Cách làm / ý tưởng chính

TradingGPT có 2 ý chính:

#### 1. Layered memory

Mỗi agent có memory nhiều tầng, giúp agent xử lý thông tin theo mức độ thời gian và độ quan trọng.

Ví dụ:

```text
Short-term memory:
- Tin mới nhất
- Biến động giá gần nhất

Medium-term memory:
- Xu hướng vài ngày/giai đoạn gần đây
- Các giao dịch gần đây

Long-term memory:
- Kinh nghiệm giao dịch
- Pattern lặp lại
- Chiến lược dài hạn
```

#### 2. Distinct characters

Các agent không giống nhau hoàn toàn, mà có đặc điểm riêng. Ví dụ:

- Agent thận trọng.
- Agent ưa rủi ro.
- Agent tập trung vào tin tức.
- Agent tập trung vào dữ liệu giá.
- Agent phản biện quyết định của agent khác.

Nhờ vậy, hệ thống có nhiều góc nhìn hơn thay vì chỉ có một LLM trả lời duy nhất.

### Cách implement có thể hiểu đơn giản

Một prototype theo TradingGPT có thể thiết kế như sau:

```text
Input:
- Market data
- News
- Historical trading records

Agent A:
- Character: cautious
- Memory: short / medium / long

Agent B:
- Character: aggressive
- Memory: short / medium / long

Agent C:
- Character: balanced
- Memory: short / medium / long

Process:
- Mỗi agent phân tích theo character riêng
- Các agent trao đổi hoặc debate
- Hệ thống tổng hợp ý kiến

Output:
- Buy / Sell / Hold
- Lý do từ từng agent
- Quyết định cuối cùng
```

### Usage / dùng trong case nào?

TradingGPT phù hợp khi muốn:

- Xây hệ thống trading có nhiều agent cùng phân tích.
- Thử nghiệm ảnh hưởng của character/personality lên quyết định giao dịch.
- Nghiên cứu memory trong multi-agent system.
- Làm prototype có debate giữa các agent.
- Tạo hệ thống trading assistant có nhiều quan điểm khác nhau.

### Có gì hay?

Điểm hay của TradingGPT là kết hợp cùng lúc 3 ý tưởng:

1. **LLM agent**
2. **Layered memory**
3. **Distinct characters / multi-agent debate**

Cách này làm hệ thống giống một nhóm trader hơn là một model đơn lẻ. Mỗi agent có thể nhớ, phân tích và phản ứng khác nhau, sau đó cùng thảo luận để ra quyết định.

### Hạn chế / điểm cần chú ý

- Multi-agent sẽ tốn chi phí và phức tạp hơn single-agent.
- Debate giữa các agent không đảm bảo lúc nào cũng đúng.
- Nếu nhiều agent cùng bị ảnh hưởng bởi dữ liệu sai, kết quả vẫn có thể sai.
- Cần cơ chế tổng hợp quyết định rõ ràng.
- Cần đánh giá bằng backtest và so sánh với baseline.

### Ghi chú cá nhân

TradingGPT gần với FinMem ở phần memory và character, nhưng khác ở chỗ TradingGPT nhấn mạnh **multi-agent** hơn.

Nếu FinMem là một agent có memory tốt, thì TradingGPT là nhiều agent có memory và character khác nhau cùng làm việc.

---

## 4. Paper 3: StockAgent: LLM-based Stock Trading in Simulated Real-world Environments

### Thông tin nhanh

- **Tên paper đầy đủ:** When AI Meets Finance (StockAgent): Large Language Model-based Stock Trading in Simulated Real-world Environments
- **Chủ đề chính:** Mô phỏng giao dịch cổ phiếu bằng LLM-based agents trong môi trường gần thực tế
- **Vai trò trong quá trình đọc:** Hiểu cách xây môi trường simulation để đánh giá hành vi trading của LLM agent

### Abstract nói gì?

Paper này giới thiệu **StockAgent**, một hệ thống multi-agent dùng LLM để mô phỏng hành vi giao dịch của nhà đầu tư trong môi trường thị trường chứng khoán gần với thực tế.

Paper tập trung vào câu hỏi: liệu AI agent có thể mô phỏng môi trường trading để nghiên cứu tác động của các yếu tố bên ngoài lên hành vi giao dịch không?

Các yếu tố bên ngoài có thể gồm:

- Kinh tế vĩ mô.
- Chính sách.
- Tin tức doanh nghiệp.
- Fundamental của công ty.
- Sự kiện toàn cầu.

StockAgent cho phép phân tích xem các yếu tố này ảnh hưởng như thế nào đến:

- Hành vi giao dịch.
- Lợi nhuận.
- Biến động giá cổ phiếu.
- Quyết định của investor agents.

### Cách làm / ý tưởng chính

Ý tưởng chính của StockAgent là tạo một môi trường mô phỏng gần thị trường thật, trong đó nhiều investor agents giao dịch với nhau.

Thay vì chỉ đánh giá agent bằng một chuỗi dữ liệu giá cố định, StockAgent cố gắng mô phỏng hành vi của nhiều nhà đầu tư và phản ứng của họ với thông tin thị trường.

Có thể hiểu đơn giản:

```text
External Factors:
- News
- Policy
- Macro economy
- Company fundamentals
- Global events

Investor Agents:
- Đọc thông tin
- Ra quyết định giao dịch
- Tương tác với môi trường

Market Environment:
- Ghi nhận giao dịch
- Cập nhật trạng thái thị trường
- Quan sát hành vi và kết quả
```

Một điểm quan trọng là paper chú ý đến vấn đề **test set leakage**, tức là tránh việc LLM đã biết trước dữ liệu test hoặc thông tin tương lai.

### Cách implement có thể hiểu đơn giản

Một prototype đơn giản theo StockAgent có thể là:

```text
1. Tạo danh sách investor agents
2. Gán cho mỗi agent một số đặc điểm riêng
3. Cung cấp dữ liệu thị trường và tin tức theo từng thời điểm
4. Cho agent đọc thông tin và quyết định buy / sell / hold
5. Môi trường ghi lại hành vi giao dịch
6. Đánh giá kết quả và phân tích hành vi
```

Output có thể gồm:

```text
- Hành vi giao dịch của từng agent
- Lợi nhuận/lỗ
- Ảnh hưởng của news/policy lên quyết định
- Sự thay đổi giá hoặc market dynamics trong simulation
```

### Usage / dùng trong case nào?

StockAgent phù hợp khi muốn:

- Mô phỏng hành vi investor agents trong thị trường cổ phiếu.
- Nghiên cứu tác động của news, policy, macro events lên trading.
- Đánh giá LLM agent trong môi trường gần thực tế hơn.
- Kiểm tra cách nhiều agent tương tác với nhau.
- Xây benchmark hoặc simulation environment cho LLM-based trading.

### Có gì hay?

Điểm hay của StockAgent là nó không chỉ hỏi “agent có kiếm lời không?”, mà còn hỏi:

- Agent phản ứng thế nào với sự kiện bên ngoài?
- Các yếu tố thị trường ảnh hưởng đến hành vi giao dịch ra sao?
- LLM có thể mô phỏng investor behavior không?
- Làm sao tránh việc model biết trước dữ liệu test?

Paper này hữu ích nếu muốn nghiên cứu trading agent ở góc nhìn **simulation environment**.

### Hạn chế / điểm cần chú ý

- Simulation vẫn không phải thị trường thật.
- Hành vi của LLM agent chưa chắc giống nhà đầu tư thật.
- Kết quả phụ thuộc vào cách thiết kế environment.
- Cần rất cẩn thận với leakage và dữ liệu thời gian.
- Việc mô phỏng market dynamics là bài toán khó.

### Ghi chú cá nhân

StockAgent giúp em hiểu thêm rằng trading agent không chỉ là xây agent ra quyết định, mà còn cần một môi trường mô phỏng tốt để đánh giá hành vi.

Nếu sau này làm demo hoặc research, StockAgent có thể gợi ý cách xây **simulated market environment** để test agent.

---

## 5. So sánh nhanh 3 paper hôm nay

| Paper | Hướng chính | Dùng để làm gì? | Điểm đáng nhớ |
|---|---|---|---|
| FinMem | Single LLM trading agent với layered memory và character design | Xây agent có trí nhớ và phong cách giao dịch | Memory giúp agent nhớ và chọn lọc thông tin quan trọng |
| TradingGPT | Multi-agent system với layered memory và distinct characters | Nhiều agent cùng phân tích/tranh luận để ra quyết định | Mỗi agent có memory và character riêng |
| StockAgent | LLM-based stock trading simulation | Mô phỏng hành vi giao dịch trong môi trường gần thực tế | Tập trung vào simulation, investor behavior và external factors |

---

## 6. Những ý cần nhớ sau buổi đọc hôm nay

- **Memory** là thành phần rất quan trọng trong LLM trading agent.
- Layered memory giúp agent phân biệt thông tin ngắn hạn, trung hạn và dài hạn.
- Character design giúp tạo ra các agent có phong cách giao dịch khác nhau.
- Multi-agent system có thể giúp hệ thống có nhiều góc nhìn hơn.
- Simulation environment rất quan trọng để đánh giá trading agent.
- Stock trading agent cần tránh **test set leakage** và việc model biết trước thông tin tương lai.
- Các paper hôm nay đều cho thấy trading agent đang tiến dần từ “LLM trả lời đơn lẻ” sang “hệ thống agent có memory, vai trò và môi trường đánh giá”.

---

## 7. Liên hệ với các paper hôm trước

Các paper hôm trước giúp em nắm bức tranh chung:

- **Survey paper:** hiểu tổng quan LLM agent trong trading.
- **FinRL:** hiểu hướng reinforcement learning.
- **TradingAgents:** hiểu hướng multi-agent mô phỏng trading firm.

Các paper hôm nay giúp em đi sâu hơn vào:

- **Layered memory:** FinMem, TradingGPT.
- **Character design:** FinMem, TradingGPT.
- **Multi-agent interaction:** TradingGPT, StockAgent.
- **Simulation environment:** StockAgent.

Có thể hiểu đơn giản:

```text
Hôm trước:
- Nắm tổng quan các hướng autonomous trading agents

Hôm nay:
- Đi sâu hơn vào memory, character và simulation
```

---

## 8. Câu hỏi để research tiếp

- Layered memory nên được thiết kế cụ thể như thế nào?
- Memory nên lưu những gì: news, price, action, reward, reasoning hay tất cả?
- Character của agent nên được định nghĩa bằng prompt hay bằng rule?
- Multi-agent debate có thật sự làm quyết định tốt hơn không?
- Làm sao đánh giá agent mà tránh test set leakage?
- Nên chọn FinMem, TradingGPT hay StockAgent làm hướng prototype ban đầu?
- Nếu làm demo nhỏ, nên bắt đầu từ memory module hay simulation environment trước?

---

## 9. Hướng có thể làm tiếp

Nếu tiếp tục research hoặc làm prototype, em nghĩ có thể đi theo một hướng nhỏ trước:

### Option 1: Prototype theo FinMem

Tập trung vào một agent có memory:

```text
Data → Memory Manager → LLM Decision Maker → Buy/Sell/Hold
```

Phù hợp nếu muốn hiểu sâu memory trong LLM agent.

### Option 2: Prototype theo TradingGPT

Tập trung vào nhiều agent có character khác nhau:

```text
Cautious Agent + Aggressive Agent + Balanced Agent → Debate → Final Decision
```

Phù hợp nếu muốn thử multi-agent và debate.

### Option 3: Prototype theo StockAgent

Tập trung vào môi trường mô phỏng:

```text
Market Environment + Investor Agents + External Events → Trading Behavior Analysis
```

Phù hợp nếu muốn nghiên cứu simulation và investor behavior.

---

## 10. Link tham khảo

- FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design: https://arxiv.org/abs/2311.13743
- TradingGPT: Multi-Agent System with Layered Memory and Distinct Characters for Enhanced Financial Trading Performance: https://arxiv.org/abs/2309.03736
- StockAgent: When AI Meets Finance: Large Language Model-based Stock Trading in Simulated Real-world Environments: https://arxiv.org/abs/2407.18957
- FinMem GitHub: https://github.com/pipiku915/finmem-llm-stocktrading
- StockAgent GitHub: https://github.com/MingyuJ666/Stockagent
