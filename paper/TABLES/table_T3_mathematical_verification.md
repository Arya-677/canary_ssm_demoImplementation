# table_T3_mathematical_verification: Kalman Reference Fixture and Matrix Algebraic Verification



| Verification_Task            | Theoretical         | Empirical   |   Abs_Error | Result   |
|:-----------------------------|:--------------------|:------------|------------:|:---------|
| Scalar Fixture Step 1 (Mean) | 0.6875              | 0.6875      |       0     | True     |
| Scalar Fixture Step 1 (Var)  | 0.34375             | 0.34375     |       0     | True     |
| Scalar Fixture Step 2 (Mean) | 0.8344370860927153  | 0.834437    |       1e-16 | True     |
| Scalar Fixture Step 2 (Var)  | 0.23509933774834438 | 0.235099    |       1e-16 | True     |
| Joseph PSD (Cond 1e2)        | >= 0.0              | 0.0452      |       0     | True     |
| Joseph PSD (Cond 1e6)        | >= 0.0              | 0.0001      |       0     | True     |
| Joseph PSD (Cond 1e12)       | >= 0.0              | 1.2e-09     |       0     | True     |
| Basis Orthogonality C^T B    | 0.0                 | 0.0         |       1e-16 | True     |
| Basis Orthonormality B^T B   | I                   | I           |       1e-16 | True     |
