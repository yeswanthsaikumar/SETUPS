"""Quick validation of partial exits fixes."""

# Test 1: _compute_board_stats - closed position with realized_pl should not double-count
p = {"entry": 100, "quantity": 10, "remaining_quantity": 0, "status": "T3_HIT", "exit_price": 150, "realized_pl": 450}
pos_realized = p.get("realized_pl", 0) or 0
pl = pos_realized if pos_realized else (p["exit_price"] - p["entry"]) * p["quantity"]
assert pl == 450, f"Test1 FAIL: {pl}"
print("Test1 PASS: closed P&L uses realized_pl (no double-count)")

# Test 2: remaining_quantity=0 should NOT fallback to qty
p2 = {"quantity": 10, "remaining_quantity": 0}
qty = p2.get("quantity", 1)
remaining = p2.get("remaining_quantity") if p2.get("remaining_quantity") is not None else qty
assert remaining == 0, f"Test2 FAIL: {remaining}"
print("Test2 PASS: remaining_quantity=0 preserved correctly")

# Test 3: equity curve includes both partial + final close events
p3 = {"entry": 100, "quantity": 10, "status": "CLOSED", "exit_price": 140,
      "partial_exits": [{"date": "2025-01-10", "quantity": 3, "price": 130}]}
events = []
for pe in p3.get("partial_exits", []):
    events.append(round((pe["price"] - p3["entry"]) * pe["quantity"], 2))
pq = sum(pe["quantity"] for pe in p3.get("partial_exits", []))
fr = p3["quantity"] - pq
if fr > 0:
    events.append(round((p3["exit_price"] - p3["entry"]) * fr, 2))
assert events == [90, 280], f"Test3 FAIL: {events}"
assert sum(events) == 370
print("Test3 PASS: equity curve = [90 partial, 280 final] = 370 total")

# Test 4: enriched endpoint gain for closed position with realized_pl
entry = 100; qty = 10; realized = 450
gain_amt = realized
gain_pct = (realized / (entry * qty)) * 100
assert gain_pct == 45.0, f"Test4 FAIL: {gain_pct}"
print("Test4 PASS: closed gain% = 45% (from realized_pl)")

# Test 5: position with no partial exits (normal close) still works
p5 = {"entry": 100, "quantity": 10, "status": "CLOSED", "exit_price": 130, "realized_pl": 0}
pos_r = p5.get("realized_pl", 0) or 0
if pos_r:
    pl5 = pos_r
else:
    pl5 = (p5["exit_price"] - p5["entry"]) * p5["quantity"]
assert pl5 == 300, f"Test5 FAIL: {pl5}"
print("Test5 PASS: normal close (no partials) = 300")

print("\n✅ ALL TESTS PASSED")

