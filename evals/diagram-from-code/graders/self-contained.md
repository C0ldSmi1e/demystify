---
type: regex
match: not_contains
target: { source: file, path: rate-limiter.svg }
pattern: '<script|(?:href|src)\s*=\s*["'']https?://'
---
