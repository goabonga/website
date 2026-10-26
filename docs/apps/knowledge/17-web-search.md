# Search page

The search page is the browser front end of the [semantic search](05-search.md)
service. It is served at `/search` by the internal sub-application (tag `Web`)
and, like the other workspace pages, requires a signed-in user with an active
workspace (see [Web authentication](14-web-authentication.md)); visitors are
redirected to the login page.

## Routes

| Route | Behavior |
| --- | --- |
| `GET /search` | Renders the form and, when `q` is present, the results. |
| `POST /search` | Receives the form and redirects (`302`) to the equivalent `GET /search?...` URL so that searches can be bookmarked and shared. Parameters that keep their default value are omitted. |

### Query parameters of `GET /search`

| Parameter | Default | Meaning |
| --- | --- | --- |
| `q` | empty | Search text. Without it no search runs. |
| `collection_id`, `collection_ids` | none | One collection, or a comma-separated list of ids or slugs, to search in. |
| `all_collections` | `false` | Search every collection of the workspace and ignore the two previous parameters. |
| `top_k` | `20` | Number of results; values outside 1 to 100 fall back to 20. |
| `threshold` | `0.5` | Minimum similarity; values outside 0 to 1 fall back to 0.5. |
| `distance_type` | `cosine` | `cosine`, `l2` or `inner_product`; unknown values fall back to `cosine`. |
| `include_content` | `true` | Show the content of the matches. |
| `filters_json` | empty | Metadata filters as a JSON object. Anything else shows "Filters must be a JSON object." or "Filters must be valid JSON." and the search still runs without filters. |

The page lists the workspace's collections (for the filter), then the matches
with their score as a percentage, their collection and a link to the document
(`/documents/<id>`). The content is truncated to 500 characters. An empty
result shows "No results found". When the search service raises, the page
shows "Search failed: ..." instead of an error page.

The search runs through `SearchService` with the workspace id as tenant, so it
covers the collections linked to the workspace as described in
[Collection and document pages](16-web-collections-documents.md).

The sidebar gains the *Search* link (active on this page) and the dashboard a *Search* quick
action.

## Tests

pytest:

- `test_web_search.py`: the page and the submit route with mocked service:
  parameters, validation fallbacks, filters, errors and redirects.
- `unit/test_web_search_routes.py`: the query building of the submit route.

behave (`features/web_search.feature`): real routes and template over the
in-memory store, with the in-memory cosine search replacing pgvector.

- The search page requires a signed-in user
- The empty search page offers the collections of the workspace
- A query lists the best matches first
- A search can be restricted to one collection
- Weak matches are filtered by the threshold
- Invalid JSON filters are reported
- A failing search is reported on the page
- Submitting the form redirects to a shareable URL

browser (`features/browser/web_search.feature`, tag `@browser`): the page in a real
Chromium, signed in through the fake OpenID provider. SQLite has none of the pgvector
operators, so the page is served by a ranking done in Python (cosine similarity over
the documents of the selected collections) with the contract of `SearchService`; the
query and the documents are embedded by the bag-of-words model of the behave fakes.

- The search page is reached from the sidebar
- A query finds the documents that talk about it
- A result leads to its document
- The search can be limited to some collections
- A query that matches nothing says so
- The threshold decides what is similar enough
- The filters must be a JSON object
- The search page requires a signed-in user
- The dashboard leads to the search page
- The search page only leads to pages that exist
