# Prompts

One versioned markdown file per node. The first line is `<!-- version: N -->`; bump it whenever
the text changes so traces and eval results record which prompt produced them. Variables use
`$name` (Python `string.Template`). CI fails if any `.py` file under `agent/` contains an inline
prompt longer than one line (see tests/unit/test_prompts_live_in_files.py).
