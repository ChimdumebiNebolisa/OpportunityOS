# Profile import

OpportunityOS never reads ChatGPT memory or history through OAuth. Import a user-provided snapshot or
submit sourced facts explicitly.

The structured JSON format is:

```json
{
  "export_version": "1.0",
  "generated_at": "2026-08-21T12:00:00Z",
  "facts": [
    {
      "field_path": "career.objective",
      "value": "Synthetic AI research objective",
      "confidence": 0.7,
      "supporting_text": "User-provided snapshot"
    }
  ]
}
```

Import with `opportunityos profile import snapshot.json`, or use the profile-sync Hermes skill for
documents and user statements. Imported facts are candidates with provenance, not silent truth.
Conflicts appear in `opportunityos review list`; resolve them with a selected candidate or an entered
JSON value and a note.

`opportunityos profile sync-github USERNAME` records observable repository metadata, up to ten
releases for each of the first ten repositories, and up to 100 merged pull-request search results.
A language, release, or contribution is not converted into an expertise claim. Use an authenticated
GitHub token only in private environment configuration if higher rate limits or private-repository
metadata are needed; private source contents are never indexed.
