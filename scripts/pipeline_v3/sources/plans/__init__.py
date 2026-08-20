from scripts.pipeline_v3.sources.plans.anthropic import AnthropicPlanAdapter
from scripts.pipeline_v3.sources.plans.cursor import CursorHobbyPlanAdapter, CursorPlanAdapter, CursorTeamsPlanAdapter
from scripts.pipeline_v3.sources.plans.github import GitHubCopilotOrganizationPlanAdapter, GitHubCopilotPlanAdapter
from scripts.pipeline_v3.sources.plans.kiro import KiroPlanAdapter
from scripts.pipeline_v3.sources.plans.google import GooglePlanAdapter
from scripts.pipeline_v3.sources.plans.minimax import MiniMaxPlanAdapter
from scripts.pipeline_v3.sources.plans.moonshot import MoonshotPlanAdapter
from scripts.pipeline_v3.sources.plans.openai import OpenAIPlanAdapter
from scripts.pipeline_v3.sources.plans.openai_commercial import OpenAIBusinessPlanAdapter, OpenAIProPlanAdapter
from scripts.pipeline_v3.sources.plans.opencode import OpenCodePlanAdapter
from scripts.pipeline_v3.sources.plans.qwen import QwenTokenPlanAdapter
from scripts.pipeline_v3.sources.plans.xiaomi import XiaomiPlanAdapter
from scripts.pipeline_v3.sources.plans.zhipu import ZhipuPlanAdapter


def verified_plan_adapters(timeout_seconds: int = 45):
    """Official sources that pass unattended live extraction checks."""
    return [
        AnthropicPlanAdapter(timeout_seconds=timeout_seconds),
        CursorPlanAdapter(timeout_seconds=timeout_seconds),
        CursorTeamsPlanAdapter(timeout_seconds=timeout_seconds),
        GitHubCopilotPlanAdapter(timeout_seconds=timeout_seconds),
        GitHubCopilotOrganizationPlanAdapter(timeout_seconds=timeout_seconds),
        KiroPlanAdapter(timeout_seconds=timeout_seconds),
        GooglePlanAdapter(timeout_seconds=timeout_seconds),
        OpenAIPlanAdapter(timeout_seconds=timeout_seconds),
        MiniMaxPlanAdapter(timeout_seconds=timeout_seconds),
        OpenCodePlanAdapter(timeout_seconds=timeout_seconds),
        QwenTokenPlanAdapter(timeout_seconds=timeout_seconds),
        ZhipuPlanAdapter(timeout_seconds=timeout_seconds),
    ]


def experimental_plan_adapters(timeout_seconds: int = 45):
    """Official sources still blocked by login, WAF, or missing public prices."""
    return [
        # OpenAI's Help Center currently returns 403/WAF to unattended
        # requests in validation. Keep these parsers available for probing,
        # but do not make them release-blocking until their official source is
        # reliably accessible from the deployment environment.
        OpenAIProPlanAdapter(timeout_seconds=timeout_seconds),
        OpenAIBusinessPlanAdapter(timeout_seconds=timeout_seconds),
        CursorHobbyPlanAdapter(timeout_seconds=timeout_seconds),
        MoonshotPlanAdapter(timeout_seconds=timeout_seconds),
        XiaomiPlanAdapter(timeout_seconds=timeout_seconds),
    ]


def all_plan_adapters(timeout_seconds: int = 45):
    return [
        *verified_plan_adapters(timeout_seconds),
        *experimental_plan_adapters(timeout_seconds),
    ]


__all__ = [
    "AnthropicPlanAdapter",
    "CursorPlanAdapter",
    "CursorHobbyPlanAdapter",
    "CursorTeamsPlanAdapter",
    "GitHubCopilotPlanAdapter",
    "GitHubCopilotOrganizationPlanAdapter",
    "KiroPlanAdapter",
    "GooglePlanAdapter",
    "MiniMaxPlanAdapter",
    "MoonshotPlanAdapter",
    "OpenAIPlanAdapter",
    "OpenAIProPlanAdapter",
    "OpenAIBusinessPlanAdapter",
    "OpenCodePlanAdapter",
    "QwenTokenPlanAdapter",
    "XiaomiPlanAdapter",
    "ZhipuPlanAdapter",
    "verified_plan_adapters",
    "experimental_plan_adapters",
    "all_plan_adapters",
]
