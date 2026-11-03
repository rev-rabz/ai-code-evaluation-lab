# Stage 8 — AI-Powered Code Reviews

## Goal

Add optional, evidence-linked AI feedback to an existing evaluation without changing trusted test execution or server-calculated scores.

## Scope

1. Authenticated users can explicitly request an AI review for one of their own saved evaluations.
2. Use a provider selected by `AI_REVIEW_PROVIDER`. The default is local Ollama; OpenAI is an optional alternative. Ordinary evaluation never calls an AI provider.
3. Require a structured response containing a summary, strengths, findings, and next steps.
4. Every finding must include a 1-based inclusive line range and an exact source excerpt. The API verifies the excerpt against the stored source before saving it.
5. Persist one review per evaluation. Repeated POST requests return the stored review and do not make another provider request.
6. Users can retrieve only reviews belonging to their own evaluations.

## API

- `POST /api/v1/evaluations/{evaluation_id}/review` — generate once or return the existing review.
- `GET /api/v1/evaluations/{evaluation_id}/review` — retrieve the stored review.

## Provider configuration

### Default: local Ollama

Configure the API service with:

- `AI_REVIEW_PROVIDER=ollama`
- `OLLAMA_BASE_URL=http://host.docker.internal:11434` when the API runs in Docker Desktop and Ollama runs natively on Windows/macOS
- `OLLAMA_REVIEW_MODEL=qwen3.5:4b` by default

Install Ollama from [ollama.com/download](https://ollama.com/download) and download the model with `ollama pull qwen3.5:4b`. The API uses Ollama's local `/api/chat` endpoint and passes the review JSON Schema through its `format` parameter. No API key or per-request provider charge is required. Model downloads require internet access and disk space; inference uses the developer machine's CPU/GPU and memory.

Ollama's API does not provide built-in authentication. On Windows, it may need to listen on `0.0.0.0:11434` for Docker containers to reach it. Do not expose port 11434 to the public internet or untrusted networks; restrict host firewall access to trusted local development traffic.

### Optional: OpenAI

Set `AI_REVIEW_PROVIDER=openai`, `OPENAI_API_KEY`, and optionally `OPENAI_REVIEW_MODEL` (default: `gpt-5.6-terra`). OpenAI API usage requires separately provisioned API billing; a ChatGPT subscription does not itself provide API credits. Keep the key in the local environment file or deployment secret store; never commit it.

The OpenAI review endpoint sends the stored source code to OpenAI only when a user explicitly calls the POST endpoint. The request uses the Responses API with Structured Outputs and `store: false`.

## Safety and trust boundaries

- The source code is treated as untrusted prompt data. The model receives no tools and is instructed not to follow instructions embedded in code.
- Model output is advisory only; it never changes the evaluation score, test results, or execution decision.
- Every finding must cite an exact excerpt from the submitted source. Invalid line ranges or mismatched excerpts are rejected.
- Expected test values, actual test outputs, stdout, and stderr are not included in the AI context. Only test names and pass/fail outcomes are supplied.
- Source size is limited to 25,000 characters for an AI review.
- Provider errors do not create a review record. Reviews are stored privately against the evaluation and remain subject to the user's evaluation ownership.
- Ollama model output is still untrusted and can be inaccurate; exact evidence validation prevents invented source excerpts, but does not prove the semantic correctness of every review finding.
- Rate limiting, provider budget controls, deletion/retention tools, and a web reviewer dashboard remain future work.
