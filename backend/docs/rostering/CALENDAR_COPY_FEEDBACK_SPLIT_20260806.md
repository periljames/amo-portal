# Calendar copy feedback split

The calendar-link copy feedback is intentionally separated from the personal calendar backend repair.

The frontend implementation must use an explicit helper called only by intended copy controls. It must not replace `navigator.clipboard.writeText` globally or infer the triggering control from `document.activeElement`.

This work remains independent from the backend calendar-feed pull request and is not required to restore the `.ics` endpoint.
