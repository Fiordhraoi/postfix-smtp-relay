# Publishing and using the ready-made image

Image: `ghcr.io/fiordhraoi/postfix-smtp-relay`  
Platform: **linux/amd64**. ARM64 is not currently published or tested.

## How publishing works

The **Test and publish** Actions workflow runs for pushes to main, pull requests,
and manual dispatches. It validates configuration, builds one candidate image,
then runs the full mock-upstream SMTP integration suite against that image.
Only a successful run on this repository's main branch can push to GHCR.
The tested image is tagged and pushed directly, without a second build.

The workflow uses GitHub's temporary `GITHUB_TOKEN` with `packages: write`;
no personal token or extra repository secret is required. Only maintainers able
to change the main branch/workflow should be trusted with publication.

Tags:

- `latest`: the most recently published successful main-branch build.
- `sha-<full-40-character-Git-commit>`: a build of that source revision.

Tags can move if the same source is rebuilt against newer OS packages. Digests
identify exact image content. The revision label and GitHub source at that
revision provide the corresponding project source. Ubuntu and Postfix retain
their own licenses. The image includes this project's LICENSE and README in
`/usr/share/doc/smtp-relay/`.

## Make the package public once

GitHub initially creates container packages as **private**, even in a public
repository. The owner must change the package visibility before anonymous users
can pull it.

1. Open your [GitHub profile's Packages tab](https://github.com/Fiordhraoi?tab=packages).
2. Open the **postfix-smtp-relay** container package.
3. Click **Package settings**.
4. Under **Danger Zone**, choose **Change visibility**.
5. Select **Public** and complete GitHub's confirmation.

This makes the container image public, matching the public source repository.
Package settings are separate from repository settings. If the package is absent,
first check [Actions](https://github.com/Fiordhraoi/postfix-smtp-relay/actions)
for a successful publishing step.

Once public, test without signing into GHCR:

```sh
docker pull ghcr.io/fiordhraoi/postfix-smtp-relay:latest
```

See [GitHub's registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
for authentication and visibility details.

## Pin a deployment

Pull the desired image, then inspect its digest:

```sh
docker pull ghcr.io/fiordhraoi/postfix-smtp-relay:latest
docker image inspect ghcr.io/fiordhraoi/postfix-smtp-relay:latest --format '{{index .RepoDigests 0}}'
```

Copy the complete result beginning with
`ghcr.io/fiordhraoi/postfix-smtp-relay@sha256:`.
Create `compose.override.yaml` in the repository directory:

```yaml
services:
  smtp-relay:
    image: ghcr.io/fiordhraoi/postfix-smtp-relay@sha256:REPLACE_WITH_THE_ACTUAL_DIGEST
```

Replace the placeholder with the real digest before running Compose. If you
already have an override for secrets or certificates, add `image:` under its
existing `smtp-relay:` entry instead of replacing that file.

```sh
docker compose pull
docker compose up -d
```

Keep the same digest across sites for the same tested image. Change the pinned
digest deliberately for upgrades; pulling alone does not change a pinned digest.

## Local builds and tests

```sh
cp .env.example .env
docker compose -f compose.yaml -f compose.build.yaml build --pull
python3 -m unittest discover -s tests -v
RELAY_TEST_IMAGE=postfix-smtp-relay:local python3 tests/integration.py
```

`RELAY_TEST_IMAGE` tells the suite to test an already available image and retain
it afterward. Without that variable, the suite builds and deletes its own
uniquely named image. Both modes clean up their test containers, queue and network.

## If publishing fails

Open the failed workflow's **Publish tested image to GHCR** step. A failing test
prevents this step from running. If GHCR denies a push, check that the package
is linked to this repository and grants this repository Actions access in
**Package settings → Manage Actions access**. Organization policies can also
restrict package publishing or workflow permissions.

To retry after correcting a setting, open **Actions → Test and publish → Run
workflow**, select **main**, and run it. There is no scheduled rebuild: updates
are published on main pushes or a manual run.
