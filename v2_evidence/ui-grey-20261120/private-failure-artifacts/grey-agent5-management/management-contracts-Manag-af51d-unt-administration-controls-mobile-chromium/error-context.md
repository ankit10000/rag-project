# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - link "Skip to content" [ref=e2] [cursor=pointer]:
    - /url: "#main"
  - button "Open Next.js Dev Tools" [ref=e8] [cursor=pointer]:
    - img [ref=e9]
  - alert [ref=e12]
  - generic [ref=e14]:
    - banner [ref=e15]:
      - generic [ref=e16]:
        - button "Toggle navigation" [ref=e17] [cursor=pointer]:
          - img
        - link "RAG workspace" [ref=e18] [cursor=pointer]:
          - /url: /chat
      - link "Sources" [ref=e19] [cursor=pointer]:
        - /url: /documents
        - text: Sources
        - img [ref=e20]
    - main [ref=e23]:
      - generic [ref=e24]:
        - generic [ref=e25]:
          - generic [ref=e26]:
            - img [ref=e27]
            - heading "Users & access" [level=1] [ref=e29]
          - paragraph [ref=e30]: Manage who can use this workspace.
        - alert [ref=e31]:
          - heading "Access denied" [level=2] [ref=e32]
          - paragraph [ref=e33]: This page is available to administrators.
```