# Superadmin session authentication fix

## Root cause

`platformConsole.ts` spread the return value of `authHeaders()` into a plain object. `authHeaders()` returns a `Headers` instance, whose entries are not enumerable object properties. The resulting `/platform/console/bootstrap` and `/platform/console/search` requests therefore omitted the Bearer token.

The first 401 response then called `endSession("manual")`, which posted `/auth/logout`, revoked the valid token server-side, cleared local authentication, and caused the remaining platform polling requests to fail. This made an active superuser session appear to expire immediately.

## Correction

- construct a real `Headers` instance and preserve the Authorization header;
- mark platform-console requests as active session work;
- refresh the access token through `/auth/extend-session` when it approaches expiry;
- handle a genuine 401 as an authentication failure without issuing a second logout request;
- add a regression test using a real `Headers` object so object-spread loss cannot recur.
