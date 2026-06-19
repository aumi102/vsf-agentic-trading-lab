---
title: mentor_adjustment_factor_source_questions
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Adjustment Factor Source Questions

Anh ơi, em đã làm xong phần khung cho adjusted OHLC/factor verification trong repo:

- DB đã có cột adjusted OHLC và provenance riêng cho factor.
- Có readiness gate để block backtest nếu adjusted OHLC/factor chưa đủ.
- Có local factor application cho symbol explicit.
- Có verification layer cho payload adjusted close hoặc corporate action.
- Hiện tại chưa fetch live và chưa chạy Backtrader/VN100.

Phần còn thiếu là nguồn factor thật được approve. Anh confirm giúp em:

1. Mình dùng adjusted close từ vendor có được không, hay bắt buộc phải derive
   factor từ dividend/split/corporate action?
2. Nguồn nào được xem là approved để em lưu raw evidence + provenance?
3. Em test trước trên FPT, VNM, VCB hay một subset VN100 nhỏ?
4. Date range đầu tiên cần adjusted readiness pass là khoảng nào?
5. Transaction cost/slippage vẫn xử lý riêng sau khi source factor được approve,
   đúng không anh?

Sau khi anh confirm source, em sẽ verify payload nhỏ trước, sau đó mới integrate
vào ETL. Em sẽ chưa chạy Backtrader/VN100 khi adjusted readiness chưa pass.
