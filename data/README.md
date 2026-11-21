# Data

- `locomo10.json`: the [LoCoMo](https://github.com/snap-research/locomo) conversations (CC BY-NC 4.0).
- `questions.json`: the 1,540 LoCoMo questions in categories 1-4, generated with
  `python -m contextfact prepare --locomo data/locomo10.json --out data/questions.json`.

## Your own data

Convert conversations to the LoCoMo format:

```json
[{"sample_id": "my-conv",
  "conversation": {
    "speaker_a": "Alice", "speaker_b": "Bob",
    "session_1_date_time": "1:56 pm on 8 May, 2023",
    "session_1": [{"dia_id": "D1:1", "speaker": "Alice", "text": "..."}],
    "session_2_date_time": "...", "session_2": ["..."]}}]
```

Session dates use the `%I:%M %p on %d %B, %Y` format; turn IDs are `D<session>:<turn>`.
