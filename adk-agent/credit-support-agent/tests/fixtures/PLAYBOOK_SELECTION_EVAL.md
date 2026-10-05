# Playbook selection evaluation

`playbook_discovery_cases.json` is a 16-case synthetic corpus for semantic selection among the four published playbooks. It covers direct requests, indirect payment need after fraud remediation, overlapping fraud and card needs, missing information, ambiguity, already satisfied work, information only, and unsupported outcomes. Each gold label declares the expected decision, reason, cited criterion, and draft business inputs. The labels are hand authored and independent of model output.

The runner is `scripts/playbook_selection_eval.py`. With no catalog argument, it reads the newest version of each local repository definition and derives the published digest. This is a **repository-file catalog baseline**; it is not a fresh database-backed `discover_playbooks` response. The public input schemas mirror `banking-service/services/proposal_capabilities.py`; an unknown operation fails closed. To evaluate an actual discovery response or a larger future catalog, pass `--catalog-snapshot path.json`. The JSON must have `retrieval_mode: FULL_PUBLISHED_CATALOG` and `playbooks` entries with published ID, revision, digest, discovery criteria, input schema, and `eligibility: NOT_CHECKED`. The snapshot may also carry a `source` label. No vector retrieval or ranker is exercised; the model sees the whole catalog.

Run the deterministic scorer with saved model outputs:

```sh
cd adk-agent/credit-support-agent
python3.13 scripts/playbook_selection_eval.py \
  --recorded tests/fixtures/playbook_selection_baseline_gemini_2_5_flash.jsonl \
  --recorded-model gemini-2.5-flash
python3.13 -m pytest -q tests/test_playbook_selection_eval.py
ruff check scripts/playbook_selection_eval.py tests/test_playbook_selection_eval.py
```

The historical baseline replay intentionally exits with code 1 because 12 of 16 cases fail its strict score. `--recorded-model` is a display label for legacy recordings, not verified run metadata. For future runs, the runner writes a `.lineage.json` sidecar **before** model calls. It contains the exact catalog, every rendered prompt, their SHA-256 digests, model/project/location and generation settings. Each response row binds those inputs with digests, and replay checks the sidecar and case inputs before scoring. A changed catalog or prompt fails replay. The [current v3 input artifact](playbook_selection_v3_unmeasured_inputs.json) freezes those exact prompts and catalog for future qualification; its status is `unmeasured_inputs`, and it contains no model responses.

To make a new, explicitly authorized live run with synthetic contexts only:

```sh
uv run --no-project --python 3.13 --with google-genai python scripts/playbook_selection_eval.py \
  --live-model gemini-2.5-flash --project evo-genai-workspace --location us-central1 \
  --write-recorded /tmp/playbook-selection-new.jsonl
```

The live mode uses Vertex application default credentials and one structured model response per case at temperature 0, with at most two retries for transient errors. `--max-model-requests` caps direct SDK calls (default 20), including retries. It exposes no banking tools and cannot prepare, commit, or mutate an account. Its `prepare` field is a draft only. The scorer separately rejects false eligibility or authorization claims, including string or numeric claims, malformed inputs, wrong revision/digest pins, unsupported preparation, and wrong decision/criterion. `decision_protocol_valid_count` measures only the production decision/reason/citation contract; gold-exact playbook and criterion counts remain separate. A passing score describes this isolated selection task, not production voice behavior, eligibility, authorization, or financial outcomes. Actual proposal preparation and commit remain governed by banking runtime checks.

## Measured baseline, 2026-10-04

`playbook_selection_baseline_gemini_2_5_flash.jsonl` contains 16 successful responses observed from Vertex `gemini-2.5-flash` in `evo-genai-workspace` / `us-central1`, using the local four-playbook catalog. The v1 prompt did not explicitly enumerate the closed reason-code vocabulary. The [baseline report](playbook_selection_baseline_report.json) records 16/16 correct decision classes, 14/16 exact playbook IDs, 8/16 exact reasons, 6/16 exact criterion indices, 0 false prepare drafts, and 4/16 strict full-case passes. All eight SELECT cases chose the intended playbook and drafted the expected published pin and business inputs. Two no-action cases omitted an optional playbook citation; the exact-ID metric counts those as misses. The model's invalid reason strings and missing criterion indices are wire-format failures that the first prompt made likely. The scorer's gold labels are deliberately stricter than the service's acceptance of a catalog-wide no-action decision; interpret exact-ID and full-case scores accordingly.

The v2 prompt explicitly listed the production `record_playbook_decision` reason codes and criterion rule. A separately labeled [four-case follow-up](playbook_selection_followup_report.json) covered dinner, ambiguous card help, already queued Wallet, and missing credit-limit total. It passed 4/4 with four recorded direct model calls; this is a focused diagnostic, not a second full baseline. The current v3 prompt only corrects sentence order from v2; it has not been measured live. The v1/v2 rendered prompts, exact catalog snapshot, and complete request settings were **not captured at execution**. Their saved responses are reproducible for offline *scoring* against today's catalog, but the original model requests cannot be verified or exactly reproduced from committed artifacts. Both reports label this `unverified_legacy_diagnostic`. The first run saved 16 successful responses but did not record direct request attempts, so its retry count cannot be verified retroactively. SDK transport attempts are not measured in either run. A new model run may differ.
