# CostGuard CLI

Cloud cost analysis tool for Terraform. Get cost estimates before deploying infrastructure.

## Installation

```bash
pip install costguard
```

## Quick Start

```bash
# Configure API key
costguard configure --api-key YOUR_API_KEY

# Analyze a single project
costguard breakdown --path ./terraform

# Analyze multiple projects with config file
costguard breakdown --config costguard.yml

# Output as JSON
costguard breakdown --path ./terraform --format json

# Output for GitHub PR comment
costguard breakdown --config costguard.yml --format github-comment --out comment.md
```

## Configuration

Create a `costguard.yml` in your repository root:

```yaml
version: 1

projects:
  - path: infrastructure/aws
    name: AWS Production

  - path: infrastructure/gcp
    name: GCP Production

  - path: infrastructure/azure
    name: Azure Production

thresholds:
  warn_monthly_cost: 1000
  fail_monthly_cost: 10000

output:
  format: table
  show_resources: true
```

## Commands

### `costguard breakdown`

Analyze Terraform plans and show cost breakdown.

```bash
# Options
--path, -p       Path to Terraform directory
--config, -c     Path to costguard.yml
--format, -f     Output format: table, json, github-comment
--out, -o        Output file path
--resources      Show resource breakdown (default: true)
--api-key        CostGuard API key
```

### `costguard configure`

Configure CLI settings.

```bash
costguard configure --api-key YOUR_KEY
costguard configure --show
```

### `costguard version`

Show version information.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `COSTGUARD_API_KEY` | API key for authentication |
| `COSTGUARD_API_URL` | API endpoint URL |

## CI/CD Integration

### GitHub Actions

```yaml
- name: Install CostGuard
  run: pip install costguard

- name: Analyze costs
  env:
    COSTGUARD_API_KEY: ${{ secrets.COSTGUARD_API_KEY }}
  run: |
    costguard breakdown --config costguard.yml --format github-comment --out comment.md

- name: Post PR comment
  uses: actions/github-script@v7
  with:
    script: |
      const fs = require('fs');
      const comment = fs.readFileSync('comment.md', 'utf8');
      github.rest.issues.createComment({
        owner: context.repo.owner,
        repo: context.repo.repo,
        issue_number: context.issue.number,
        body: comment
      });
```

### GitLab CI

```yaml
cost-check:
  image: python:3.11
  script:
    - pip install costguard
    - costguard breakdown --config costguard.yml --format json
```

## Output Formats

### Table (default)
```
  === CostGuard Cost Analysis ===

  Total Monthly Cost: $2,861.84
  Decision: [OK] ALLOW

  === Projects ===

  [OK] AWS Production
     Path: infrastructure/aws
     Cost: $2,725.00/month
```

### JSON
```json
{
  "status": "success",
  "decision": "ALLOW",
  "summary": {
    "total_monthly_cost": 2861.84
  },
  "projects": [...]
}
```

### GitHub Comment

Markdown formatted for PR comments with collapsible resource sections.

## License

MIT License - see LICENSE file.
