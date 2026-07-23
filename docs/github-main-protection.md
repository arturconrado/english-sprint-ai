# Future `main` protection

The repository is private and owned by a GitHub Free personal account. Branch
protection for private repositories requires GitHub Pro, Team, or Enterprise, so
these rules are intentionally documented instead of being falsely reported as
active.

After upgrading the plan, apply the following rules to `main`:

- require pull requests before merging;
- require zero approvals for the individual owner;
- require the unique `contract`, `backend`, `android`, `ios`, and `security` checks;
- require the branch to be up to date;
- require conversation resolution;
- block force pushes;
- block branch deletion.

Repository-level merge settings remain active without branch protection:

- squash merge is the only enabled merge strategy;
- merged head branches are deleted automatically.
