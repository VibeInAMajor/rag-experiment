"""Load the production adapter after the application admits a request."""

from agent_runtime.runtime import AgentRuntime


def create_runtime() -> AgentRuntime:
    from agent_runtime.adapters.maf_openai import MafOpenAIRuntime

    return MafOpenAIRuntime()
