  echo "review the issue described in #$ARGUMENTS. Follow these steps:

  1. **Understand the issue** described in the text and its business impact
  2. **Locate the relevant code** in our codebase (components, services, tests, schemas, types)
  3. **Identify the type**: bug, feature, or tech debt (check all templates in
  .github/ISSUE_TEMPLATE/)
  4. **Select the relevant issue template** and understand its required fields
  5. **Think through potential stumbling blocks** including:
     - Edge cases and error conditions
     - Mobile/responsive design considerations (PRD emphasizes mobile-first)
     - Performance implications (especially for real-time gameplay)
     - Accessibility requirements (screen readers, keyboard navigation)
     - Security considerations if handling user input or sensitive data
  6. **Identify comprehensive test cases** including:
     - Unit tests for individual functions/components
     - Integration tests for API/WebSocket interactions
     - Manual testing scenarios across devices
     - Accessibility testing if applicable
  7. **Consider issue scope**: Should work be contained within one issue or split into multiple
   self-contained issues? Good self-contained issues have:
     - Clear, independent deliverables
     - Minimal dependencies on other unfinished work
     - Can be tested and verified independently
     - Reasonable size for development iteration (1-3 days typically)
  8. **Review existing open issues** for:
     - Overlap or duplication
     - Dependencies that affect sequencing
     - Related work that could be coordinated
     - Conflicting priorities or approaches
  9. **Check implementation requirements**:
     - API changes need schema regeneration (make openapi/ws-schema)
     - WebSocket changes need type updates
     - New dependencies need justification
     - Documentation updates for user-facing features
  10. **Ensure alignment with PRD spirit**: casual, real-time, mobile-first social gaming
  11. **Complete and submit** the issue to GitHub with appropriate labels and priority"
