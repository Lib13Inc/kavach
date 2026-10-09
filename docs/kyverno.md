# What Kavach borrows from Kyverno

Kyverno is a Kubernetes policy engine. Its admission, mutate/generate and image-verification features are
shaped around cluster resources and do not apply to an agent's outbound traffic. Four policy-management
ideas do, and are implemented:

| Kyverno idea | In Kavach |
| --- | --- |
| `validationActions: [Audit]` vs `[Deny]` | `egress.mode: audit` logs the violation (`egress_audit`) and lets it through; `enforce` (default) blocks. Compiles to OpenShell's `enforcement: audit\|enforce`. |
| `PolicyException` | `exceptions:` list: hosts, owner, reason, expiry. Egress only; a stand-in key sent to the wrong host is never waivable. |
| `PolicyReport` | `kavach policy report TRACE...` emits a `wgpolicyk8s.io/v1alpha2` PolicyReport (pass/fail/skip per decision, OpenShell denials included). |
| Policy tests / CI | `kavach policy lint` (Python, tested) and `policy/lint/kavach-pack.kyverno.yaml` (the same rules as Kyverno CEL `ValidatingPolicy`s in JSON mode). |

The Kyverno CEL file has **not been run** through the Kyverno CLI (not installed here); the Python lint is the tested path.

Not adopted: CEL as the policy language (the pack stays plain YAML for now), `mutate`/`generate`/`verifyImages`,
background scans. Worth revisiting: Kyverno JSON mode as the evaluation engine for per-request rules, once its engine SDK ships.
On Kubernetes, Kyverno is complementary: it can require that agent pods run in a Kavach/OpenShell sandbox.
