# Policies

Policies are versioned YAML. `default` balances routine replacement and quarantine
of indirect identifiers. `strict` lowers confidence thresholds and reviews most
unspecified categories. `ai-safe` targets preparation before an AI upload.

Use:

```bash
cleanroom policies
cleanroom policies show ai-safe
cleanroom policies validate ./config/custom-policy.yaml
```

A policy defines `schema_version`, name, version, description, default action,
global and category confidence, category actions, placeholders, review behavior,
prompt hints, and verification strictness. Actions are `replace`, `redact`,
`ignore`, and `review`. Review findings are hash-only in reports and quarantine
by default; `warn_only` or `auto_replace` must be an explicit policy decision.
