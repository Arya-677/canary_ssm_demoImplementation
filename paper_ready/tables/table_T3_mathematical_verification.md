# table_T3_mathematical_verification: Mathematical and Software Correctness Verification



| Test_Suite                                   | Theoretical         | Empirical        |   Abs_Error | Result   |
|:---------------------------------------------|:--------------------|:-----------------|------------:|:---------|
| Exact Scalar Kalman Fixture (Step 1 Mean)    | 0.6875              | 0.6875           |       0     | True     |
| Exact Scalar Kalman Fixture (Step 1 Var)     | 0.34375             | 0.34375          |       0     | True     |
| Exact Scalar Kalman Fixture (Step 2 Mean)    | 0.8344370860927153  | 0.834437         |       1e-16 | True     |
| Exact Scalar Kalman Fixture (Step 2 Var)     | 0.23509933774834438 | 0.235099         |       1e-16 | True     |
| Joseph Form PSD Stability (Cond 1e2 to 1e12) | lambda_min >= 0     | > 0.0            |       0     | True     |
| Basis Orthogonality C^T B                    | 0.0                 | 0.0              |       1e-16 | True     |
| Basis Orthonormality B^T B                   | I                   | I                |       1e-16 | True     |
| Telemetry Causal Invariants (TEL-01 to 10)   | Prefix Invariant    | Prefix Invariant |       0     | True     |
| Comparator Semantics (KAY, ARGO, FLAG, SLO)  | Deterministic Trace | Matched Trace    |       0     | True     |
