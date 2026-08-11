# Access Matrix

## Groups

| Capability | Internal | Viewer | Trainer | Manager |
|---|---:|---:|---:|---:|
| Open student application | No | Yes | Yes | Yes |
| Read student, enrollment, exam, report, and portfolio data | No | Yes | Yes | Yes |
| Read the legacy student password field | No | No | No | Yes |
| Create/edit student master and enrollment | No | No | Limited enrollment update | Yes |
| Start/grade/reset exams | No | No | Yes | Yes |
| Create/finalize report assessment | No | No | Yes | Yes |
| Create/edit portfolio items | No | No | Yes | Yes |
| Delete operational academic records | No | No | No | Yes |
| Manage levels, class types, and report rubric | No | No | No | Yes |

`Manager` implies `Trainer`; `Trainer` implies `Viewer`; `Viewer` implies the
standard internal-user group.

## Ownership Rules

Trainer-specific record rules are intentionally deferred until assignment data
is complete. At the migration baseline, only 3 of 11 private-student report
assessments have `pelatih_id`. Enabling an ownership rule before backfilling
that data would hide active records from legitimate trainers.

The ownership cutover must be completed together with attendance assignment:

1. Establish the authoritative trainer field for every active enrollment.
2. Backfill existing enrollment, exam, report, and portfolio ownership.
3. Validate zero active unassigned records.
4. Add and test trainer record rules.
