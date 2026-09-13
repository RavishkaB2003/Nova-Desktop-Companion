<#
.SYNOPSIS
  Publishes clean client-facing code to GitHub without internal agent framework files.
.DESCRIPTION
  Syncs client files (assets, nova, scripts, models, requirements.txt, README.md)
  to the client-main branch and force-pushes to origin, keeping .agents, docs, and internal
  governance files completely invisible to the client.
#>

param (
    [string]$CommitMessage = "feat: update Project NOVA release"
)

Write-Host "Publishing clean client files to GitHub..." -ForegroundColor Cyan

# 1. Ensure working tree is committed on dev
$status = git status --porcelain
if ($status) {
    Write-Error "Working tree has uncommitted changes. Please commit or stash before publishing."
    exit 1
}

# 2. Switch to client-main
git checkout client-main

# 3. Pull client-distributable files directly from dev
git checkout dev -- README.md requirements.txt scripts assets nova tests

# 4. Stage only client-distributable assets & code
git add README.md requirements.txt scripts/ assets/ nova/ tests/
if (Test-Path "models/.gitkeep") {
    git add models/.gitkeep
}

# 5. Commit
git commit -m $CommitMessage --allow-empty

# 6. Push to remote
git push origin client-main:main --force
git push origin client-main:dev --force

# 7. Switch back to dev
git checkout -f dev

Write-Host "Successfully published clean client distribution to GitHub!" -ForegroundColor Green