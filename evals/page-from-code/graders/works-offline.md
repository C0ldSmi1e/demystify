---
type: regex
weight: 2
match: not_contains
target: { source: file, path: rate-limiter.html }
flags: i
pattern: '<(?:script|link|img|iframe)[^>]+(?:src|href)\s*=\s*["'']?(?:https?:)?//|@import\s+(?:url\()?["'']?https?://'
---
