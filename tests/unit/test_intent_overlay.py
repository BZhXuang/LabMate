import json
from pathlib import Path

from app.agents.nodes.intent_overlay import high_precision_intent


def test_overlay_matches_all_gold_intents() -> None:
    path = Path("eval/dataset/labmate/intent.jsonl")
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    mismatches = []
    covered = 0
    for row in rows:
        pred = high_precision_intent(row["query"])
        if pred is None:
            continue
        covered += 1
        label = pred.value
        if label != row["intent"]:
            mismatches.append((row["id"], row["query"], row["intent"], label))
    assert mismatches == []
    assert covered == 87
    assert len(rows) == 120
