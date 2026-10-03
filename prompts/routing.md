## Global role delegation

These rules apply to any Root model. Explicit user scope and project restrictions still apply. A process whose task starts with CODEX_ORCHESTRATION_CHILD executes its assigned task directly and must not delegate again.

- Handle short, local tasks directly. Delegate only a bounded task with a clear deliverable when separate investigation or implementation helps. File size alone is not a trigger.
- Run these roles through `py -3 "{{RUNNER}}" ROLE --cwd "ABSOLUTE_WORKSPACE" --task-file "ABSOLUTE_UTF8_BRIEF"`. These are separate Codex CLI processes, not native spawn_agent roles. The runner applies each role's model, effort, and Fast. Do not substitute native spawning for this route.
- Use `explorer` for independent cross-file investigation; `researcher` for independent documentation questions. Reuse existing findings and optimized read/search tools.
- Use `worker` for independent implementation with explicit file ownership and acceptance criteria. Root must not duplicate work or edit those files concurrently. Root owns Git staging, commits, and remote writes.
- Use `architect` before choosing a high-impact approach (public interfaces, persistent data, authentication, or cross-module contracts); after two failed fixes of the same issue; and before declaring a substantial multi-module change complete. Reuse a review if the evidence has not changed.
- Put the question, relevant evidence, constraints, authorized scope, expected output, and response language in the brief. The worker does not inherit this chat. Pass only needed context. Never put credentials in the brief. Use the user's output language.
- At most three role processes run concurrently. Wait for required results. The runner prints a result-file path; read it once with existing optimized tools. A failed process is not a completed review. Integrate results, verify acceptance criteria and tests, and report limitations.
- If the runner or requested model is unavailable, report the problem and complete permitted work directly. Do not silently change models or claim a review that did not run.
