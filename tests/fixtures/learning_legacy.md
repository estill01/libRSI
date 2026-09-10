# Legacy adaptive replay fixture

`learning_legacy.json` contains actual canonical inputs, ordinary feedback and
runtime transitions produced using the installed libRSI `c775bb41` wheel (source
fingerprint in the JSON), whose adaptive implementation matches the pre-change
`4f06a6c` main revision. It is not a hand-authored approximation of an old request.

The unchanged `examples/adaptive_strategy.py` supplied adapter, policy and provider
identities. Two profiles execute its two ordinary training inputs. One provider
raises `KeyboardInterrupt` after action persistence, leaving a pending request;
the other raises `OSError`, producing a completed native failure. Both use pass ID
`legacy`, the example's held-out inputs and `activate=False`.

The test restores the trace through public LearningStore/RuntimeStore writes,
checks the original state root, resumes the pending action with its exact request,
and reads the completed result without a new call. Old context shape and unknown
telemetry remain intact. No mutable environment or consumer profile is imported
by these replay tests.
