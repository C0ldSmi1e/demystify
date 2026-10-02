---
type: regex
weight: 2
target: { source: file, path: rate-limiter.svg }
pattern: '^(?=[\s\S]*<svg)(?=[\s\S]*429)(?=[\s\S]*Retry-After)(?=[\s\S]*\b20\b)'
---
