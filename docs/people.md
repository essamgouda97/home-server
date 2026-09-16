# People: household account onboarding

`https://people.home.egouda.xyz` is the owner-only household roster and invitation
console. It reads the non-secret `config/identities.json` policy and shows current
grants. The app does not replace Authelia, Jellyfin, Requests or File Browser.
The owner is `egouda` (Essam); `mgouda` remains Mariam's separate account.

## Invite a person

1. Sign in to People as `egouda`. Choose a new username, display name and only
   the services that person needs. Media clients and Requests require Jellyfin.
2. Copy the generated HTTPS invitation link. It appears once and expires in 24
   hours. Share it privately with the intended person. Do not put it in Git or
   public messages.
3. The invitee opens it and creates their own password (16+ characters). The
   browser never sends the token in an HTTP URL: it is stored in the link
   fragment, removed from browser history on page load, then sent in the request
   body. People stores only its SHA-256 digest and never saves plaintext
   passwords. The password travels through a protected local pipe to the
   enrollment helper, which writes the Authelia verifier and native Jellyfin
   profile. It is not passed in a shell argument or environment variable.
4. Verify the new account with its owner present: sign in to the final HTTPS
   Home dashboard, then open each granted service. For Moonfin, approve Quick
   Connect in the *new person's* Jellyfin profile and test remote playback.
   Use [household onboarding](household-onboarding.md) for phone and TV setup.

The first invitation can be tested with a spare new username before inviting
family. Do not use `egouda` or `mgouda`: existing identities cannot be
re-enrolled, protecting their media history and sessions.

## Security and lifecycle

- The owner route uses the shared Authelia gateway and checks the authenticated
  `egouda` identity again in the backend. A private proxy key prevents other
  containers or direct clients from spoofing that header. The backend binds only
  to the Docker proxy bridge; it has no LAN or Internet listener.
- `/join/` is an explicit path exception in the shared proxy compiler. It has
  **no owner powers**; every enrollment action needs an unexpired, single-use,
  256-bit random invitation token. The default host policy remains owner-only.
  Same-origin JSON POST checks and an 8 KiB body limit constrain the endpoint.
- Invitations live at `~/.config/home-server/secrets/people/invitations.json`
  with mode 600. The proxy key lives next to it and is installed into Nginx via
  stdin. Both are outside Git. Configuration rollback copies live under
  `~/.local/state/home-server-maintenance/people/`.
- The current UI creates accounts and displays grants. Changing or revoking an
  existing person's access still requires the reviewed operator procedure in
  [authentication](authentication.md). Revoking gateway access alone does not
  revoke native Jellyfin sessions, LAN clients or Tailscale sharing.
- Provisioning across native apps is not a database transaction. If a step
  fails, the invitation becomes `needs-review` and cannot be reused. Inspect
  native profiles and private state before creating another link; preserve any
  existing watch history and requests. Do not delete a partial account merely
  to retry.
- `config/identities.json` changes on the server during enrollment. Commit and
  push that **non-secret** file, then pull the Mac checkout after verification.
  Never commit private users.yml or the invitation store. This is an operator
  follow-up until policy synchronization is automated.

## Deployment and checks

On the server, after syncing the repo changes, run:

```sh
python3 scripts/test-people.py
python3 scripts/configure-people.py
python3 scripts/check-auth.py
python3 scripts/sync-service-catalog.py
python3 scripts/provision-homarr-identities.py
make check-server
```

The server service is `systemctl --user status home-server-people.service`.
The `check-people.py --local` check proves the backend rejects missing proxy
keys and non-owner identities. Its HTTPS check proves an actual owner sign-in,
anonymous owner-route denial, and access to only the public invitation page.
Run `make check-network` on the Mac after deployment. To roll back the route,
restore the private Nginx backup, reload Nginx, and stop the user service. Keep
the identities and native profiles already enrolled.
