# contrib/

Community and experimental integrations. Not wired into the CLI or core pipeline.

## github_integration.py

GitHub API client (`GitHubClient`) and `GraphCollaborationManager` for triggering
graph updates on PR events. Reads `GITHUB_TOKEN` from env.

**Not yet exposed as a CLI command.** Wire into a GitHub Actions workflow or call
directly from a webhook handler:

```python
from contrib.github_integration import GitHubClient, GraphCollaborationManager

client = GitHubClient(token=os.environ["GITHUB_TOKEN"])
manager = GraphCollaborationManager(client)

# In a PR webhook handler:
if manager.should_update_graph_on_pull_request(pr_data):
    info = manager.get_collaboration_info(pr_data)
    # trigger smt sync or smt build
```
