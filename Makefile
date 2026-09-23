.PHONY: install check-venv import smoke negative test mutations mutations-external report report-file clean

# Real binary, no shebang - safe even though this path has spaces/parens
# (unlike .venv/bin/pip or .venv/bin/pytest, whose #! line would break).
PY := .venv/bin/python

install:
	python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

check-venv:
	@test -x $(PY) || { echo "No .venv found - run 'make install' first."; exit 1; }

# Regenerate src/spec/operations.py and endpoints.py from postman/collection_raw.json.
# After this, review any new action-shaped operation/endpoint flagged by
# tests/generated/*.py's import-time assertions before running tests.
import: check-venv
	$(PY) tools/import_postman.py

smoke: check-venv
	$(PY) -m pytest tests/smoke -v

negative: check-venv
	$(PY) -m pytest tests/negative -v

# Full read-only regression: smoke + negative + every reviewed-safe
# generated query/endpoint + the deeper hand-written examples.
# Mutations are NOT included - see `make mutations`.
#
# Every run also writes a per-run Excel report to reports/, and (if
# REPORT_EMAIL_TO is set in .env) prompts at the end to email a summary with
# that Excel attached. Pass --email/--no-email to skip the prompt, e.g.
# `.venv/bin/python -m pytest tests -v -m "not mutation" --alluredir=allure-results --email`.
test: check-venv
	$(PY) -m pytest tests -v -m "not mutation" --alluredir=allure-results

# Gated: writes real data on `pre`. Requires ALLOW_MUTATIONS=1 in .env.
# Runs only "isolated" tier mutations (src/testdata/mutation_profiles.py) -
# tier="external" stays skipped even here. See mutations-uncleaned.json
# after a run for what was written and couldn't be cleaned up.
mutations: check-venv
	$(PY) -m pytest tests/mutations -v --alluredir=allure-results

# Also runs tier="external" mutations: real, irreversible writes to a
# real lender and a live credit-bureau pull. Requires BOTH
# ALLOW_MUTATIONS=1 and ALLOW_EXTERNAL_MUTATIONS=1 in .env. Do not run
# this without a specific reason to.
mutations-external: check-venv
	ALLOW_EXTERNAL_MUTATIONS=1 $(PY) -m pytest tests/mutations -v --alluredir=allure-results

# Fixed port so the URL is known ahead of time; the browser launch is
# backgrounded with a short delay to give the server time to bind, then
# `allure open` runs in the foreground as the (blocking) server - Ctrl+C
# to stop it.
report:
	allure generate ./allure-results --clean -o ./allure-report
	( sleep 2 && xdg-open http://localhost:8080 >/dev/null 2>&1 & )
	allure open --port 8080 ./allure-report

# One self-contained index.html with everything inlined - no local server
# needed, just double-click/open it in a browser or send the file to
# someone else.
report-file:
	allure generate ./allure-results --clean -o ./allure-report-single --single-file

clean:
	rm -rf allure-results allure-report allure-report-single .pytest_cache **/__pycache__
