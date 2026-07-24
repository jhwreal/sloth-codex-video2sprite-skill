# Provider contracts

## GPT Image 2

Use the OpenAI Image API for one-shot canonical master generation.

- Default model: `gpt-image-2`.
- Credential: `OPENAI_API_KEY`.
- Default endpoint: `POST /v1/images/generations`.
- The API returns Base64 image data. Decode it inside the worker and discard the encoded string before emitting any status.
- GPT Image 2 does not support transparent backgrounds. Generate on a flat
  extraction matte; default to a dark non-green hue absent from the character.
- Do not enable streaming or partial images; they multiply media payloads without helping this workflow.
- Retry only when the provider clearly reports a retry-safe failure. Do not automatically
  repeat an ambiguous generation request, because that can create duplicate billed work.
  Never retry user or moderation errors unchanged.

The worker may store request ID, model, usage numbers, output path, size, and hash. It must not store or print `b64_json`.

The adjacent provenance sidecar includes a generation fingerprint over the
prompt, provider, model, size, quality, and matte. A verified identical output
is reused without another API request. Any changed input or mismatched output
hash requires an intentional `--overwrite`.

## Volcengine Ark video generation

Use the asynchronous contents-generation API:

```text
POST {base_url}/contents/generations/tasks
GET  {base_url}/contents/generations/tasks/{task_id}
```

Default base URL:

```text
https://ark.cn-beijing.volces.com/api/v3
```

Credential: `ARK_API_KEY`.

Send:

- one text prompt;
- one canonical local image path, provider-readable URL, or asset URI;
- selected model ID;
- resolution, ratio, duration, seed when supported;
- native-audio request when the model supports it.

Persist the returned task ID before polling. Download a completed video immediately because provider URLs may expire. Redact URL query strings in summaries.

For a local image path, validate the file against Ark's documented image
constraints, require the run-level canonical master hash to match, encode it
only inside the worker request, and release the inline value immediately after
the HTTP call. Persist only the local path, hash, byte count, and dimensions.
Reject caller-supplied data URLs so encoded media cannot cross the CLI or run
schema boundary.

Known aliases must reject unsupported request parameters before billing. In
particular, Seedance 2.0 accepts integer durations from 4 through 15 seconds
and currently does not support `seed` or `camera_fixed`.

Batch orchestration may poll several persisted task IDs concurrently. It must
not infer permission to submit missing candidates, retry failed generations,
or exceed the per-action candidate budget.

The first remote action is also a run-level paid pilot. Do not expand to other
actions until a processed remote candidate has a valid user approval, unless
the user explicitly authorizes `--allow-unapproved-batch`.

Do not automatically resubmit an ambiguous failed `POST`. First inspect the bounded task
state; use a new candidate ID only when a new billed generation is intentional.

The exact model catalog and account entitlement can change. Treat `assets/model-presets.json` as tested aliases, not the source of truth. Allow a full model ID override.

## Adding another video provider

Implement the same narrow interface:

```text
submit(action, candidate, reference) -> task_id
poll(task_id) -> bounded status and optional download URL
download(url, destination) -> hash and byte count
capabilities(model) -> native_audio, image_to_video
```

Keep provider request and response peculiarities inside the adapter. Do not leak them into the run schema or CLI output.

## Official references

- OpenAI image generation:
  `https://developers.openai.com/api/docs/guides/image-generation`
- Volcengine create-video task API:
  `https://www.volcengine.com/docs/82379/1520757`
- Volcengine query-video task API:
  `https://www.volcengine.com/docs/82379/1521309`

Re-check these sources before changing request fields or refreshing bundled model
aliases. Provider documentation and account availability override this Skill.
