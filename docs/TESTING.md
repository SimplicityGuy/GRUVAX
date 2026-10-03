# Behavioral test requirements

`just check` and CI run `scripts/check_test_patterns.py`, the full test suite,
and the runtime skip policy in `tests/pattern_policy.py`.

- An implemented route's missing authentication, unexpected status, missing fixture
  records, or absent endpoint must fail. Runtime `pytest.skip` is a failure.
  Explicit platform markers and pytest-benchmark's normal-suite skips
  remain deliberate exceptions. Use a known-bin successful request before asserting
  an unknown-bin 404; a deleted route must not satisfy the negative test.
- DATA-01, PRIV-02, and SEG-08 require executed behavior. Source greps and signature
  checks can be supplementary tripwires. The DATA-01 reference is
  `test_nondefault_profile_scoping.py`: write as a non-default profile, then check
  that profile changed and both the other profile and default profile did not.
  SEG-08 uses fresh synthetic boundaries and a seeded PIN per client.
- Nullable property results must have a non-null census outside the guarded
  invariant. Assert that a covered outcome is non-null, or assert the populated
  nonempty result collection or positive counter before checking its invariants. Empty loops do not
  verify bounds, membership, ordering, or cosmetic stability.
- Privacy tests capture the actual console JSON emission channel through
  `configure_logging` and `capfd`, and assert successful search status. Ring buffers
  are secondary checks because they discard structured fields. Only the test
  HTTP client's URI logger is suppressed; every server JSON field is inspected.
- A no-exception requirement can use `behavior_no_raise` explicitly. Ordinary
  tests need an assertion, a `pytest.raises` context, a mock's assertion, or a
  called helper containing assertions. The static check is a structural tripwire;
  helper recognition does not prove the helper reaches its assertions. The behavioral
  tests and injected failure proofs establish the actual contract. No legacy
  exceptions bypass the structural gate.

`just slo` requires raw benchmark samples for both HTTP search (p95 ≤ 200 ms) and
HTTP locate (p95 ≤ 50 ms). The gate rejects missing tests, unknown benchmarks,
missing samples, and tail regressions; a passing mean is insufficient. Temporary
benchmark files are unique and cleaned on every exit.
