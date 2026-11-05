# AI Quality Suite contributor instructions

- Target CPython 3.11.15. Use the committed `uv.lock` and `package-lock.json`. Update locks and run the relevant adapter tests when changing dependencies.
- `app.main.create_app` is the FastAPI composition root. Keep HTTP adapters, generation, retrieval, session state, and evaluation separate. The evaluation runner shares the live RAG pipeline.
- Keep production code typed and readable. Use dependency injection for offline failure tests. Keep provider errors structured and avoid logging prompts, answers, secrets, or provider exception text.
- The handbook, safety fixtures, and evaluation data are synthetic. Keep safety fixtures outside the public index. Update the manifest and evidence spans when editing datasets. Keep generated reports, state, caches, model files, and credentials outside Git.
- Run `uv sync --locked`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run python -m evaluation.datasets`, and `uv run python -m pytest --cov`. Use `--group judges` for adapter tests and `scripts/test.ps1 -Live` for the opt-in real RAG check.
- Treat missing model or judge results as incomplete or errors. Record the scope of every executed check in `docs/results.md` and distinguish mocked, embedded, local live, and remote CI evidence.
- Completion requires working serving and evaluation paths, dataset validation, bounded safety and failure tests, compatible baseline comparison, transactional history, generated reports, pinned dependencies, and verified reproduction commands. Publish or run paid services only with the user's authorization.
