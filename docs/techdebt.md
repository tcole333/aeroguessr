## ⛳ Item: Deferred CI/CD Deployment Setup to Raspberry Pi

- **Context:** Initial project setup phase (Tasks 8, 9, 10 in `docs/task-list.md`). Decided to focus on local development and core feature implementation first.
- **Potential issues:** The full CI/CD loop isn't validated early. Deployment issues might be discovered later in the development cycle. The current GitHub Actions workflow (`lint.yml`) builds the Docker image but doesn't deploy it.
- **Why accepted:** To accelerate initial local development and feature prototyping without the overhead of setting up Pi network access (port forwarding/tunnels) and SSH credentials securely in CI at this stage.
- **Next step:** Revisit Tasks 8, 9, and 10 when ready to set up automated deployment. This involves finalizing Pi network access (direct SSH or tunnel like Cloudflare/Tailscale), configuring GitHub secrets (`PI_DEPLOY_KEY`, `PI_HOST`, `PI_USER`), writing `infra/deploy.sh`, and adding a deployment job to the GitHub Actions workflow.
- **Code Ref:** `docs/task-list.md#L16` (Task 8 link), `.github/workflows/lint.yml`

---
