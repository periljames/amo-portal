# Controlled PDF reader navigation and loading repair

This branch corrects the reader regression where a page visible in the viewport could remain queued or blank while the toolbar reported another page, and where table-of-contents or PDF annotation jumps appeared not to work.

## Confirmed failure mechanism

The same IntersectionObserver was being used both to determine the authoritative visible page and to prefetch pages. Its network-dependent root margin reached several thousand pixels. Pages far outside the viewport were therefore treated as intersecting and could replace the actual visible page as the current render target. The bounded render window then retained the wrong pages and evicted the page the user was viewing.

## Repair contract

- Visible-page authority uses the real viewport only.
- Adjacent-page preloading remains controlled by the existing render radius and hot-page limit.
- A TOC or PDF destination jump primes the requested page, and the observer no longer immediately replaces it with an off-screen page.
- The page number, visible page, active contents row, and rendered canvas must remain synchronized.

## Browser acceptance

1. Open a publication of at least 100 pages.
2. Jump from page 1 to pages 50, 80, 95, and the last page using the page box.
3. Click nested Contents entries repeatedly, including duplicate heading text on different pages.
4. Click internal PDF links and bookmarks.
5. Scroll rapidly through the document in both directions.
6. Confirm the toolbar page number matches the visible page and the visible page renders without a prolonged queued placeholder.
7. Repeat under constrained-network emulation and at Fit width, Fit page, and custom zoom.
