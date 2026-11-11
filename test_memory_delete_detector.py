from services.memory_delete_service import (
    is_explicit_memory_delete_request,
)

tests = [
    ("Forget my Hinglish preference", True),
    ("Forget everything", True),
    ("Please forget my cricket habit", True),
    ("stop remembering my cricket habit", True),
    ("Don't remember my phone number", True),
    ("Delete this memory from your stored memories.", True),
    ("Remove my preference from memory.", True),
    ("Don't forget to cite page numbers", False),
    ("I forget the formula, explain it", False),
    ("I forgot my password", False),
    ("Forget it, move on", False),
    ("Hey, forget my cricket habit", False),  # intentionally conservative
    ("How do I remove a column from the table?", False),
    ("Explain embeddings.", False),
    ("", False),
]

failed = 0
for message, expected in tests:
    actual = is_explicit_memory_delete_request(message)
    ok = actual == expected
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'} | {actual} | expected={expected} | {message}")

print(f"\n{failed} failure(s)")
