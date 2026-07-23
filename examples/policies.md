# Policies

List and inspect bundled policies:

```bash
cleanroom policies
cleanroom policies show strict
cleanroom policies validate config/strict-policy.yaml
```

Expected list:

```text
ai-safe v1 — Removes personal, security, and customer-identifying information before AI upload.
default v1 — Balanced sanitization for routine local documents.
strict v1 — Conservative policy that quarantines all uncertain contextual identifiers.
```

Copy a policy before customization. Keep its schema version and provide an explicit
action for every category. See [policy documentation](../docs/policies.md).
