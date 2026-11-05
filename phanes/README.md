# Phanes

Ollama Modelfiles for the four Phanes local models. Each file sets a base model, the chat template, a system prompt and sampling parameters.

| Model | Purpose (from its system prompt) | Base model | num_ctx | num_predict | temperature | top_p | repeat_penalty |
|---|---|---|---|---|---|---|---|
| phanes-agent | Fully local autonomous agent: plan, act, verify, report; tool discipline | qwen2.5:7b | 16384 | 4096 | 0.15 | 0.9 | 1.08 |
| phanes-code | Local coding specialist: read before editing, verify with tests | qwen2.5-coder:7b | 16384 | 4096 | 0.1 | 0.9 | 1.05 |
| phanes-fast | Quick local helper: brief answers, tools only when needed | qwen2.5:7b | 8192 | 2048 | 0.2 | 0.9 | — |
| phanes-reason | Careful planner and analyst: structured plans, trade-offs, verification | qwen2.5:14b | 32768 | 8192 | 0.2 | 0.9 | — |

## Build

Pull the base models, then create the model from its Modelfile:

```
ollama pull qwen2.5:7b
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:14b
ollama create phanes-agent -f phanes-agent.Modelfile
ollama create phanes-code -f phanes-code.Modelfile
ollama create phanes-fast -f phanes-fast.Modelfile
ollama create phanes-reason -f phanes-reason.Modelfile
```

## License

The base models are Apache-2.0. The full licence text is not copied here; see the upstream model pages on ollama.com/library.
