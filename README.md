# Saathi API automation

API-level regression suite for the Saathi platform (`pre-saathi.ambak.com`
in the browser, `pre-apis.ambak.com` as the gateway every request in this
suite actually talks to). Complements `Automation Saathi` (UI/Playwright)
with direct backend coverage - GraphQL and REST - without a browser.

Imported from a Postman export (`postman/collection_raw.json`): 90
GraphQL operations across 5 services (finex, payout, insurance,
bank-integration, reporting-api) and 31 REST endpoints (partner, core,
dealer, account, process-rule, central-service). See `API_INVENTORY.md`
for the full per-operation coverage table.

**Read `AUTH_FINDINGS.md` before changing anything about auth or the
generated-test safety classification.** It documents why HMAC signing is
disabled, why token acquisition is cached, and a real incident (a
WhatsApp message, an email, and an SMS were sent to real
numbers/addresses during suite verification) that shaped the default-deny
safety model the generated tests now use.

## Setup

```bash
cp env.example.txt .env    # then edit if needed - defaults work against `pre`
make install
```

`.env` is gitignored. The default `.env` needs nothing changed to run
read-only tests against `pre` - it ships with a known test account
(`AUTH_MOBILE`/`AUTH_OTP`) that already works.

`make install` creates a project-local virtualenv at `.venv` and installs
`requirements.txt` into it (Debian's system Python is PEP 668-managed and
refuses `pip install --user`). All `make` targets use `.venv` automatically.
For any ad-hoc command outside `make`, run it as
`.venv/bin/python -m pytest ...` rather than bare `python3`/`pytest`.

## Running tests

```bash
make smoke      # auth + one read per GraphQL service - fast, CI-safe
make negative   # confirms the gateway actually rejects bad auth
make test       # full read-only regression (smoke + negative + every
                 # reviewed-safe generated query/endpoint + deeper
                 # hand-written examples) - mutations excluded
make mutations  # writes real data on `pre` - requires ALLOW_MUTATIONS=1
                 # in .env; skipped entirely otherwise. Runs "isolated"
                 # tier only - see below.
make mutations-external  # ALSO runs "external" tier: a real lender
                 # application + a live credit-bureau pull. Requires
                 # ALLOW_EXTERNAL_MUTATIONS=1 as well. Irreversible - do
                 # not run without a specific reason to.
make report     # generate + open the Allure report
```

Or with pytest directly: `python3 -m pytest tests/smoke -v`, etc. Markers:
`smoke`, `negative`, `mutation`, `schema`, `known_bug`.

### Mutation safety model

Every mutation must have an entry in `src/testdata/mutation_profiles.py`
to run at all - default-deny, so a newly re-imported mutation stays
skipped until someone explicitly classifies it. Each profile:

- Replaces the captured Postman PII (real-looking name/mobile/PAN) with
  synthetic data (`src/testdata/mutation_data.py`) before the call goes out.
- Declares a `tier`: `isolated` (Ambak-internal writes only) or
  `external` (reaches a real lender/credit bureau - gated behind the
  extra `ALLOW_EXTERNAL_MUTATIONS` flag).
- Declares `cleanup` if the API offers a way to reverse the write, or a
  `cleanup_reason` otherwise. **The captured spec has no delete/revert
  mutations at all**, so almost every profile has no cleanup - every
  mutation run leaves a permanent record on `pre`. `tests/mutations/conftest.py`
  logs every run to `mutations-uncleaned.json` so what's left behind is
  at least traceable.

`ALLOW_MUTATIONS=1` alone is also checked against the *resolved* host
(`MUTATION_SAFE_HOSTS` in `src/config/environments.py`), not just the
`ENV`/profile name - so pointing `BASE_URL` at prod can't silently make
mutations run there. Mutation calls also disable HTTP retries
(`retries=0`), so a commit-then-timeout never gets replayed as a
duplicate write.

## Email report

Every run (any `pytest`/`make` invocation, not just `make test`) generates a
per-run Excel workbook at `reports/saathi-api-report-<env>-<timestamp>.xlsx`
with three sheets: **Summary** (env, pass/fail/skip/known-bug counts, pass
rate, API call totals), **API Calls** (one row per HTTP exchange - service,
operation/endpoint name, method, path, HTTP status, GraphQL error if any,
latency, PASS/FAIL), and **Tests** (one row per pytest item).

If `REPORT_EMAIL_TO`/`REPORT_EMAIL_USER`/`REPORT_EMAIL_PASSWORD` are set in
`.env` (see `env.example.txt`), you're prompted at the end of the run:

```
📧 Run finished: 12/12 passed, 0 failed.
   Send report email to recipients? [y/N]
```

Answering `y` emails an HTML summary (KPI tiles, failures-first callout,
per-service call tally) with the Excel workbook attached. Leaving
`REPORT_EMAIL_TO` unset skips the whole email step (report generation and
prompt) silently. Pass `--email` to send without prompting (CI/agents) or
`--no-email` to always skip.

## Layout

```
src/
  config/       environment profiles (pre/prod) + settings loader
  core/         HTTP client, GraphQL POST helper, response wrapper
  auth/         OTP login (cached), static-token option, HMAC signer (unused by default)
  spec/         GENERATED operation/endpoint registries - do not hand-edit
  clients/      GenericClient (spec-driven) + a hand-written example (finex.py)
  models/       pydantic schemas for the operations with deeper tests
  validators/   fluent ResponseValidator
  testdata/     synthetic data + the default-deny mutation-profile registry
tools/
  import_postman.py      regenerates src/spec/* from postman/collection_raw.json
  generate_inventory.py  regenerates API_INVENTORY.md
  probe/                 throwaway auth-verification spike (see AUTH_FINDINGS.md)
tests/
  smoke/        auth + one read per service
  negative/     unauthenticated / bad-token rejection
  generated/    full sweep over every SAFE-classified query/endpoint
  mutations/    every write, gated behind ALLOW_MUTATIONS
  finex/        deeper, schema-validated hand-written example - copy this
                pattern when a generated smoke test needs to grow up
```

## Re-importing after a fresh Postman export

```bash
make import                       # regenerate src/spec/operations.py, endpoints.py
python3 tools/generate_inventory.py
make test
```

Any newly-discovered operation/endpoint whose name suggests it performs a
real action (send/create/update/save/sms/email/whatsapp/...) will fail
test collection with a clear message until you read its captured body and
classify it as safe or excluded in `tests/generated/test_operations.py` /
`test_endpoints.py`. This is deliberate - see the incident writeup in
`AUTH_FINDINGS.md`. Do not weaken this to get tests running faster.

## Known backend issues tracked as `known_bug`

Two real issues on `pre`, found by the first full run of this suite -
tracked as `xfail(strict=True)` so they don't block the suite but do flip
to a hard failure if they change. Details and reasoning in
`tests/generated/test_operations.py`'s `KNOWN_BUGS` dict and in
`API_INVENTORY.md`:

- `finex.get_banker_records_by_id` - stale capture (`city` arg no longer
  accepted; schema now requires `bank_id`).
- `finex.get_feature_list` - resolver throws "Invalid time value" on at
  least one row's date field, alongside still returning data.
- `insurance.GetMobileOffers` - **resolved 2026-09-02** (the missing
  `ambak_insurance.ins_pb_city_alias` table now exists); its `known_bug`
  marker has been retired and it is covered by the normal sweep.
# Saathi-API
# Saathi-API
