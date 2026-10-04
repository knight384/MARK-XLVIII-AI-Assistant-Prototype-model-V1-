# Developer Intelligence Architecture

Developer Intelligence in MARK XLVIII provides native capabilities for safe repository inspection and controlled modifications. 

## Security Principle
Developer Intelligence is NOT an authorization boundary. All operations execute via:
Developer Agent -> ToolExecutor -> PolicyEngine -> ApprovalManager -> SandboxManager.

## Features
- **Project Index**: Detects languages, package managers, test configs.
- **Context Builder**: Bounded aggregation of metadata, Git status, and relevant files.
- **Safe Modifications**: Reads are unblocked; writes require Approval.
