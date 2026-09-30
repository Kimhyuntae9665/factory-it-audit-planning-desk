# Frozen synthetic planning contract

This contract was authored before any P15 model use. There is no P15 model call or independent audit benchmark. Runtime reads scope, policy and evidence JSON only; expected-test-only.json is test-only. All records and site/role identifiers are fictional.

Primary scope: PLANT-A / MES-REPORT-A; audit interval [2026-08-01, 2026-09-01) by calendar date; planning cutoff 2026-09-10T09:00:00Z inclusive. Evidence must be available by cutoff, within the selected site/service and audit period, and the right artifact type. An applicable policy must be approved, available by cutoff and effective for the entire audit interval. ACCESS-01 v1 is the August monthly rule. Approved v2 becomes effective September 1 and draft v3 never governs August.

ACCESS-01 asks for reviewer role, review date and account-list version. EV-ACCESS-AUG-R1 cites AL-0829 as a candidate. EV-ACCESS-JUL-R1 is outside the August period. Neither is a control effectiveness result.

RESTORE-01 asks for a documented monthly restore exercise. EV-BACKUP-AUG-R1 is only a daily backup-completion summary and must create a restore-evidence request.

CHANGE-01 asks for change request, approval and implementation records for sampled changes. EV-CHANGE-AUG-R1 is planned only. Request confirmation of implementation and, if implemented, approval and implementation records. Absence is not an accusation.

INVENTORY-01 asks for a monthly component export with scope/completeness declarations. EV-INVENTORY-AUG-R1 contains a partial three-component list and cannot yield a full population or percentage. Its R2 is only available after the primary cutoff; the later cutoff may select it without retroactively changing the primary view. Even a declared-full R2 is an artifact claim, not verified operational completeness.

Role projection precedes candidate selection, sources, counts, review and export. PLANT-B policy/evidence cannot be inferred or read from PLANT-A. A demo actor header is not authentication/SSO. Every effectiveness/result cell begins unassessed. Reviewed-plan acknowledgment binds exact scope, cutoff, policy/evidence source hashes, rules version and actor role; it is never an audit pass or certification. A changed cutoff/revision invalidates export while retaining scoped historical receipts. No P15 model or external QMS write is authorized.
