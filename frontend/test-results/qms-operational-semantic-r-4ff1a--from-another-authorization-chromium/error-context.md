# Page snapshot

```yaml
- generic [ref=e2]:
  - alert [ref=e3]:
    - generic [ref=e4]:
      - img [ref=e5]
      - generic [ref=e7]:
        - heading "This page could not be displayed" [level=1] [ref=e8]
        - paragraph [ref=e9]: personnel is not iterable
        - paragraph [ref=e10]: Reload the page and repeat the action. Any records already saved to the server remain available.
      - button "Reload page" [ref=e11] [cursor=pointer]:
        - img [ref=e12]
        - text: Reload page
  - button "Open inbox" [ref=e18] [cursor=pointer]:
    - img [ref=e19]
  - generic "System notifications":
    - alert [active] [ref=e21]:
      - img [ref=e23]
      - generic [ref=e25]:
        - generic [ref=e26]: This page could not be displayed
        - generic [ref=e27]: personnel is not iterable
        - button "Reload page" [ref=e28] [cursor=pointer]
      - button "Dismiss notification" [ref=e29] [cursor=pointer]:
        - img [ref=e30]
```