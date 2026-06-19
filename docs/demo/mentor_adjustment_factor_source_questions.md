---
title: mentor_adjustment_factor_source_questions
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Adjustment Factor Source Questions

Anh ơi, em đã làm xong khung adjusted OHLC và factor verification trong repo:

- DB đã có cột adjusted OHLC và provenance cho factor.
- Có readiness gate để chặn backtest nếu adjusted OHLC chưa đủ.
- Có local factor application cho symbol explicit.
- Có parser/verification cho payload adjusted close hoặc corporate action.
- Verification hiện chỉ chạy local payload, không tự fetch live.

Phần còn thiếu là nguồn factor thật được approve. Anh confirm giúp em nên dùng
nguồn nào cho adjusted close hoặc corporate action/factor:

1. Dùng adjusted close từ vendor có được không, hay bắt buộc derive factor từ
   dividend/split/corporate action?
2. Nguồn nào được xem là approved để em lưu raw evidence và provenance?
3. Em test trước trên FPT, VNM, VCB hay một subset VN100 nhỏ?
4. Date range đầu tiên cần adjusted readiness pass là khoảng nào?
5. Transaction cost/slippage vẫn xử lý riêng sau khi source factor được approve,
   đúng không anh?

Em sẽ chưa chạy Backtrader/VN100 khi adjusted readiness chưa pass.
