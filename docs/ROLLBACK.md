# Rollback

Before production upgrade, stop Odoo and capture the database, deployed commit,
group memberships, and add-on worktree state.

## Code-only rollback

Deploy the previous commit and upgrade `students` again only when the database
change is known to be reversible.

## Full rollback

For unexpected group, ACL, XML, schema, or data changes, stop Odoo and restore
the pre-upgrade database dump and previous add-on commit as one checkpoint.
Restart Odoo, verify `/web/login`, and repeat the access smoke tests.

Do not deploy `database_sekolah` until the `students` rollback or production
verification has completed.
