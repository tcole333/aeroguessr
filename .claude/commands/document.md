  echo "Conduct a comprehensive documentation audit of the current directory and
  subdirectories.

  **Goal**: Identify documentation drift, missing docs, and inaccuracies that could mislead
  LLMs or developers.

  Follow these steps:

  1. **Inventory Documentation**:
     - List all .md files in current directory and subdirectories
     - Identify missing READMEs in key directories
     - Note any orphaned docs (referencing non-existent code)

  2. **Cross-Reference Implementation**:
     - For each documented feature/API/component:
       - Verify it exists in the codebase
       - Check if the implementation matches the description
       - Validate code examples still work
       - Confirm file paths and function names are current
     - For each code module:
       - Check if it has corresponding documentation
       - Identify undocumented public APIs or components

  3. **Validate Technical Accuracy**:
     - API endpoints match actual routes
     - WebSocket messages align with implemented handlers
     - Database schemas reflect current models
     - Configuration examples use correct variable names
     - Dependencies listed are actually used
     - Command examples execute successfully

  4. **Check Cross-References**:
     - Verify all @mentions and relative links resolve correctly
     - Ensure referenced issues/PRs are relevant and current
     - Validate external links are not broken

  5. **Assess Completeness**:
     - Each major feature has user-facing documentation
     - Setup instructions are complete and tested
     - Error scenarios and edge cases are documented
     - Testing instructions are current

  6. **Flag Critical Issues** (that could mislead LLMs):
     - 🚨 **CRITICAL**: Code has been removed but docs remain
     - 🚨 **CRITICAL**: API signatures have changed
     - 🚨 **CRITICAL**: Security practices documented incorrectly
     - ⚠️ **WARNING**: Examples use deprecated patterns
     - ⚠️ **WARNING**: Missing documentation for public APIs
     - 📝 **INFO**: Typos, formatting, or minor inconsistencies

  7. **Generate Audit Report**:
     Create 'documentation-audit-{date}.md' with:
     - Executive summary of findings
     - Critical issues requiring immediate attention
     - List of missing documentation
     - Specific drift items with code references
     - Recommendations for each issue
     - Priority order for fixes

  8. **Suggest Improvements**:
     - Recommend new READMEs where helpful
     - Propose documentation structure improvements
     - Identify opportunities for auto-generated docs
     - Suggest documentation templates for consistency

  **Special Focus Areas** (high risk for LLM confusion):
  - Configuration and environment setup
  - API contracts and schemas
  - State management and data flow
  - Build and deployment processes
  - Testing strategies and commands
  - Authentication and security patterns

  **Output Format**:
  - Clear severity levels (Critical/Warning/Info)
  - Specific file:line references
  - Before/after comparisons where applicable
  - Actionable fix recommendations
  - Priority ordering by impact

  Remember: The goal is to ensure LLMs and developers can trust the documentation as the source
   of truth."
