# P09 v2 visual alignment and P15 behavior checks

The prior public P15 commit `d2b5840a15c0febae73a034e83e5821cdbcddf56` used a dark full-width header, 1500px workspace and asymmetric matrix/sidebar. The current interface follows the actual [P09 v2 development view](https://github.com/Kimhyuntae9665/maintenance-job-plan-draft-review/blob/main/artifacts/media/v2-development-stored-desktop.png): page `#f1f4f6`, text `#142635`, primary `#173f60`, white 1px `#9eaeba` panels, evidence surface `#e7edf1`, centered 1120px content with 24px padding and two equal columns separated by 20px. The compact Korean title stays on one line at 390px. The matrix remains source-facing and the request/review column remains result-facing; source strings and warnings remain visible.

The same pass reproduced and fixed three state defects without changing source fixtures or audit meaning:

1. A late source A response could overwrite the currently open B dialog. A per-dialog request identity now prevents this; a live Chrome delayed-response test holds A, opens B, then releases A and checks B title/body.
2. A draft review note could cross a cutoff boundary and be submitted against another packet. Loading a new scope clears the unbound draft. Receipts stay bound to their original packet.
3. Switching demo role reset still-valid July/later filters. The role refresh now restores allowed filter values and clears the note. The read-only role still cannot submit.

An independent source review also found that July planning request text named August. The question now uses the selected month, and a July/August regression checks both wording and unassessed status. These are engineering/browser regressions, not audit-effectiveness checks. The 10 recaptured feature screenshots and workflow video replace the previous styling at the same paths; no old screenshot is represented as current.
