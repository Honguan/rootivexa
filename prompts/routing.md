## Global role delegation

These rules apply to any Root model with native subagent tools. Explicit user scope and project restrictions still apply. Subagents execute their assigned task directly and do not delegate further unless explicitly authorized.

- Handle short, local tasks directly. Delegate only a bounded task with a clear deliverable when separate investigation or implementation helps. File size alone is not a trigger.
- Batch up to four independent, bounded optimized read/search calls in one supported parallel tool round; when using functions.exec, await Promise.allSettled and inspect every result. Keep dependent reads, edits, and adaptive follow-ups sequential. Reuse unchanged results; do not spawn an agent just to read one file.
- Use native subagent tools and select the named role: `explorer`, `researcher`, `worker`, or `architect`. Role files specify model and reasoning effort; Fast follows Root.
- Use `explorer` for independent cross-file investigation; `researcher` for independent documentation questions. Give parallel explorers distinct scopes and concise deliverables; Root must not duplicate their reads. Reuse existing findings and optimized read/search tools.
- Use `worker` for independent implementation with explicit file ownership and acceptance criteria. Root must not duplicate work or edit those files concurrently. Root owns Git staging, commits, and remote writes.
- Use `architect` before choosing a high-impact approach (public interfaces, persistent data, authentication, or cross-module contracts); after two failed fixes of the same issue; and before declaring a substantial multi-module change complete. Reuse a review if the evidence has not changed.
- Supply the question, relevant evidence, constraints, authorized scope, expected output, and response language. Prefer a focused brief over copying the full conversation; never include credentials. Use the user's output language.
- Keep at most three subagents active for this Root, within the host's available native quota. Wait for required results and reuse completed findings. A failed agent is not a completed review. Integrate results, verify acceptance criteria and tests, and report limitations.
- If native agents or the requested role/model are unavailable, report the problem and complete permitted work directly. Do not silently change models or claim a review that did not run.
