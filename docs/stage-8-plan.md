# Stage 8 — AI-Powered Code Reviews

## Goal

Add optional, evidence-linked AI feedback to an existing evaluation without changing trusted test execution or server-calculated scores.

## Scope

1. Authenticated users can explicitly request an AI review for one of their own saved evaluations.
2. Send the stored source code plus limited evaluation/task context to the configured OpenAI Responses API. The review is opt-in; ordinary evaluation does not call an AI provider.
3. Require a structured response containing a summary, strengths, findings, and next steps.
4. Every finding must include a 1-based inclusive line range and an exact source excerpt. The API verifies the excerpt against the stored source before saving it.
5. Persist one review per evaluation. Repeated POST requests return the stored review and do not make another provider call.
6. Users can retrieve only reviews belonging to their own evaluations.

## API

- `POST /api/v1/evaluations/{evaluation_id}/review` — generate once or return the existing review.
- `GET /api/v1/evaluations/{evaluation_id}/review` — retrieve the stored review.

## Provider configuration

Set `OPENAI_API_KEY` and optionally `OPENAI_REVIEW_MODEL` on the API service. The default model is `gpt-5.6-terra`. Keep the key in the local environment file or deployment secret store; never commit it. AI review requires a separately provisioned API key and API billing. A ChatGPT subscription does not itself provide API credits.

The review endpoint sends the stored source code to OpenAI only when a user explicitly calls the POST endpoint. The request uses the Responses API with Structured Outputs and `store: false`. The application does not execute model-generated code or suggestions.

## Safety and trust boundaries

- The source code is treated as untrusted prompt data. The model receives no tools and is instructed not to follow instructions embedded in code.
- Model output is advisory only; it never changes the evaluation score, test results, or execution decision.
- Every finding must cite an exact excerpt from the submitted source. Invalid line ranges or mismatched excerpts are rejected.
- Expected test values, actual test outputs, stdout, and stderr are not included in the AI context. Only test names and pass/fail outcomes are supplied.
- Source size is limited to 25,000 characters for an AI review.
- Provider errors do not create a review record. Reviews are stored privately against the evaluation and remain subject to the user's evaluation ownership.
- Rate limiting, provider budget controls, deletion/retention tools, and a web reviewer dashboard remain future work.
