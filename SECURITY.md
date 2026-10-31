# Security policy

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's private vulnerability reporting: open the repository's **Security** tab and choose **Report a vulnerability** ([direct link](https://github.com/tcole333/aeroguessr/security/advisories/new)). Please don't open a public issue or pull request for a vulnerability.

A useful report says:
- what is affected (the backend, the frontend, the published images, `selfhost/compose.yaml`, the release workflow);
- the version or commit;
- how to reproduce it, and what an attacker gains.

AeroGuessr is maintained by one person in their spare time, so reports are handled on a best-effort basis. You'll hear back in the advisory thread, and fixes ship in a new release.

## Supported versions

AeroGuessr is in alpha. Only the latest release gets fixes; update by following [docs/self-hosting.md](docs/self-hosting.md#updating).

## Scope

In scope: the code in this repository, the images the release workflow publishes, and aeroguessr.com, the maintainer's instance.

Out of scope:
- **Other self-hosted instances.** Each one is run by its own operator. Report a problem with one to its operator, unless the cause is in this code.
- **Third-party services**, such as FlightAware AeroAPI, OpenFreeMap and Cloudflare. Report those to their owners.

If you come across an exposed API key or other credential belonging to this project, report it here as a vulnerability.

## Testing

aeroguessr.com runs on one Raspberry Pi. When you look into a problem:
- reproduce it on your own instance where you can ([docs/self-hosting.md](docs/self-hosting.md));
- don't run load tests, denial-of-service attempts or automated scanners against aeroguessr.com;
- use only rooms and data you created yourself.
