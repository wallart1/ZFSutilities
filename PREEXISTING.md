# This file is maintained by Kimi Code. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (policy-vs-practice, coding-policies.md): The Bash section says regexes
  "may not exceed 10 characters in length," but several shipped scripts use
  longer, comment-documented regexes (`move-vm-disk` ×4, `remove-vm`,
  `install-two-node` ×2, and now `enroll-proxmox-pool`'s storage-ID check,
  which mirrors its documented Python counterpart). Either the policy should
  be relaxed to the Python wording ("profusely documented") or the shipped
  regexes rewritten as glob patterns. Pre-dates this cycle; recorded during
  the 2026-10-02 standards review.
