# Adapter plugins

Third-party packages can add adapters without changing Voice Eval. Expose a
zero-argument factory in your package's `pyproject.toml`:

```toml
[project.entry-points."voice_agent_eval_lab.adapters"]
my-pipeline = "my_package:make_adapter"
```

The factory must return a `VoicePipelineAdapter`. After installing the package,
`get_adapter("my-pipeline")` discovers it automatically. Adapter names are
case-insensitive. Empty names, duplicate names, unknown names, and factories
that return the wrong type produce explicit errors.

Applications can also call `register_adapter("my-pipeline", factory)` during
startup. Set `replace=True` only when intentionally overriding a registration.

