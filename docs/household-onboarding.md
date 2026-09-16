# Household media and service onboarding

Use this when someone joins the household or adds a phone/TV. Keep each person’s
Jellyfin, Requests, Homarr and Tailscale identities separate. The server address
is shared; user accounts and permissions are not.

## Existing household member: add a device

1. Decide whose media profile the device should use. `egouda` is the owner;
   `mgouda` is Mariam. On a shared TV, add each as a separate Moonfin user and
   switch users. Do not approve a code from one person under another’s account.
2. For a phone, install Tailscale and Moonfin. The owner signs Tailscale into the
   existing owner tailnet. A second person uses **their own** Tailscale account
   and accepts a single-use share of only `home-server` from the owner. Do not
   share the owner’s Tailscale account or password. A machine share does not
   carry the LAN subnet route; all shared users use the HTTPS address below.
3. Keep Tailscale connected. On iPhone, its VPN On Demand option can connect on
   cellular and other Wi-Fi automatically. Only one VPN can be active at a time.
   The owner can revoke a shared device from the Tailscale Machines page.
4. In Moonfin, add `https://home-server.tail9bfb3e.ts.net` as the server on
   phones, at home and away. The basement TV may continue using
   `http://10.0.0.182:8096` on home Wi-Fi. The private HTTPS address does **not**
   use the browser Authelia page; Jellyfin authenticates the app itself.
5. Choose Quick Connect in Moonfin. The short code is temporary. Approve it in
   **that same person’s** signed-in Jellyfin account. A code approved while
   `egouda` is signed in creates an `egouda` Moonfin profile, even if Mariam
   initiated it. Never send a password or long-lived token in chat. If the code
   expires, generate a new one.
6. Check Moonfin’s displayed user, library, watch history and playback. On a
   phone, turn Wi-Fi off and verify over cellular. Test Requests separately;
   the installed Jellyseerr 2.7.3 may need one native request login per person.
   Request access must match that person’s existing Jellyseerr permissions.

The owner’s phone Quick Connect was approved as `egouda` on September 16, 2026.
Jellyfin reported a distinct Moonfin phone session and TV session. Actual
cellular playback and Mariam’s Moonfin sign-in remain to be checked.

## New person: create their accounts first

The normal path is the owner-only [People app](people.md) at
`https://people.home.egouda.xyz`. Choose the person's services there, send the
one-use private invitation, and let them create their own password. Verify the
final HTTPS sign-ins and Moonfin profile after enrollment. Existing `egouda`
and `mgouda` profiles stay intact.

The terminal helper below is the recovery/operator path if People is unavailable.

The owner or a trusted operator runs the enrollment helper on the server in an
interactive SSH terminal. Confirm the service list before running it; default
grants are `homarr,jellyfin,vue,requests`, not owner/admin tools. The helper
rejects existing usernames and asks for a new password through a hidden prompt.
The person should enter or choose it privately and save it in their own password
manager. Do not type a password into chat, shell arguments, Git or a ticket.

```sh
ssh -t home-server
cd ~/workspace/home-server
python3 scripts/enroll-household-user.py USERNAME --name 'Display Name' \
  --services homarr,jellyfin,vue,requests
```

The helper creates the central verifier and explicit grants, an ordinary Jellyfin
profile, a Requests import for that exact profile ID, a private Homarr board,
and an explicit Jellyfin OIDC subject link. It does not grant ownership. For
`files`, the helper also creates a dedicated private folder and constrained File
Browser account; never grant broad access to the owner’s storage root.

Check the person’s normal HTTPS sign-in and role before giving them a Tailscale
share. Run `scripts/check-household-identities.py` for the original `mgouda`
invariants and `scripts/check-auth.py` for gateway entitlements, then verify the
new account interactively. Review Requests’ default permissions before new
enrollments; the helper does not currently set a custom request quota or approval
policy. Password changes in Jellyfin and Authelia are **not synchronized** after
initial enrollment, so use a reviewed rotation procedure for both systems.

If enrollment stops partway through, inspect the identities and native profiles
before retrying. The helper intentionally refuses to overwrite an existing user;
never delete a profile that might have requests or watch history just to rerun it.
Commit only `config/identities.json` and other non-secret policy/documentation;
sync both repository checkouts. Back up private Authelia and application state.

## Boundaries and recovery

- The tailnet policy in [`config/tailscale/media-access.hujson`](../config/tailscale/media-access.hujson)
  gives shared users only HTTPS port 443 on `home-server`. Public Funnel is off.
- Tailscale grants reachability. Jellyfin and Moonfin still require a separate
  user login; Jellyseerr applies its own request permissions.
- To revoke a lost phone, revoke its Tailscale share/device and its Jellyfin
  sessions. Do both: they are independent authorizations.
- A new household member needs only the services deliberately granted in
  `config/identities.json`. The base `household` group grants nothing by itself.
- Keep `make check-network` and `make check-server` green after infrastructure
  changes. The main [authentication runbook](authentication.md) documents SSO,
  native-login exceptions and encrypted recovery.
