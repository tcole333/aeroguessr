#!/bin/bash
ISSUE_NUMBER=$1
if [ -z "$ISSUE_NUMBER" ]; then
    echo "Usage: $0 <issue-number>"
    exit 1
fi

# Fetch issue title for branch name
ISSUE_TITLE=$(gh issue view $ISSUE_NUMBER --json title -q .title | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | cut -c1-30)

git checkout main && git pull
git checkout -b "feature/$ISSUE_NUMBER-$ISSUE_TITLE"
echo "Created branch for issue #$ISSUE_NUMBER"
