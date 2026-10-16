# B14 Result navigation

Branch: `feat/mvp-0.1-b14`, based on `feat/mvp-0.1-b13` commit `4171445`.

Completed analyses load the full v1 result set with `GET /api/analyses/{id}/findings?page=1&per_page=20`. The findings contract allows at most 20 items, so category and severity filters apply to the complete validated set. The interface still shows five items per page. Changing either filter returns to the first page, updates the count, and distinguishes no filter matches from a genuinely empty analysis. The filters cause no extra API calls.

Each evidence entry links to the public GitHub blob for the analysis repository and recorded commit SHA, with the original inclusive line range in the fragment. Path segments are encoded separately. The link builder requires a canonical repository, 40 character SHA, safe relative path, and valid line range. Angular continues rendering finding text as escaped text. Links open only when chosen by the user; the application does not fetch more source or add an API field or endpoint.

Validation from `services/frontend`:

| Check | Result |
| --- | --- |
| `npm test` | Passed: public contract and source URL checks |
| `npm run build` | Passed: production Angular bundle |
| `CHROMIUM_EXECUTABLE=/usr/bin/chromium node --test tests/browser.test.mjs` | Passed: 10 browser scenarios, including cross-page filtering, empty matches, pinned links, and existing lifecycle behavior |
| `git diff --check` | Passed |

Browser tests use intercepted public responses and a local server. They do not open external GitHub pages or make provider calls. B12's PostgreSQL/Compose checks and B13's native integrated acceptance passed. Longer-term retention measurements and real-time interval observation remain documented operational limits, not unrun B12/B13 tests.
