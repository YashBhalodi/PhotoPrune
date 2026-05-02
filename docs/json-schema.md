# JSON output schema (`photoprune --mode json`)

The JSON mode prints a single object to stdout. Status messages (model loading, scan progress) go to stderr and never to stdout, so the output is safe to pipe directly into `jq`, an LLM context window, etc.

The schema carries a `version` field — bumped only on incompatible changes. Today's version is **`"1"`**.

## Shape

```jsonc
{
  "version": "1",
  "album_path": "/abs/path/to/album",
  "threshold": 0.85,
  "scanned": 135,
  "groups": [
    {
      "group_id": "1",
      "detection_type": "near",                  // "exact" | "near" | "mixed"
      "size": 5,
      "max_similarity": 0.9397,                  // 0.0..1.0, cosine
      "suggested_keep": "/abs/path/to/best.jpg",
      "members": [
        {
          "path": "/abs/path/to/best.jpg",
          "size_bytes": 4738543,
          "width": 4000,
          "height": 2252,
          "sharpness": 4051.14,                  // Laplacian variance, or null
          "quality_rank": 0.9072,                // 0.0..1.0, or null
          "is_suggested_keep": true
        },
        {
          "path": "/abs/path/to/copy.jpg",
          "size_bytes": 5371526,
          "width": 4000,
          "height": 2252,
          "sharpness": 3626.29,
          "quality_rank": 0.8691,
          "is_suggested_keep": false
        }
      ]
    }
  ]
}
```

## Field reference

### Top-level

| Field | Type | Notes |
|---|---|---|
| `version` | string | Schema version. `"1"` today. Bumped on breaking changes only. |
| `album_path` | string | Absolute path to the directory that was scanned. |
| `threshold` | number | The cosine-similarity cutoff used for near-duplicate detection. |
| `scanned` | integer | Total number of supported image files found and loaded. |
| `groups` | array | Duplicate groups, each containing ≥ 2 photos. |

### Group object

| Field | Type | Notes |
|---|---|---|
| `group_id` | string | Stable within a single run; not a global identifier. |
| `detection_type` | enum | `"exact"` (matched only via pHash), `"near"` (matched only via embedding similarity), `"mixed"` (both signals contributed). |
| `size` | integer | Number of members. |
| `max_similarity` | number | Highest pairwise cosine similarity in the group. `1.0` for `exact` groups by definition. |
| `suggested_keep` | string | Absolute path of the auto-suggested keeper. Member with the highest `quality_rank`. |
| `members` | array | Sorted with `is_suggested_keep: true` first, then by `quality_rank` descending. |

### Member object

| Field | Type | Notes |
|---|---|---|
| `path` | string | Absolute path. |
| `size_bytes` | integer | File size on disk. |
| `width` | integer | Pixels (after EXIF orientation is honored). |
| `height` | integer | Pixels. |
| `sharpness` | number \| null | Variance of the Laplacian on the grayscale image. Higher = sharper. `null` if scoring failed (rare — usually means the file couldn't be decoded). |
| `quality_rank` | number \| null | `0.5·sharpness + 0.3·resolution + 0.2·filesize`, normalized within the group. `1.0` for the keeper. `null` if any input was missing. |
| `is_suggested_keep` | boolean | Whether this member is the group's auto-suggested keeper. Exactly one member per group has this set to `true`. |

## Empty result

When no duplicates are found, `groups` is `[]` but the structure is still valid:

```json
{
  "version": "1",
  "album_path": "/abs/path",
  "threshold": 0.94,
  "scanned": 0,
  "groups": []
}
```

## Determinism

For a given album state and threshold, the output is deterministic — same input, same JSON. Scan order is stable (alphabetical), pHash and embedding computations are deterministic, and Faiss with `IndexFlatIP` is exhaustive. Group IDs, however, are local to the run; don't rely on them across runs to identify "the same group".

## Versioning policy

- Adding new fields → no version bump (additive changes are non-breaking; downstream parsers should ignore unknown fields).
- Removing or renaming fields, changing semantics, or changing types → bump `version`.

If you're consuming this output from a script or LLM, key on `version == "1"` and skip processing on a higher version unless your code knows about it.
