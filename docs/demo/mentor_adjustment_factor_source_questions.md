---
title: mentor_adjusted_price_policy_confirmation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Adjusted Price Policy Confirmation

Anh ơi, em confirm lại phần anh đã chốt để em đưa vào pipeline:

- VN100 dùng list hiện tại.
- Giá dùng cho backtest bắt buộc là adjusted price.
- Em sẽ điều chỉnh toàn bộ OHLC theo adjusted price, không chỉ close.
- Factor điều chỉnh sẽ tính theo dividend/split factor.
- Transaction cost em sẽ tự research.
- Slippage em sẽ đặt hợp lý và không vượt biên độ sàn: HSX/HOSE +/-7%, UPCoM +/-15%.

Tiếp theo em sẽ update pipeline theo hướng này: verify adjusted price/factor
evidence trên FPT, VNM, VCB trước, sau đó mới populate adjusted OHLC và chạy
readiness gate. Em vẫn chưa chạy Backtrader/VN100 khi adjusted readiness chưa
pass.
